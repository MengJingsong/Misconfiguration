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

### Amendment 2026-10-29 (stage-4 audit, before the freeze): B2 and B3 replaced by the design below

Operand kind (none-type-design.md section 2): **1, a count of held data** (`size` and `tombstones.size` are element counts). Reasons, all independent of any reading:
(a) the filed B2f/B2g use `unsharedHeapSize()` as "retained heap", but reading `add()` (RangeTombstoneList.java:143-179) shows its tail
`boundaryHeapSize += start.unsharedHeapSize() + end.unsharedHeapSize();` at **:178** runs *after* `addInternal` -> `setInternal` has already added the same amount (:766), for every path except the
first-element path (:151-155); the merge branch (:220-232) reaches `setInternal` through `insertFrom`/`addInternal` only. So the counter `boundaryHeapSize` is counted twice per element on the add() branch and once on the merge
branch (this settles the open point at the end of A3). `unsharedHeapSize()` (:770-778) therefore **can differ by branch for identical content** while the real objects are identical. The amended
design reads the real retained size (`ObjectSizes.measureDeep`, ObjectSizes.java:230, which exists and uses jamm) and per-call allocation, and records the counter separately; (b) a branch cannot be chosen
for a given (n, m), because the branch is a function of the operands, so "same content, both branches" is made by an *equal-content twin* (below); (c) the filed B3 cannot toggle the branch at scale
(for n > 1,000 both phases take the add() branch) and the effect is below heap noise.
Other audit corrections to the filed text (feedback in section D): A2's sentence "`unsharedHeapSize()` ... not which branch ran" is wrong for the counter (see (a)); B2d's "`ObjectSizes.measureDeep` is not assumed to exist" - it exists (ObjectSizes.java:230);
B2a's `rsync /users/jason92/cassandra-5.0.9` and `-XX:+UseSerialGC` are replaced by `copy-source.sh` and the default collector (allocation is read per thread, the collector does not matter); B2d's "jdb breakpoint at line 215" is replaced by a Byteman rule. Citations re-read in
`cassandra/cassandra-5.0.9/` and found correct: RangeTombstoneList.java 184, 186-187, 189-192, 213, 215-216, 220-232, 520-529, 658, 664-669, 680-686, 770-778; MutableDeletionInfo.java 118, 142; Config.java 798, 802; DatabaseDescriptor.java 4654; StorageServiceMBean.java 1166, 1172; RangeTombstoneListTest.java 235, 263, 281, 719.

