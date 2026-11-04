# repair_session_space — HistogramBuilder.add values array — verification solution  <!-- file: cases/repair-session-space-histogram-add-values--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/utils/HistogramBuilder.java:45` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code agent, 2026-10-26 (design only, nothing built or run) |
| Estimate | `negative`. `HistogramBuilder.values` has no limit of its own and is not counted in the repair Merkle-tree budget (`repair_session_space`); it only grows with the leaf count of a tree that the budget bounds, and only when DEBUG logging is on. |
| Ground | The target line is a plain doubling growth of a `long[]` (`HistogramBuilder.java:45-47`). The class has no cap, no config entry and no constant. Its sole production callers are `MerkleTree.histogramOfRowSizePerLeaf/histogramOfRowCountPerLeaf` (`MerkleTree.java:464-487`), reached only from `Validator.complete()` inside `if (logger.isDebugEnabled())` (`Validator.java:226-233`). `repair_session_space` sizes the tree (`ValidationManager.java:62-77`) at tree-node cost per leaf; the 8 B/leaf array (plus the discarded half-size copy during growth) is allocated on top of that budget and is never charged to it. It is memory-significant only at the maximum depth (about 10.5 MB array, about 15.7 MB peak with the old copy, per builder, per tree). |

## A. Constraint trace

**A1. The constraint.** The line given is not itself a constraint. The nearest constraint that sizes the object it fills is `repair_session_space` (with `repair_session_max_tree_depth` as a second cap on the same quantity).
- `repair_session_space`: configuration entry, `DataStorageSpec.IntMebibytesBound`, declared `src/java/org/apache/cassandra/config/Config.java:207-208` (renamed from `repair_session_space_in_mb`). Unit MiB. Default null, then set in `DatabaseDescriptor.java:609-610` to `max(1, maxMemory / (16 * 1048576))`, i.e. 1/16 of max heap in MiB. Settable by yaml key `repair_session_space` (restart) and at runtime via JMX `ActiveRepairService.setRepairSessionSpaceInMiB` (`DatabaseDescriptor.java:4091-4101`, minimum 1; warns above heap/4). Commented entry in `conf/cassandra.yaml:826-840`.
- `repair_session_max_tree_depth`: `Config.java:206`, default 20 (`DatabaseDescriptor.java:596-607`; deprecated, min 10 enforced at startup, `setRepairSessionMaxTreeDepth` also min 10). Settable in yaml and via `StorageService` JMX.
- Within the entry pointer: `HistogramBuilder.values`, `new long[10]` at `HistogramBuilder.java:40`, doubled at `:46`. No bound.

**A2. What it caps.** Heap (and, when `use_offheap_merkle_trees` is true, `conf` `Config.java:212`, off-heap) used by Merkle trees during validation compaction. The quantity compared: a depth estimated from `repair_session_space * 1048576 / RF` scaled by the range's share of partitions, converted to depth with `MerkleTree.estimatedMaxDepthForBytes(..., 32)` (`MerkleTree.java:1520-1541`, leaf and inner node sizes measured with `ObjectSizes.measureDeep`). Not compared against the histogram array at all.