**B2 (amended). Unit tier.** One JUnit class `AddAllBranchTest` (harness `harness/none-addall-size--autonomous/`), run with the plain `java` launcher on a `copy-source.sh` tree (not `ant testsome`), default collector, `-Xmx2g`, `-javaagent:jamm`.
Bounds: `BufferClusteringBound.inclusiveStartOf/inclusiveEndOf` over one `Int32Type` column, `cmp = new ClusteringComparator(Int32Type.instance)`, all tombstones `markedAt = 1000`, `localDeletionTime = 0`. A = n tombstones `[4i, 4i+1]`, i < n (built by `add`, outside every window). B = m tombstones `[4k+2, 4k+3]`, k < m. B interleaves with the first m elements of A, nothing overlaps, so `A.addAll(B)` has exactly n + m elements in either branch.
- **Trigger and proof the check ran.** `A.addAll(B)` is the call `MutableDeletionInfo.add(DeletionInfo)` makes (:142). Byteman (a separate JVM run, `AT LINE 215` for the add() branch and `AT LINE 220` for the merge branch, each tracing `$0.size`, `$1.size`, `$0.starts.length`) counts the branch per call; the instrument run uses no agent. A key whose branch count does not match `n > 10*m` is Invalid.
- **Capacity arms.** P: A constructed with capacity n+m (no growth). G: A constructed with capacity n exactly (growth through `growToFree` at the first insertion, growth factor 1.5, in both branches).
- **Sweeps (values fixed here).** S1: n = 10,000, m in {500, 999, 1000, 1001, 2000, 10000} (add, add, merge, merge, merge, merge). S2: m = 1,000, n in {9999, 10000, 10001, 10010} (merge, merge, add, add; the flip is between n = 10,000 and 10,001). Both arms P and G for both sweeps. Each point: 3 warm-up and 7 timed repeats, a fresh A each, B reused.
- **Equal-content twin T (n = 10,000, m = 1,000, arms P and G).** T-merge: one call `A.addAll(B)` (10,000 > 10,000 is false: merge branch). T-add: `A.addAll(Bk)` for k < 1000 where each `Bk` is a one-tombstone list holding the same bound objects as B's k-th tombstone (n >= 10,000 > 10: add() branch every call; `Bk` built outside the window). Final contents are identical (`equals`, :485), so retained size can be compared exactly.
- **Measurements.** (1) `ThreadMXBean.getThreadAllocatedBytes` around the `addAll` call (T-add: around the 1000-call loop) with nothing else inside the window (as `batch_size_fail_threshold-...--guided/Alloc.java`; the test calls the MXBean directly); median, min, max of 7; (2) after the call: `size()`, capacity (reflection on `starts.length`), `unsharedHeapSize()`, `ObjectSizes.measureDeep(list)`, `bsz` = `unsharedHeapSize()` of one start plus one end bound of B, and `equals` against a reference list built in sorted order. Instrument checks before the sweep: an 8 MiB `byte[]` must read 8 MiB to 8 MiB + 64 KiB; an empty window is recorded as the instrument's own baseline.
- **Positive control.** `DatabaseDescriptor.setRangeTombstoneListGrowthFactor(3.0)` (DatabaseDescriptor.java:4654) at (n = 10,000, m = 1,000), arm G, against the same point at 1.5.
- **Noise floor.** The point (10,000, 1,000) in both arms measured as two separate blocks of 7 repeats, one at the start and one at the end of the run; floor = max(range within a block, |difference of the two block medians|), per arm.
- **B2f. Predictions (frozen).** Slot cost with compressed oops: `ClusteringBound[]` 4 + `long[]` 8 + `int[]` 4 + `ClusteringBound[]` 4 = 20 bytes per slot plus 4 x 16 bytes of array headers, so a capacity c costs 20c + 64.
  (i) Arm P: every call allocates at most 4,096 bytes, at every m and n; no step at m = 1,000 or n = 10,001.
  (ii) Arm G: one growth to ceil(1.5 x capacity): S1 m <= 2000: 300,064 bytes; S1 m = 10,000 (two growths, 10,000 -> 15,000 -> 22,500): 750,128; S2: n = 9,999: 300,044; 10,000: 300,064; 10,001: 300,104; 10,010: 300,364; each within +-10 percent. Resulting capacity: 15,000 (and 22,500 for m = 10,000).
  (iii) Branch-adjacent pairs (S1 m = 999 vs 1000, S2 n = 10,000 vs 10,001, and the twin T-merge vs T-add): per-call allocation differs by at most max(2 x noise floor, 1,024 bytes) once the closed-form growth of (ii) is allowed for. For T the two totals are compared directly: arm P both at most 4,096 + 1000 x 256 bytes; arm G both within 10 percent of 300,064 plus at most 256,000 bytes of per-call overhead.
  (iv) Result `size()` = n + m and the twin results are `equals`; Byteman counts: add branch for m = 500, 999 (S1), n = 10,001, 10,010 (S2) and every T-add call; merge branch for the rest.
  (v) Real retained size: `measureDeep(list) - (20 x capacity + 64)` divided by (n + m) is the same for every point of both sweeps within 1 percent; T-merge and T-add give `measureDeep` within 64 bytes of each other in each arm.
  (vi) Counter (reported separately, not the verdict): `unsharedHeapSize()` of T-add minus T-merge equals 1000 x `bsz` exactly (the double count at :178), with equal capacity in each arm.
  (vii) Control: arm G at growth factor 3.0 allocates 600,064 bytes +-10 percent (capacity 30,000), at least 1.8 times the 1.5 reading, and `unsharedHeapSize()` rises by 300,000 +-1 percent.
**B2g. Readings (amended; each row also needs the control and both branches observed).**

| Observation | Meaning | Verdict | Effect |
|---|---|---|---|
| (iii), (iv), (v) hold, control moved (vii) | the branch does not change what is allocated or retained; usage follows the data and the growth factor | Confirmed | does not cap |
| as the row above, and (vi) holds (the counter differs by branch by 1000 x `bsz`) | as above, plus an accounting divergence in `add()` (:178) that is recorded as feedback; the memtable-level effect of the inflated counter (`BTreePartitionUpdater.java:121`) is not measured here | Confirmed | does not cap (real usage); counter divergence reported |
| allocation or `measureDeep` differs by branch by more than max(2 x noise, 1,024 bytes) and the closed form of growth does not explain it | the branch gates an allocation or retention | Refuted | caps (or caps only on some paths) |
| (iii) differences between the noise floor and twice the floor | not resolved | Not confirmed | undetermined |
| control did not move, only one branch observed, `size()` != n + m, twins not `equals`, or a Byteman count contradicts `n > 10*m` | the experiment could not show an effect | Invalid / Not confirmed | undetermined |
| a sub-prediction numeric (ii), (vi) missed while the relations (iii), (v) hold | the arithmetic of the prediction was off | Confirmed, with the miss recorded | does not cap |