**A3. Mechanism.**
1. `ValidationManager.createMerkleTrees` (`ValidationManager.java:54-88`): `availableBytes = repair_session_space MiB / RF` (`:62-63`); per range `rangeAvailableBytes = max(1, ratio * availableBytes)` (`:71`); `estimatedMaxDepth` from bytes (`:74`); `maxDepth = min(estimatedMaxDepth, repair_session_max_tree_depth)` (`:75-77`); `depth = min(ceil(log2(numPartitions)), maxDepth)` (`:79`); `trees.addMerkleTree(2^depth, range)` (`:80`).
2. `MerkleTree.init()` splits to `min(floor(log2(maxsize)), hashdepth)` (`MerkleTree.java:139-148`), so leaves <= 2^depth <= 2^20 = 1,048,576.
3. After the validation scan, `Validator.complete()` (`Validator.java:221-237`), only if `logger.isDebugEnabled()`, calls `trees.logRowCountPerLeaf` and `logRowSizePerLeaf` (`MerkleTrees.java:273-292`). For each tree this creates a `HistogramBuilder`, iterates every leaf with `TreeRangeIterator` and calls `add` once per leaf (`MerkleTree.java:464-487`).
4. `add` (`HistogramBuilder.java:43-48`): when `count == values.length` it allocates `Arrays.copyOf(values, length << 1)`; capacity sequence 10, 20, 40, ... = 10*2^k. Outcome at the "limit": there is none; the array just grows with the number of leaves. `buildWithStdevRangesAroundMean` then allocates only small arrays (<= 9 boundaries, `:70-112`).
5. Arithmetic: n = 2^20 leaves gives capacity 10*2^17 = 1,310,720 longs = 10,485,776 B (16 B header + 8 B each); the previous 655,360-long array (5,242,896 B) is live at the copy, so peak about 15.7 MB per builder; builders are sequential (count, then size) and per tree, so they do not stack, but they sit on top of the tree itself. For n = 2^13 (about 8 k leaves) the array is about 82 KB.
- Bypass/overshoot: the array is not in the budget at all (budget counts only node and hash bytes, `MerkleTree.java:1534-1539`); the transient array is an unbudgeted extra of roughly 8 to 24 B per leaf. With DEBUG off (logger level INFO for `org.apache.cassandra.repair`) it is zero. Default `conf/logback.xml:132` sets `org.apache.cassandra` to DEBUG, so it is on in the stock install.

**A4. Other consumers.** Memtables, key and chunk caches, compaction buffers, the `TreeRangeIterator` stack and `TreeRange` objects created during the same iteration, and the serialized tree response all use heap outside `repair_session_space`. `concurrent_merkle_tree_requests` (`Config.java:210`, `cassandra.yaml:861`, 0 = no limit) multiplies the number of trees held at once, and the coordinator holds RF trees (comment `ValidationManager.java:59-60`).

**A5. Evidence beyond the source.** CASSANDRA-14096 (repair_session_space and tree depth sizing), CASSANDRA-11390, CASSANDRA-5263 (as cited in `ValidationManager.java:68-78`), CASSANDRA-19336 (`concurrent_merkle_tree_requests`, cited in `conf/cassandra.yaml:858`). Unit test `test/unit/org/apache/cassandra/utils/HistogramBuilderTest.java` exercises only correctness of the ranges. JDK: `Arrays.copyOf`, JFR events `jdk.ObjectAllocationOutsideTLAB` and `jdk.ObjectAllocationInNewTLAB`, `ThreadMXBean` allocation counters (JDK 11 docs).

## B. Verification solution

**B1. Claim under test.** The `long[]` that `HistogramBuilder.add` grows is not governed by `repair_session_space`: it is allocated on top of the Merkle-tree budget, it depends on the leaf count (flat once the tree hits the depth cap of 20, whatever `repair_session_space` is above that), and it exists only when DEBUG logging is on. Falsified if the array's size stays within, or is shrunk by, the budget at fixed leaf count, or if it is allocated with DEBUG off.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk, never build in the shared copy: `rsync -a ~/cassandra-5.0.9/ /local/scratch/c509/` (path on local disk with at least 5 GB free), `cd /local/scratch/c509 && ant jar` (build needs network for dependency download once; or use a pre-populated `~/.m2`). **[Amended 2026-10-26, stage-4 audit: the run does not use `testsome` (it forks a 1 GiB JVM that ignores `-Xmx`). It uses the non-test alternative below. The copy is made with `stage4-runtime-verification/copy-source.sh ~/s4-b7-hv/c509` (not rsync from `~/cassandra-5.0.9`), built with `ant build-test`; the probe is compiled with `javac` against `build/classes/main` and `build/lib/jars/*` into a separate output directory, and run with `-javaagent:build/lib/jars/jamm-*.jar` (`ObjectSizes.measureDeep` needs it), `-Dcassandra.config=file://<copy>/conf/cassandra.yaml`, and the options of `conf/jvm11-clients.options`. Harness: `harness/repair-session-space-histogram-add-values--autonomous/`.]** Put the test class in the copy at `test/unit/org/apache/cassandra/utils/HistogramBudgetProbe.java`, package `org.apache.cassandra.utils` (the histogram methods on `MerkleTree` are package-private). Run: `ant testsome -Dtest.name=org.apache.cassandra.utils.HistogramBudgetProbe -Dtest.jvm.args="-Xmx2g -Xms2g"`. Non-test alternative: compile the probe against `build/classes/main` and `build/lib/jars/*` and run `java -Xmx2g -cp ... ` with `DatabaseDescriptor.daemonInitialization()` first.

**B2b. Knobs.**
- Budget `S` = `repair_session_space` in MiB, set by `DatabaseDescriptor.setRepairSessionSpaceInMiB(S)` (call `daemonInitialization()` first): 1, 8, 64, 512, 2047, 2048, 4096 **[Amended 2026-10-26, stage-4 audit, before any reading: 2047 and 2048 added. Source finding: `ValidationManager.java:62-63` computes `getRepairSessionSpaceInMiB() * 1048576 / RF` in `int` arithmetic (the getter returns `int`, `DatabaseDescriptor.java:4096`), so it wraps for S >= 2048 MiB: S = 2048 gives -2^31, S = 4096 gives 0; `Math.max(1, (int) ...)` at `:71` then makes `rangeAvailableBytes` 1 and `estimatedMaxDepthForBytes` returns 1. The probe reproduces the `int` arithmetic exactly.]**. Why: spans the range where `estimatedMaxDepthForBytes` is below the cap (small S) to well above the depth-20 cap.
- RF = 3 (divisor, as in `ValidationManager.java:62-63`), fixed; also RF = 1 with S = 2047 (cap case, no wrap) and S = 4096 (wrap).
- `repair_session_max_tree_depth` D: 10, 20 (default), set by `setRepairSessionMaxTreeDepth`.
- Leaf count n: driven directly (below), 2^8 ... 2^20.
- Debug flag: direct calls to `histogramOf*` have no flag, so the probe also calls `Validator`-equivalent logic: `if (logger.isDebugEnabled())` is skipped by hand; the off case is covered at cluster tier.

**B2c. Workload.** For each (S, D): compute `depth = min(estimatedMaxDepthForBytes(Murmur3Partitioner.instance, (S*1048576/3), 32), D)` exactly as `ValidationManager.java:71-77`, with `rangeOwningRatio = 1`, and assume numPartitions >= 2^depth so `depth` is not limited by data (line 79). Build the tree as production does, `new MerkleTrees(Murmur3Partitioner.instance).addMerkleTree(1 << depth, fullRange)` (hashdepth is `RECOMMENDED_DEPTH` = 126, `MerkleTree.java:89`, `MerkleTrees.java:108-110`; it is not `depth`; the size cap `maxsize = 2^depth` sets the split depth) and call `init()` (all leaves exist, `MerkleTree.java:139-148`; `Validator.java:124`). **[Amended 2026-10-26, stage-4 audit: replaces `new MerkleTree(..., depth, 1L << depth)`, which passes a different hashdepth than production. The leaf count after `init()` is read back from `tree.size()` and reported; it is not assumed to be 2^depth.]** Then call `tree.histogramOfRowCountPerLeaf()` (this adds one value per leaf). Separately, drive `HistogramBuilder` alone with n = 10, 11, 20, 21, 2^10, 2^13, 2^17, 2^20, 2^20+1 values. Arithmetic: at depth 20 there are 1,048,576 leaves, so the limit (maxsize 2^20) is reached and the array reaches capacity 1,310,720.

**B2d. Observables and instruments.**
- (i) `values.length` of the builder after the adds, read by reflection on `HistogramBuilder.values` (private, `setAccessible(true)`; JDK 11 allows it for the app classpath). Needs a builder the probe owns, hence the direct runs above.
- (ii) Bytes allocated by the thread around `histogramOfRowCountPerLeaf()`: `((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId())` before and after; includes TreeRange garbage, so it is an upper bound and is reported with the per-leaf slope.
- (iii) Tree size reference: `ObjectSizes.measureDeep(tree)` for on-heap trees (budget-side value), after `init()`.
- (iv) `MerkleTree.size()` (leaf count, `:180`) to confirm n.
Not observable: peak live bytes inside `Arrays.copyOf` (use JFR at cluster tier).