**B2h. Controls.** Same content in the twin (`equals`); same JVM and collector; arm P isolates the branch from growth, arm G shows the growth both branches share; the growth factor changed in one run only and restored to 1.5; ranges disjoint; A and B built outside every window; the branch proved by Byteman in a separate run.

**B3 (amended). Cluster tier.** `n/a: operand cannot be toggled at scale and the effect is below heap noise.` In a real node the branch is a function of the memtable list size n and the update size m: with n > 1,000 both of the filed phases (m = 1 and m = 100) take the add() branch for almost every update, so a cluster run has no merge-branch arm to compare; the whole data of 100,000 tombstones is tens of MB, close to the heap noise of a node (about +-16 MiB with G1), and the per-element difference is bytes. The unit tier decides. B3a-B3h, B3 predictions and B3 readings below are the filed text and are **not run**.

*The text from here to B4 is the filed B2/B3 as of 2026-10-27, kept for the record; the amendment above replaces it for the run.*

### B2. Unit tier (as filed 2026-10-27; superseded by the amendment above)

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

### B3. Cluster tier (as filed 2026-10-27; `n/a` by the amendment above)

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

**2026-10-29, stage 4 (autonomous, unit tier only; results: [`results/none-addall-size--autonomous.md`](../../stage4-runtime-verification/results/none-addall-size--autonomous.md)).** Verdict: **Confirmed, does not cap** (real memory); outcome class **true negative** (estimate `negative`). Cluster tier `n/a: operand cannot be toggled at scale and the effect is below heap noise`. B2/B3 were amended before the freeze (section B, dated 2026-10-29); the estimate is unchanged.
Readings: per-call allocation and `ObjectSizes.measureDeep` are equal on both sides of `size > 10 * tombstones.size` (arm P, capacity n+m: 0 bytes at every point; arm G, capacity n: 300,064 bytes = one growth to 15,000 slots at 20 bytes per slot plus 64, 750,128 for m = 10,000; the twin "one merge call vs 1000 add() calls" gives equal allocation and equal deep size, 2,860,224 / 2,940,224 bytes); growth factor 3.0 doubled the allocation (600,064) and raised `unsharedHeapSize()` by 300,000; noise floor 0; Byteman: ADD 20,080 calls, MRG 190 calls, none contradicting the literal.
Feedback for stage 3 (corrections to the filed text; none changes the estimate):
1. **A2 and B1 say `unsharedHeapSize()` does not depend on the branch; it does.** `add()` (RangeTombstoneList.java:143-179) adds `start.unsharedHeapSize() + end.unsharedHeapSize()` to `boundaryHeapSize` at **:178** after `addInternal` -> `setInternal` (:766) has already added it, on every path except the first-element path (:151-155). The merge branch reaches `setInternal` only. Measured: for the same 1,000 tombstones `unsharedHeapSize()` is exactly 1000 x 240 = 240,000 bytes higher through the add() branch (5,499,384 at m = 999 vs 5,259,872 at m = 1000, while `measureDeep` is 2,859,976 vs 2,860,224). The open point at the end of A3 is settled. The counter feeds the memtable's accounted heap (`BTreePartitionUpdater.java:121`), so the add() branch (the common one for memtable updates, since n is usually more than 10 m) inflates the accounted heap; whether that flushes a memtable earlier at node level was not measured (below heap noise). Worth a note for any later case on memtable accounting.
2. B2d's "`ObjectSizes.measureDeep` is not assumed to exist": it exists (ObjectSizes.java:230) and works with the jamm agent.
3. B2a's copy path (`/users/jason92/cassandra-5.0.9`) and `-XX:+UseSerialGC` are replaced by `copy-source.sh` and the default collector.
4. B3 cannot toggle the branch: with n > 1,000 both of the filed phases (m = 1 and m = 100) take the add() branch.
5. Citations re-read and correct: RangeTombstoneList.java 184, 186-192, 213, 215-216, 220-232, 520-529, 658, 664-669, 680-686, 770-778; MutableDeletionInfo.java 118, 142; Config.java 798, 802; DatabaseDescriptor.java 4654; StorageServiceMBean.java 1166, 1172; RangeTombstoneListTest.java 235, 263, 281, 719.