**B2e. Procedure.**
1. Copy and build as in B2a.
2. Run the probe for each (S, D) in B2b, printing: S, D, estimatedMaxDepth, depth used, `tree.size()`, `measureDeep(tree)`, thread-allocated bytes of the histogram call, and from the direct run the `values.length` for the same n.
3. Run the direct sweep over n.
4. Repeat each point three times in one JVM after one warm-up; take the median of allocated bytes.
5. Positive control run (B2h) in the same program.
6. Delete `/local/scratch/c509` when done.

**B2f. Predictions (before any run).**
- `values.length(n) = 10 * 2^ceil(log2(n/10))`: n=10 gives 10; 11 gives 20; 2^13 = 8192 gives 10,240; 2^17 gives 163,840; 2^20 gives 1,310,720; 2^20+1 gives 1,310,720. Exact.
- For fixed n the array size is independent of S. Across S (RF = 3, D = 20): depth, hence n, increases with S until it reaches D; for S >= about the value where estimatedMaxDepth >= 20 (need roughly 2^20 * (leaf+inner node bytes) * 3 bytes of budget), n stays 2^20 and values.length stays 1,310,720 for S = 512 (if reached) and 2047. **[Amended 2026-10-26, stage-4 audit, before any reading, replacing "and 4096": for S = 2048 and S = 4096 the `int` budget wraps (B2b), the tree has depth 1, n = 2 and values.length = 10; the same for RF = 1 with S = 4096. RF = 1 with S = 2047 gives depth 20, values.length 1,310,720.]**
- With D = 10, n <= 1024, values.length <= 1,280 (10*2^7), for all S.
- Array bytes per leaf lies between 8 and 16 B (capacity slack 1x to 2x of 8 B); thread-allocated bytes of the histogram call at depth 20 is above 10.5 MB and below about 120 MB (includes iterator garbage).
- `measureDeep(tree)` per leaf is much larger than 8 B (tens to hundreds of bytes). The array is therefore a small, unbudgeted fraction (expected a few percent to about 20 percent) of the tree it describes.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| values.length follows the formula and is identical across S at equal n | Array is a function of leaf count only; not governed by S directly (claim holds) |
| n and values.length rise with S until depth 20 then stay constant at 1,310,720 | Indirect dependence through the tree size, saturating at the depth cap (claim holds: the cap that binds is the depth cap, not a histogram limit) |
| values.length at n = 2^20+1 exceeds 1,310,720 | Not possible via the tree; would mean a different growth rule, revisit A3 |
| Builder array shrinks or is truncated when S is small at equal n | Claim refuted: some budget acts on the array |
| Array exceeds S/RF at some small S (e.g., S = 1 MiB gives 349,525 B tree budget; array for the resulting n is less than that) | Report ratio only; array exceeding the per-tree budget would confirm "unbudgeted overshoot", staying under it is not a refutation, since the budget need not contain it |
| Usage flat in S above the depth cap while the positive control (tree bytes via `measureDeep`) also flat | Consistent; both capped by D |
| (Amended 2026-10-26) S = 2048 or 4096: depth 1, n = 2, values.length = 10, tree bytes collapse | The budget's `int` arithmetic wrapped (`ValidationManager.java:62-63`); the array still follows the leaf count only; a source finding about the budget, not a refutation |
| Usage flat in S while the positive control (tree bytes at S below the cap) moves | Claim confirmed for the array vs the budget |
| Limit never reached (no run reaches depth 20) or tree bytes did not move with S | Not confirmed; raise S or fix depth by calling `new MerkleTree(..., 20, 1L<<20)` directly |

**B2h. Controls.**
- Positive control: the tree's own footprint `measureDeep(tree)` for the same (S, D), which is the object that the budget does bind (`ValidationManager.java:71-77`); it should rise about proportionally to 2^depth as S rises from 1 to the cap.
- Direct `HistogramBuilder` sweep removes the iterator/tree effects.
- Fixed JVM heap (`-Xmx2g -Xms2g`), `System.gc()` before each timing, same JIT warm-up, single thread, so allocation counters are comparable.
- A run with the histogram call removed (only `TreeRangeIterator` iteration) subtracts iterator garbage from (ii).

### B3. Cluster tier

**B3a. Environment and build. [Amended 2026-10-26, stage-4 audit; replaces the paths and addresses below where they differ: copy with `copy-source.sh ~/s4-b7-hv/c509` and `ant build-test` (the stress tool is needed); node addresses 127.0.2.1 (node 1) and 127.0.2.2 (node 2) on the one host pc12, the loopback block needs no alias; JMX ports 7120 (node 1) and 7121 (node 2); native transport only on 127.0.2.1:9042 (`start_native_transport: false` on node 2); data, commit log, hints, saved caches, JFR and GC logs under `/dev/shm/s4-b7-hv/` (tmpfs, 126 GB, not the NFS); `initial_token` -4611686018427387904 (node 1) and 4611686018427387904 (node 2), `auto_bootstrap: false`, both nodes in `seeds`, so each owns half the ring and the primary range of each holds about 1M of the 2M partitions; node processes are stopped by recorded PID, never `pkill -f`. Environment deviation: the design wants two hosts; both nodes run on pc12.]** Two nodes (RF = 2, so the divisor is 2) on one Linux host, JDK 11, built from a local copy: `rsync -a ~/cassandra-5.0.9/ /local/scratch/c509/ && cd /local/scratch/c509 && ant jar`. Run two instances from that build directory with separate `CASSANDRA_CONF` dirs copied from `conf/`, `listen_address`/`rpc_address` 127.0.0.1 and 127.0.0.2 (add loopback alias if missing), `seed_provider` 127.0.0.1, `num_tokens: 1`, `endpoint_snitch: SimpleSnitch`, data/commitlog/hints/saved_caches on local disk (`/local/scratch/n1`, `/local/scratch/n2`, each with at least 10 GB free), `cassandra.logdir` local. JVM: `MAX_HEAP_SIZE=3G HEAP_NEWSIZE=600M` per node (so heap/4 is 768 MiB, which bounds the sensible `repair_session_space` before the warning at `DatabaseDescriptor.java:614`; the warning is only a warning). JFR on startup: `-XX:StartFlightRecording=filename=/local/scratch/n1/rec.jfr,settings=profile,dumponexit=true` plus a custom setting that enables `jdk.ObjectAllocationOutsideTLAB` with `stackTrace=true` and threshold 0 (copy `$JAVA_HOME/lib/jfr/profile.jfc`, set `jdk.ObjectAllocationOutsideTLAB#enabled=true`). **[Amended 2026-10-26, stage-4 audit: arrays under the TLAB size are allocated inside a TLAB and JFR does not report each one, so the JVM also gets `-XX:-ResizeTLAB -XX:TLABSize=16k`, which sends every allocation of 16 KB or more outside the TLAB; the instrument check shows JFR then reports the known arrays of a standalone driver before run 1. Both nodes get the same JVM options.]**

**B3b. Knobs.**
- `repair_session_space` S in MiB: 8, 64, 700 (yaml key, restart; or JMX `ActiveRepairService` attribute without restart). 700 is under heap/4 = 768 MiB. Why: 8 should limit depth below 20; 700 with RF 2 gives 350 MiB per tree, enough for depth 20 if a node costs under about 330 B per leaf-plus-inner pair (expected, `estimatedMaxDepthForBytes`); the debug log line "Created ... merkle trees" shows the resulting size.
- `repair_session_max_tree_depth` D: 20 (default) and 12.
- Logger level for `org.apache.cassandra.repair.Validator`, `ValidationManager`, `MerkleTrees`, `MerkleTree`: DEBUG (stock) vs INFO, via `nodetool setlogginglevel org.apache.cassandra INFO` (and `... DEBUG` to restore).
- `use_offheap_merkle_trees` true (default); false for a run where the tree is also on heap.

**B3c. Workload.** Keyspace `ks` RF 2, table `t(id bigint primary key, v blob)` single small blob (about 32 B). Load 2,000,000 distinct partitions, so `ceil(log2(2e6)) = 21` and depth is bounded by `min(21, estimatedMaxDepth, D)`; with D = 20 and a large S, the tree reaches depth 20 (1,048,576 leaves, the limit being reached). Load with cassandra-stress built in the copy: `tools/bin/cassandra-stress write n=2000000 -schema "replication(factor=2)" -rate threads=32 -node 127.0.0.1` (or a CQL-driven loop). Disk: 2 M rows of about 100 B including overhead is under 1 GB per node. Make the nodes inconsistent so validation does real work: not required, since Validator.complete runs regardless of mismatches. Run `nodetool -h 127.0.0.1 repair -full ks t` once per configuration. **[Amended 2026-10-26, stage-4 audit: `cassandra-stress` creates `keyspace1.standard1`, not `ks.t`, so the table is `keyspace1.standard1` with replication factor 2 (`-schema "replication(factor=2)"`), and the repair is `nodetool -p 7120 repair -full -pr keyspace1 standard1`. Reason for `-pr`: without it each node validates two ranges in one session (its own and its neighbour's, RF 2 on 2 nodes), each tree gets half of the budget (`rangeOwningRatio` 0.5, `ValidationManager.java:70-71`), and S = 700 would sit at the edge of depth 20; with `-pr` there is one range and the tree gets the whole budget. Each node validates the same range, so each node builds one tree. The change does not touch the prediction or the conclusions table.]** Duration: load about 5-10 min, each repair a few minutes.

**B3d. Observables and instruments.**
- JFR events `jdk.ObjectAllocationOutsideTLAB` (large arrays) filtered to the top frame `HistogramBuilder.add` / `java.util.Arrays.copyOf` with caller `HistogramBuilder.add`: sizes of each allocated `long[]`, read with `jfr print --events jdk.ObjectAllocationOutsideTLAB --stack-depth 4 rec.jfr` (parse sizes).
- `system.log`/`debug.log` lines from `ValidationManager.java:83-84` ("Created N merkle trees with merkle trees size ..., P partitions, B bytes") for the budget side, and the "Partitions per leaf" lines from `Validator.java:228-232` as evidence the histogram path ran.
- Heap: `jstat -gc <pid> 1000` and GC logs (`-Xlog:gc*:file=/local/scratch/n1/gc.log`) for old/young occupancy during validation; `jcmd <pid> GC.class_histogram` right after `complete` is too transient, so used only as a sanity check for `long[]` retained.
- Disk: `df` on local volumes (only to confirm no growth attributable to this path).
Not directly observable: the exact peak instant of old plus new array (JFR gives both allocations; compute sum).

**B3e. Procedure.**
1. Build and prepare two node configs (B3a). Check ports free and no stray Cassandra (`pgrep -fa CassandraDaemon`).
2. Start node1 then node2 with S = 700, D = 20, level DEBUG; wait `nodetool status` shows UN UN.
3. Create schema and load the 2 M partitions; `nodetool flush`.
4. Run 1 (DEBUG, S=700, D=20): `nodetool repair -full ks t`; when done `nodetool -h ... compact` is not needed. `jcmd <pid> JFR.dump filename=...` to capture. Record the debug.log "Created" line and the `long[]` sizes.
5. Run 2: `nodetool setlogginglevel org.apache.cassandra INFO`, repeat repair, dump JFR. Expect no `HistogramBuilder.add` allocations.
6. Run 3: restore DEBUG; JMX-set S = 64 (or restart), repeat repair; run 4: S = 8; run 5: S = 700, D = 12 (JMX `StorageService` `setRepairSessionMaxTreeDepth` or restart).
7. After each run, extract from the JFR the largest `long[]` size from `HistogramBuilder.add` and sum of its allocations per tree; from debug.log the tree size in leaves and bytes.
8. Cleanup (B4).

**B3f. Predictions.**
- (Amended 2026-10-26, stage-4 audit: "tree" below means one Merkle tree for the repaired range; with `-pr` each node builds one.)
- Run 1: the largest `long[]` from `HistogramBuilder.add` is 10,485,776 B (1,310,720 longs) and the one before 5,242,896 B, per tree per call, so two calls (count and size) each produce the same sequence; the debug.log shows a tree of 2^20 leaves.
- Run 2 (INFO): zero allocation events with `HistogramBuilder.add` in the stack; no "Partitions per leaf" lines.
- Runs 3-4: the largest array falls as the tree falls: leaves = 2^depth(S) with depth(S) = floor(log2(S*1048576/2 / (leaf+inner bytes))); strictly smaller for S = 8 than S = 64 than S = 700; every array size is 16 + 8*10*2^k for integer k.
- Run 5: D = 12 caps the tree at 4096 leaves and the largest array at 16 + 8*5,120 = 40,976 B regardless of S.
- Relation: array bytes per leaf is 8 to 16, below one fifth of the tree's per-leaf bytes (tree bytes from the "Created ... bytes" line divided by leaves) **[Amended 2026-10-26, stage-4 audit, before any reading: the "Created ... bytes" figure is the serialized size (`MerkleTrees.serializer.serializedSize`), not heap bytes, so it is only a proxy and is reported but not used for this relation. The relation is judged against the heap bytes per leaf of the same tree class measured at the unit tier by `ObjectSizes.measureDeep(tree) / tree.size()`.]**, so the combined peak is the budget plus an unbudgeted extra of about 5 to 20 percent only when DEBUG is on.
- No growth in disk use attributable to this path.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| No `HistogramBuilder.add` allocations with INFO, allocations with DEBUG | Array exists only under DEBUG; confirms A3 and the negative ground |
| Largest array at S=700, D=20 is 10,485,776 B and unchanged for any larger S | Array saturates at the depth cap; not governed by S above the cap |
| Largest array falls with S at S=8, 64 (below the cap) | Dependence only through leaf count (indirect); claim still holds as "not an independently budgeted object" |
| Largest array is still 10,485,776 B at S=8 | Claim wrong in the other direction: the budget did not shrink the tree; investigate `estimatedMaxDepthForBytes` |
| Array allocated with DEBUG off | Claim refuted; some other caller exists (grep again) |
| Array exceeds the debug.log tree size per leaf (more than the tree's bytes) | Strongest unbudgeted overshoot |
| Heap during validation (jstat) shows no visible bump from the arrays (about 15 MB against 3 GB heap) | Expected; array is not memory-significant at this heap, consistent with negative |
| Positive control moves (tree size rises with S, below the cap), array flat above the cap | Claim confirmed |
| Depth 20 never reached (debug.log shows smaller trees) or control flat | Not confirmed; raise S or lower RF effect (RF 1 is not valid for repair; use more partitions or raise S) |

**B3h. Controls.**
- Positive control: the same workload with S varied below the cap (8, 64); the tree bytes in the debug.log line and the `OnHeapLeaf`/off-heap allocation counts move with S, which is the cap known to bind (`ValidationManager.java:71-77`).
- Negative control: the INFO run, same data, same S: zero histogram arrays.
- Same data set, no writes between runs; `nodetool flush` and a major compaction before the first run so sstables are identical across runs.
- Same heap and GC for all runs; repeat run 1 twice to see variation.
- Confirm via debug.log that each run executed on both nodes; take JFR from the node that logged "Partitions per leaf".

**B4. Risks and cleanup.** Disk: all data, commit logs, hints, JFR and GC logs on local `/local/scratch` (known size, at least 10 GB per node), never on shared storage; load is under 1 GB per node. Memory: two 3 GB heaps plus JFR; check host RAM before starting. Do not build in or write into `~/cassandra-5.0.9`. Stop processes: `nodetool drain` then kill both daemons (`pkill -f CassandraDaemon` for only this run's PIDs, recorded at start), then `pgrep -fa 'CassandraDaemon|cassandra-stress|java.*HistogramBudgetProbe'` must return nothing; remove the loopback alias if one was added; delete `/local/scratch/c509`, `/local/scratch/n1`, `/local/scratch/n2` after copying out the JFR and log extracts.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/utils/HistogramBuilder.java
- src/java/org/apache/cassandra/utils/MerkleTree.java (lines 97-192, 400-500, 597-640, 1517-1541)
- src/java/org/apache/cassandra/utils/MerkleTrees.java (lines 262-292)
- src/java/org/apache/cassandra/utils/EstimatedHistogram.java (constructor, `log`)
- src/java/org/apache/cassandra/repair/Validator.java (lines 215-237)
- src/java/org/apache/cassandra/repair/ValidationManager.java (lines 50-125)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 593-616, 4070-4110)
- src/java/org/apache/cassandra/config/Config.java (lines 206-212, by grep)
- conf/cassandra.yaml (lines 825-862)
- conf/logback.xml (grep for debug levels)
- grep results for `HistogramBuilder` usages across `src` and `test`
- Public references named in A5 (cited by key from code comments, not fetched)

## D. Stage-4 feedback

Stage 4, 2026-10-26 (results: `stage4-runtime-verification/results/repair-session-space-histogram-add-values--autonomous.md`). Frozen version: file sha256 `d836ea0c6839efdc65fcb8b41811c94c005ce74eb8ba2b174a0aa109841efc2f`, B2f-g + B3f-g tables `b0c1cc09429e1f07b35025459c48dec6d3c5bdbe5172dc3ae9b688e48a062baa`.
- **Unit: Confirmed — does not cap.** `values.length` = 10*2^ceil(log2(n/10)) on every row, identical across S at equal n; depth 10, 13, 16, 19, 20 for S = 1, 8, 64, 512, 2047 (RF 3), then constant at 1,310,720 longs (10,485,776 B); the tree footprint (`measureDeep`) rose from 0.1 MB to 109 MB over the same S. S = 2048 and 4096 give depth 1 and 10 longs (the `int` wrap, below).
- **Cluster: Confirmed — does not cap** (two nodes on one host, loopback). With DEBUG the largest array is 10,485,776 B at S = 700, 1,310,736 B at S = 64, 163,856 B at S = 8, 40,976 B at D = 12, on both nodes; with INFO no `HistogramBuilder.add` allocation and no "Partitions per leaf" line. The array is about 10 B per leaf against 104 to 200 B of tree heap per leaf (5 to 10 percent).
- **Corrections found by the audit (not readings):** (1) `ValidationManager.java:62-63` computes `repair_session_space * 1048576 / RF` in `int`, so S >= 2048 MiB wraps to a negative or zero budget and a 2-leaf tree; the original B2f line "S = 4096 gives 1,310,720" was wrong (amended, B2b/B2f/B2g). (2) B3 paths and table (`keyspace1.standard1`, `repair -pr`), see the inline amendments.
- **Gaps:** the "Created ... merkle trees with merkle trees size N" line (`ValidationManager.java:83-84`) is logged before `init()`, so B3f's "debug.log shows a tree of 2^20 leaves" cannot be read (size is always 1); the leaf count came from the "Partitions per leaf" bucket sum (2^depth + 1 values). Heap was not sampled during validation (`jstat` empty). The `int` wrap was reproduced in a probe, not in a running node.
- **Open point:** the array follows S through the leaf count up to the depth cap; the file's own B2g/B3g wording ("indirect; claim holds") was followed, giving a true negative.

Stage-4 audit amendments, 2026-10-26 (all made before any reading; each is marked inline next to the text it changes): B2a (standalone probe with jamm agent instead of `testsome`; copy by `copy-source.sh`), B2c (tree built through `MerkleTrees.addMerkleTree` as in production), B3a (paths, loopback addresses 127.0.2.1/127.0.2.2, ports, tmpfs data, tokens, TLAB option for JFR), B3c/B3e (`keyspace1.standard1`, `repair -full -pr`), B3f (the relation line is judged against heap bytes per leaf, not serialized bytes). B2b/B2f/B2g (S = 2047 and 2048 added; S >= 2048 MiB wraps the `int` budget at `ValidationManager.java:62-63`, so the S = 4096 prediction of 1,310,720 was wrong and is replaced; one row added to B2g). Made after the first freeze hash and before any run or reading; the B3 predictions are unchanged apart from the denominator line above.
