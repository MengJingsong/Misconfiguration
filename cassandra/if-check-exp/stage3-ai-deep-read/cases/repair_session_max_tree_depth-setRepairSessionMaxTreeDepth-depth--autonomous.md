# repair_session_max_tree_depth (JMX setter in setRepairSessionMaxTreeDepth) — verification solution  <!-- file: cases/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:4077`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4077) (`4077#1`, `depth < 10`) and `:4080` (`4080#1`, `depth > 20`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code at Meta (version string not available in the sandbox), 2026-10-25, band D triage |
| Estimate | `positive` (scoped: per merkle tree, together with `repair_session_space`). Each validation sizes each range's tree to `2^min(ceil(log2 partitions), estimatedMaxDepth(repair_session_space), repair_session_max_tree_depth)` leaves (`ValidationManager.java:74-80`). Merkle-tree heap on validating replicas and off-heap on the coordinator therefore follow the depth whenever the depth is the smallest term. The value is read at every validation, so a JMX change takes effect on the next repair. Line 4077 enforces a floor (rejects < 10). Line 4080 is only a warning: values > 20 are accepted, so there is no upper cap. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- **Declaration.** `repair_session_max_tree_depth` is a configuration entry ([`Config.java:206`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L206), `volatile Integer`, default `null`). It is deprecated in favour of `repair_session_space`. The unit is tree depth: a tree has at most 2^depth leaves.
- **Startup.**
  - When the entry is null it becomes 20 ([`DatabaseDescriptor.java:604-607`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L604-L607)).
  - When it is set, a deprecation warning is logged (`:598`), values < 10 throw (`:599-600`), and values > 20 log a warning (`:601-602`).
- **Runtime (JMX).** `StorageServiceMBean` exposes two setters, neither reachable from nodetool:
  - the deprecated `setRepairSessionMaxTreeDepth`, which throws `ConfigurationException` ([`StorageService.java:4979-4982`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L4979-L4982));
  - `setRepairSessionMaximumTreeDepth`, which rethrows the same error as `IllegalArgumentException` (`:4992-5002`).
- **Target setter.** Both call `DatabaseDescriptor.setRepairSessionMaxTreeDepth` (`:4075-4084`):
  - line 4077 throws for depth < 10, keeping the old value;
  - line 4080 logs "could lead to excessive memory usage" for depth > 20 and still stores the value (`:4083`).
- **Getter and restart.** The getter is `:4070-4073`. No restart is needed.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** It caps memory: the number of leaves per merkle tree (2^depth), which determines:
- the on-heap tree built during validation on every replica (`MerkleTree.init`, `MerkleTree.java:139-147`, which builds `OnHeapInner`/`OnHeapLeaf` nodes);
- the trees deserialized on the coordinator, off-heap when `use_offheap_merkle_trees` is true (default `Config.java:212`). These need `50·(L−1) + 32·L` bytes for L leaves with Murmur3 (`MerkleTree.java:747-751,799-802,1160-1163,1451-1457`; token size 8 bytes, `Murmur3Partitioner.java:52,269-271`).

**A3. Mechanism.**
1. `ValidationManager.doValidation` → `createMerkleTrees(vi, desc.ranges, cfs)` ([`ValidationManager.java:127`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L127)).
2. `availableBytes = repair_session_space_MiB × 2^20 / RF` (`:62-63`). For each range:
   - `rangeAvailableBytes = max(1, (int)(ratio × availableBytes))` (`:71`);
   - `estimatedMaxDepth = MerkleTree.estimatedMaxDepthForBytes(..., 32)` (`:74`, [`MerkleTree.java:1520-1541`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L1520-L1541));
   - `maxDepth = min(estimatedMaxDepth, getRepairSessionMaxTreeDepth())` ([`ValidationManager.java:75-77`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L75-L77));
   - `depth = min(ceil(log2 numPartitions), maxDepth)` (`:79`);
   - `trees.addMerkleTree(2^depth, range)` (`:80`).
3. `Validator.prepare` calls `trees.init()` ([`Validator.java:124`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/Validator.java#L124)), which builds a full tree of depth `min(log2(maxsize), 126)` ([`MerkleTree.java:139-147`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L139-L147), `RECOMMENDED_DEPTH`, `:89`).
4. When the setter check fails (< 10), an exception is thrown and the value is unchanged. When depth > 20, only a warning is logged.

Paths that bypass or overshoot:
- No upper bound: depth 30 is accepted, and only `repair_session_space` and the partition count then bound the tree.
- The setting is per node and not propagated, so each replica uses its own value.
- The coordinator holds RF trees per range at once (comment at `:60-61`).

**A4. Other consumers.**
- Other validation memory: the partition iterator and compaction buffers.
- Streaming buffers during sync.
- `repair_session_space`, which is the other term in the min.
- Repair state caches (`ActiveRepairService.java:250-260`).

**A5. Evidence beyond the source.**
- NEWS.txt:934, which introduced `repair_session_max_tree_depth`.
- NEWS.txt:819-820, `repair_session_space_in_mb`.
- CASSANDRA-14096 and CASSANDRA-5263, cited at `ValidationManager.java:69,78`: https://issues.apache.org/jira/browse/CASSANDRA-14096, https://issues.apache.org/jira/browse/CASSANDRA-5263.
- CASSANDRA-17668, the JMX setters (`StorageService.java:4975,5005-5009`).

## B. Verification solution

**B1. Claim under test.** When `repair_session_space` and the partition count allow deeper trees, each merkle tree built after a JMX `setRepairSessionMaximumTreeDepth(d)` has exactly 2^d leaves, so tree memory scales with 2^d. Values < 10 are rejected and leave the setting unchanged. Values > 20 are accepted, with only a warning.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Run `git clone --depth 1 --branch cassandra-5.0.9 <shared-clone-path> /local/c509` (never build in the shared clone). Put the test at `/local/c509/test/unit/org/apache/cassandra/repair/TreeDepthSetterTest.java`. Run with `cd /local/c509 && ant testsome -Dtest.name=org.apache.cassandra.repair.TreeDepthSetterTest`. The test JVM has `maxmemory=1024m` (`build.xml:1153`).

**Amendment 2026-10-25 (step-0 audit) — B2a, this host.** Run clone `$W/cassandra-run24` (`W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run24`, full clone, `ant -Dlocal.repository=$W/m2 build-test`), macOS arm64, JDK 11.0.32.1, Ant 1.10.18. The test class (B2e's skeleton with B2e's imports, nothing else) is kept under `stage4-runtime-verification/harness/<stem>/` and copied into the clone's `test/unit/org/apache/cassandra/repair/` by `unit-run.sh`, which runs `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.repair.TreeDepthSetterTest` three times (r1, r2, r3) and copies, after each, the JUnit XML and the test log `build/test/logs/**/TEST-org.apache.cassandra.repair.TreeDepthSetterTest.log`. The partitioner is Murmur3 (`CQLTester.java:418`, `setPartitionerUnsafe`), not the unit yaml's ByteOrdered; the keyspace is SimpleStrategy RF 1. Instrument check (audit): the class compiles in the run clone (`ant build-test`, `BUILD SUCCESSFUL`). Reason: B2a named a CloudLab path.

**B2b. Knobs.**
- Depth via `StorageService.instance.setRepairSessionMaximumTreeDepth(d)`:
  - Rejection values: 9 and 0.
  - Accepted values: 10, 14, 18, 20. These are the floor, two midpoints and the default, spaced so that 2^d spans 1024×.
  - 21 and 30: setter only (warning), not built.
- `repair_session_space` via `DatabaseDescriptor.setRepairSessionSpaceInMiB(1024)`, so that space allows depth ≈ 23 and does not bind.
- Space-binding control: `setRepairSessionSpaceInMiB(1)` with d = 18.

**B2c. Workload.** A stub `ValidationPartitionIterator` reports one full-ring range with 2^22 = 4 194 304 partitions. `ceil(log2)` = 22 ≥ every d, so d is the binding term. Call the private static `ValidationManager.createMerkleTrees` by reflection, then `trees.init()`.

Arithmetic:
- availableBytes = 1024 MiB / RF 1 = 2^30.
- estimatedMaxDepth = floor(log2(2^30 / (leaf+inner ≈ 100–200 B))) ≈ 22–23 ≥ 20.

**Amendment 2026-10-25 (step-0 audit) — B2c, the two other terms, computed.** Computed at the audit by `$W/audit-run24/Depth.java`, which repeats `ValidationManager.java:62-79` (int arithmetic included) with the built clone's `MerkleTree.estimatedMaxDepthForBytes`: space term (Murmur3, RF 1, owning ratio 1.0) = **22** at 1024 MiB and **12** at 1 MiB; data term `ceil(log2 2^22)` = **22**. So at 1024 MiB the entry is the smallest term for every d ≤ 20, and at 1 MiB the space term (12) binds for d = 18. Reason: B2c gave "≈ 22–23" as an estimate.

**B2d. Observables and instruments.**
- `MerkleTrees.size()` after `init()` (`MerkleTrees.java:197-205`; per tree `MerkleTree.java:145-146,180-183`).
- The heap delta, measured with `Runtime.totalMemory()-freeMemory()` after `System.gc()` ×3 before and after `init()`, keeping a strong reference.
- The getter after each setter call.
- `WARN` lines in `build/test/logs` for 21 and 30.

Per-node byte size cannot be observed directly. Bytes per leaf are inferred from the heap delta / leaves.

**Amendment 2026-10-25 (step-0 audit) — B2d, where each reading is read.** The stdout lines (`REJECTED`/`ACCEPTED`, `getter`, `set … getter`, `d=… size=… heapDelta=…`, `control …`) from the XML's system-out; the warning from the test log file, by its exact text `repair_session_max_tree_depth of <v> > 20 could lead to excessive memory usage` (`DatabaseDescriptor.java:4081`), counted per value. Reason: the log path and the exact text were open.

**B2e. Procedure.** Test skeleton:
```java
package org.apache.cassandra.repair;
public class TreeDepthSetterTest extends org.apache.cassandra.cql3.CQLTester {
  static ValidationPartitionIterator stub(Range<Token> r, long n, TableMetadata md) {
    return new ValidationPartitionIterator() {
      public long getEstimatedBytes() { return 0; } public long estimatedPartitions() { return n; }
      public long getBytesRead() { return 0; } public Map<Range<Token>, Long> getRangePartitionCounts() { return Collections.singletonMap(r, n); }
      public TableMetadata metadata() { return md; } public boolean hasNext() { return false; }
      public UnfilteredRowIterator next() { throw new NoSuchElementException(); } };
  }
  static long used() { for (int i = 0; i < 3; i++) System.gc(); Runtime rt = Runtime.getRuntime(); return rt.totalMemory() - rt.freeMemory(); }
  @Test public void depth() throws Throwable {
    createTable("CREATE TABLE %s (k int PRIMARY KEY, v int)");
    ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
    Token min = cfs.getPartitioner().getMinimumToken(); Range<Token> full = new Range<>(min, min);
    java.lang.reflect.Method m = ValidationManager.class.getDeclaredMethod("createMerkleTrees", ValidationPartitionIterator.class, Collection.class, ColumnFamilyStore.class);
    m.setAccessible(true);
    for (int bad : new int[]{9, 0}) { try { StorageService.instance.setRepairSessionMaximumTreeDepth(bad); System.out.println("ACCEPTED " + bad); }
      catch (IllegalArgumentException e) { System.out.println("REJECTED " + bad); } System.out.println("getter " + DatabaseDescriptor.getRepairSessionMaxTreeDepth()); }
    for (int hi : new int[]{21, 30}) { StorageService.instance.setRepairSessionMaximumTreeDepth(hi); System.out.println("set " + hi + " getter " + DatabaseDescriptor.getRepairSessionMaxTreeDepth()); }
    DatabaseDescriptor.setRepairSessionSpaceInMiB(1024);
    for (int d : new int[]{10, 14, 18, 20}) {
      StorageService.instance.setRepairSessionMaximumTreeDepth(d);
      long u0 = used();
      MerkleTrees t = (MerkleTrees) m.invoke(null, stub(full, 1L << 22, cfs.metadata()), Collections.singletonList(full), cfs);
      t.init(); long u1 = used();
      System.out.printf("d=%d size=%d heapDelta=%d%n", d, t.size(), u1 - u0);
      t.release(); t = null;
    }
    DatabaseDescriptor.setRepairSessionSpaceInMiB(1); StorageService.instance.setRepairSessionMaximumTreeDepth(18);
    MerkleTrees c = (MerkleTrees) m.invoke(null, stub(full, 1L << 22, cfs.metadata()), Collections.singletonList(full), cfs); c.init();
    System.out.println("control space=1MiB d=18 size=" + c.size());
  }
}
```
Add the needed imports: `org.apache.cassandra.dht.*`, `org.apache.cassandra.db.*`, `org.apache.cassandra.db.rows.UnfilteredRowIterator`, `org.apache.cassandra.schema.TableMetadata`, `org.apache.cassandra.utils.MerkleTrees`, `org.apache.cassandra.service.StorageService`, `org.apache.cassandra.config.DatabaseDescriptor`, `org.junit.Test`, `java.util.*`. CQLTester's keyspace is SimpleStrategy RF 1.

Run three times. Output is in `build/test/output/TEST-org.apache.cassandra.repair.TreeDepthSetterTest.xml`.

**Runbook fix 2026-10-25 (stage-4 run 1, defect 1) — B2e, where the output is.** "Output is in `build/test/output/TEST-….xml`" does not hold at this tag: the unit-test JVM routes `System.out` to the logger (`test/conf/logback-test.xml`), so the XML's system-out is empty and every printed line is in the test log `build/test/logs/**/TEST-org.apache.cassandra.repair.TreeDepthSetterTest.log` as an `INFO  [main] <time> <text>` line; a `printf` arrives split into one line per format piece (`d=`, `10`, ` size=`, `1024`, ` heapDelta=`, `<n>`), which are joined in order. The readings are read there. B2f, B2g and B2h are unchanged; the unit tier restarts from its beginning.

**B2f. Predictions.**
- **Rejections.** `REJECTED 9` and `REJECTED 0`, with the getter unchanged at 20.
- **Above 20.** For 21 and 30 the getter equals the value set, and one WARN "could lead to excessive memory usage" is logged for each.
- **Sizes.** `size` = 1024, 16 384, 262 144 and 1 048 576 for d = 10, 14, 18, 20.
- **Heap.** heapDelta(20) / heapDelta(18) = 4 ± 0.6. heapDelta(20) / 2^20 lies between 80 and 250 B per leaf. heapDelta for d = 10 and 14 may sit inside GC noise, so only `size` is asserted for them.
- **Control.** space = 1 MiB gives size = 2^floor(log2(2^20 / per-pair bytes)) ≈ 2^12–2^13, well below 2^18, which shows that the min() takes the other term.

**Amendment 2026-10-25 (step-0 audit) — B2f, exact values.** (i) Control: size = 2^12 = **4,096** exactly (space term 12, B2c amendment; inside the filed 2^12–2^13). (ii) Warnings: exactly **one** line for 21 and one for 30, and none for any other value (the sweep values are ≤ 20). (iii) Rejections: the getter reads 20 after 9 and after 0 (the test yaml does not set the entry, so it is 20 from `DatabaseDescriptor.java:604-607`). (iv) Every prediction must hold in each of the three runs. Reason: the control's value was a range; the count and the per-run rule were not stated. Changes no filed value except narrowing the control's range, for a reason read from the source before any reading.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `size` = 2^d for all d and heap ratio ≈ 4 | Claim confirmed: depth caps leaves and memory |
| `size` independent of d | Setting not used by `createMerkleTrees` (claim wrong) |
| 9 or 0 accepted | Floor at 4077 not enforced |
| 21/30 rejected | Line 4080 behaves as a cap, not a warning (estimate of "no upper cap" wrong) |
| Control size = 2^18 | Space term not applied; depth would then be the only bound |

**Amendment 2026-10-25 (step-0 audit) — B2g, rows added.** Row 1 requires all of: `size` = 2^d for d = 10, 14, 18, 20 in all three runs; heapDelta(20)/heapDelta(18) in [3.4, 4.6] and heapDelta(20)/2^20 in [80, 250] B in all three runs; 9 and 0 rejected with the getter 20; 21 and 30 accepted (getter = value) with one warning each; control 4,096.

| Observation | Meaning |
|---|---|
| `size` = 2^d in all runs, but a heap criterion fails in a run | Not confirmed for memory: leaves follow d, the heap reading does not (GC noise or other allocation) |
| 9 or 0 rejected, but the getter is not 20 afterwards | Refuted for "leaves the setting unchanged" |
| 21 or 30 accepted, but the warning count is not 1 | Refuted for the warning part of B1 |
| Control ≠ 4,096 but < 2^18 | Not confirmed: the space term differs from the audit's computation (audit error) |
| Readings differ between the three runs | Not confirmed (unstable) |
| The test does not compile or fails before its last line | Runbook defect; no verdict |

**B2h. Controls.**
- The stub fixes partition counts, so the only varying input is d.
- The space-binding control shows when d is not binding.
- The trees are released between iterations, and three GCs run before each reading.
- Three repetitions.

### B3. Cluster tier

**B3a. Environment and build.** Two nodes on one Linux host, 127.0.0.1 and 127.0.0.2, built with `ant jar` in `/local/c509`. Each node has its own conf copy, `/local/n1/conf` and `/local/n2/conf`, with:
- `cluster_name: td`, `num_tokens: 1`, `initial_token: -9223372036854775808` on n1 and `0` on n2;
- `listen_address`/`rpc_address` = the node IP, `seeds: "127.0.0.1"`;
- data, commitlog, hints, saved_caches and cdc directories under `/local/nX/`;
- `repair_session_space: 1024MiB`;
- `-Xms4G -Xmx4G` in `jvm-server.options`.

Node 2 also needs `JMX_PORT="7200"` in its `cassandra-env.sh` (`:235`).

Start each with `CASSANDRA_CONF=/local/nX/conf CASSANDRA_LOG_DIR=/local/nX/logs bin/cassandra -p /local/nX/pid`. At least 15 GB free on `/local` is needed.

**Amendment 2026-10-25 (step-0 audit) — B3a, this host.** n1 runs from `$W/cassandra-run24` (the unit clone, `build-test`), n2 from `$W/cassandra-run24-n2` (`ant -Dlocal.repository=$W/m2 jar`). Each node's conf is generated by the harness's `make-node-conf.sh` into `$W/node-rsmtds/nX/conf` from the clone's tag `conf/`, with B3a's lines (`cluster_name: td`, `num_tokens: 1`, tokens −9223372036854775808 / 0, addresses, `seeds: "127.0.0.1:7000"`, data, commitlog, hints, saved_caches and cdc directories under `$W/node-rsmtds/nX/`, `repair_session_space: 1024MiB`) plus `auto_bootstrap: false` (a fresh two-node ring with assigned tokens; nothing to stream). n2's `cassandra-env.sh` has `JMX_PORT="7200"`. The 4 GiB heap is set with `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M` on the start command (the same `-Xms4G -Xmx4G`, `cassandra-env.sh`), not by editing `jvm-server.options`. Start: `CASSANDRA_CONF=… CASSANDRA_LOG_DIR=… nohup bin/cassandra -f`, pid from `$!` (no `setsid` on macOS). Two 4 GiB heaps on 32 GiB RAM. Reason: B3a named CloudLab paths.

**B3b. Knobs.** Set `RepairSessionMaximumTreeDepth` to d ∈ {10, 16, 20} on both nodes over JMX, because every replica reads its own value. Also try 9, which must be rejected. Use this client, saved as `/local/tools/Jmx.java`:
```java
import javax.management.*; import javax.management.remote.*;
public class Jmx { public static void main(String[] a) throws Exception {
  MBeanServerConnection m = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + "/jmxrmi")).getMBeanServerConnection();
  ObjectName ss = new ObjectName("org.apache.cassandra.db:type=StorageService");
  if (a[1].equals("set")) { try { m.setAttribute(ss, new Attribute("RepairSessionMaximumTreeDepth", Integer.parseInt(a[2]))); System.out.println("OK"); } catch (Exception e) { System.out.println("REJECTED " + e); } }
  System.out.println("now " + m.getAttribute(ss, "RepairSessionMaximumTreeDepth"));
  if (a[1].equals("poll")) { ObjectName d = new ObjectName("java.nio:type=BufferPool,name=direct"); long end = System.currentTimeMillis() + Long.parseLong(a[2]) * 1000;
    while (System.currentTimeMillis() < end) { System.out.println(System.currentTimeMillis() + "," + m.getAttribute(d, "MemoryUsed")); Thread.sleep(200); } } } }
```

**Amendment 2026-10-25 (step-0 audit) — B3b, client and read-backs.** `Jmx.java` exactly as written, saved at `$W/tools-rsmtds/Jmx.java` and run in source-file mode (`java Jmx.java 127.0.0.1:<port> …`); local JMX listens on 127.0.0.1 for both nodes (ports 7199, 7200). Each `set` is followed by its `now` line on both nodes; `RepairSessionSpaceInMiB` is also read back on both nodes for each d (`nodetool sjk mx -b org.apache.cassandra.db:type=RepairService -mg -f RepairSessionSpaceInMiB`). Reason: the space term must be shown constant across d.

**B3c. Workload.**
1. `tools/bin/cassandra-stress write n=2500000 cl=ALL no-warmup -schema "replication(factor=2)" -rate threads=64 -node 127.0.0.1`.
2. `nodetool -p 7199 flush` and `nodetool -p 7200 flush`.
3. For each d, run `bin/nodetool -p 7199 repair --full keyspace1 standard1`.

With 2 single-token nodes there are 2 ranges of about 1.25 M partitions each, so ceil(log2) = 21.

Space per range at the validator: 1024 MiB / RF 2 × ratio 0.5 = 256 MiB, which gives estimatedMaxDepth ≈ floor(log2(256 MiB / 100–200 B)) = 20–21. That is ≥ 20, so d binds for 10 and 16. At d = 20 it binds if the estimate is ≥ 20. If the stage-4 run finds that the estimate is below 20, raise `repair_session_space` to 2048MiB.

Each repair takes about 1–3 minutes.

**Amendment 2026-10-25 (step-0 audit) — B3c, terms computed, a wrong fallback, compaction.** (i) Space term computed at the audit (`$W/audit-run24/Depth.java`): Murmur3, 1024 MiB, RF 2, owning ratio 0.45 / 0.5 / 0.55 → **20 / 20 / 20**. It is not below 20, so no raise is made; at d = 20 the entry and the space term are equal (20), so 10 and 16 are the values the entry alone bounds. (ii) **The filed fallback "raise to 2048MiB" must not be used:** `getRepairSessionSpaceInMiB() * 1048576` is int arithmetic (`ValidationManager.java:62`); 2048 MiB overflows to −2^31, `rangeAvailableBytes` becomes 1 (`:71`) and the space term 1 (computed: d = 1), i.e. 2-leaf trees. The largest value that does not overflow is 2047MiB (space term 21). (iii) After the flushes, wait until `nodetool compactionstats` shows 0 pending tasks on both nodes (≤ 600 s), then `nodetool disableautocompaction keyspace1 standard1` on both, so every d validates the same sstables. (iv) Data term: the validation's estimated partitions per range; with P ≈ 2.5 M in the `Created` line, P/2 > 1,048,576 gives `ceil(log2)` = 21 > 20. (v) Bounds: stress 1800 s, each repair 900 s. Reason: the fallback is wrong by the source; compaction between repairs would change the input.

**B3d. Observables and instruments.**
- On n1, the coordinator: `bin/nodetool -p 7199 setlogginglevel org.apache.cassandra.utils.MerkleTree DEBUG`. Then grep `Allocating direct buffer of size` in `/local/n1/logs/debug.log`. These lines are logged per deserialized off-heap tree (`MerkleTree.java:750`).
- Direct `MemoryUsed` on n1, polled every 200 ms.
- On n2, the validator: run `jmap -histo:live $(cat /local/n2/pid) | grep 'MerkleTree\$OnHeapLeaf'` every 3 s during the repair, and record the peak instance count.

A tree that n1 validates locally may not be serialized, so it may never produce an allocation line.

**Amendment 2026-10-25 (step-0 audit) — B3d, what n1 logs, sampling, `Prepared` lines.** (i) The `Allocating direct buffer of size` lines on n1 come from **both** replicas: n2's two trees are deserialized off heap (`MerkleTree.java:707-730`, `:787-791`) and n1's own two trees are moved off heap before they are handled (`Validator.java:295-300` → `MerkleTrees.java:373-377` → `MerkleTree.java:776-785`); each calls `allocate` (`:747-751`). A repair therefore logs exactly **4** lines on n1 (2 ranges × 2 replicas) and none on n2. `debug.log` already takes DEBUG for `org.apache.cassandra` (`conf/logback.xml`); the `setlogginglevel` step is kept. (ii) Heap sampler: `jcmd <pid> GC.class_histogram` (the live histogram that `jmap -histo:live` prints) every **1 s** instead of 3 s, on n2 (and on n1, recorded only), from before the repair until it returns; the reading is the `MerkleTree$OnHeapLeaf` instance count. Reason: a 3 s interval can miss a validation that lasts a few seconds. (iii) Per node and repair, the `Prepared AEService trees of size S` line (`Validator.java:158`, after `init()`) and the `Created N merkle trees … P partitions` line (`ValidationManager.java:85`) are read from the part of `debug.log` written after the repair started (byte offset). (iv) Direct poller as written (n1, 200 ms); baseline = median of the samples taken before the repair starts.

**Amendment 2026-10-27 (after run 1, authorised by the user) — B3d, an event-tied direct-memory instrument on n1.** This amendment follows run 1's readings: in run 1 the cluster tier was Not confirmed because B3b's 200 ms poller saw 2 of the 4 buffers at d = 16 (results file §4.2), and the user (Yang, the advisor) authorised an amendment and a re-run of the whole cluster tier on 2026-10-27. Written knowing all of run 1's readings (see the B3f amendment of the same date for what was known and whether run 1 would pass). **Where the coordinator's tree memory changes, from the source:** only at (a) `MerkleTree.allocate` (`MerkleTree.java:747-754`), which calls `ByteBuffer.allocateDirect(size)` (`:751`) once per tree, for n1's own trees moved off heap (`Validator.java:293-305` → `MerkleTrees.java:373-377` → `MerkleTree.java:776-785`) and for n2's trees deserialized off heap (`:707-730`, `:787-792`); and (b) `MerkleTree$OffHeapNode.release` (`:985-991`) → `FileUtils.clean` (`FileUtils.java:362-380`), reached from `MerkleTree.release` (`:164-168`) through `MerkleTrees.release` (`MerkleTrees.java:148-150`) at `RepairJob.java:355` and `:357`, i.e. only after `MerkleTrees.difference` of the two responses (`:310-318`). So the four buffers coexist only from the fourth allocation to the first release. The length of that interval is the differencing time of two responses, which the source does not bound from below, so no fixed-period sampler is guaranteed to see it; an instrument at (a) and (b) is. **What the pool counts, from the JDK 11 runtime's bytecode** (`javap` on `java.base` and `java.management` of OpenJDK 11.0.32.1): `DirectByteBuffer(int cap)` calls `Bits.reserveMemory(max(1, cap + (pageAligned ? pageSize : 0)), cap)` before it returns (page alignment is off by default, so the reservation is `cap`), and `Bits.tryReserveMemory` adds it to `RESERVED_MEMORY` and 1 to `COUNT`; `clean()` runs `DirectByteBuffer$Deallocator.run` synchronously, which calls `Unsafe.freeMemory` and `Bits.unreserveMemory`; the JMX bean `java.nio:type=BufferPool,name=direct` read by B3b's poller is built in `ManagementFactoryHelper.getBufferPoolMXBeans` from `SharedSecrets.getJavaNioAccess().getDirectBufferPool()`, whose `getMemoryUsed()` returns `Bits.RESERVED_MEMORY`. **Instrument:** an observe-only Byteman rule file `rsmtd.btm` (harness folder), loaded on n1 only with `-javaagent:<clone>/build/lib/jars/byteman-4.0.20.jar=script:rsmtd.btm,boot:<same jar>` in `JVM_EXTRA_OPTS`: rule (A) at the exit of `MerkleTree.allocate`, rule (B) at the entry of `MerkleTree$OffHeapNode.release`. Each prints one line `RSMTD alloc|release ms=<epoch ms> cap=<buffer capacity> mt=<running total> used=<pool MemoryUsed> count=<pool Count> thread=<name>` to n1's stdout (`node.out`). `mt` is a Byteman counter changed atomically by +cap in (A) and −cap in (B) (`incrementCounter`); `used` and `count` read the same pool as the JMX bean at the event: in (A) after the reservation, so `used` includes the new buffer; in (B) before the clean, so it still includes the buffer being released. No rule changes behaviour. B3b's poller is kept as written, because it supplies the baseline ((iv) above); its peak is recorded only. Rule check before the shakedown: `org.jboss.byteman.check.TestScript` against the run clone's classes reports no errors.

**B3e. Procedure.**
1. Start n1, wait for UN, then start n2 and wait until `nodetool status` shows 2 UN.
2. Run the stress write, then flush both nodes.
3. Run `java /local/tools/Jmx.java 127.0.0.1:7199 set 9`. Expect REJECTED and `now 20`.
4. For d in 10 16 20:
   1. `set d` on both 7199 and 7200.
   2. Start the n1 poller (`poll 600 > /local/td-$d-direct.csv &`) and the n2 `jmap` loop.
   3. Run the repair.
   4. Stop the samplers.
   5. Copy out the new `Allocating direct buffer` lines.
5. Repeat d = 16.
6. Stop both nodes with `kill $(cat /local/n1/pid) $(cat /local/n2/pid)`, then check that `pgrep -f CassandraDaemon` is empty.

**Amendment 2026-10-25 (step-0 audit) — B3e, run order.** Pre-checks (no `CassandraDaemon`; ports 7000, 7199, 7200, 9042 free; `127.0.0.2` on `lo0`), start n1 then n2 (UN and `statusbinary running`, ≤ 360 s each), stress, flushes, compaction wait (B3c amendment), `setlogginglevel` on n1, `set 9` on 7199 and read 7200, then labels d10, d16, d20, d16r (the repeat), each: set and read back both nodes, offsets, samplers, repair, stop samplers, extract lines. Then logging back to INFO, stop both nodes (`drain`, `kill`), check, wipe `$W/node-rsmtds`. A small shakedown of the same script (n = 30,000) runs before run 1 and is not judged. Reason: B3e left bounds and the shakedown open.

**Amendment 2026-10-27 (after run 1, authorised by the user) — B3e, the re-run.** Follows run 1's readings (B3d amendment of the same date). The whole cluster tier runs again from its beginning, in the order above, with these changes only: TestScript check of `rsmtd.btm` first; n1 starts with the Byteman agent (B3d amendment), and after n1 is up its `node.out` is checked for the agent (no `TypeException`, `Rule.execute called for` or Byteman exception line); for each label, the `RSMTD` lines written to n1's `node.out` after the label's offsets are taken are extracted as `n1-rsmtd.txt`. Fresh clones (`$W/cassandra-run64`, `build-test`, for n1; `$W/cassandra-run64-n2`, `jar`, for n2), node data under `$W/node-rsmtds2`, logs under `cluster-run2/`. A shakedown of the same script (n = 30,000; not judged) runs first.

**B3f. Predictions.**
- **Allocation lines.** Each line logged on n1 reports exactly 50·(2^d − 1) + 32·2^d bytes: 83 918 for d = 10, 5 373 902 for d = 16, and 85 983 182 for d = 20. There are at least 2 lines per repair, one per range from n2.
- **n2 heap.** The peak `OnHeapLeaf` count on n2 is ≈ 2 × 2^d plus a small constant: about 2 048, 131 072 and 2 097 152.
- **n1 direct memory.** The peak rise in n1 direct memory is ≈ (number of lines) × buffer size: under 1 MiB at d = 10, about 10–21 MiB at d = 16, and about 164–328 MiB at d = 20.
- **Rejection.** 9 is rejected and the depth stays 20.

**Amendment 2026-10-25 (step-0 audit) — B3f, corrected formula and exact values.** (i) **Buffer size, from the source:** the serialized `size` field is the leaf count (written at `MerkleTree.java:686`; `size = 2^depth` at `:146`), read back as `innerNodeCount` (`:714`), and `moveOffHeap` passes the same `size` (`:782`); the buffer is innerNodeCount·(4 + 4 + 32 + 2 + 8) + (innerNodeCount + 1)·32 = **82·2^d + 32** bytes (`:799-802`, `:1160-1163`, `:1451-1457`; Murmur3 maximum token size 8): **84,000 · 5,373,984 · 85,983,264** at d = 10 · 16 · 20. The filed 50·(2^d − 1) + 32·2^d counts the true inner nodes and is 82 bytes lower. (ii) Exactly **4** lines per repair on n1, all of that size. (iii) `Prepared … size` S = 2·2^d on n1 and n2 (2,048 · 131,072 · 2,097,152), `Created 2 merkle trees`. (iv) n2 peak `OnHeapLeaf` count in [2·2^d, 2·2^d + 16]. (v) n1 direct: peak − baseline ≥ 0.95 × 4 × buffer at d = 16 and 20 (≥ 19.5 MiB, ≥ 311.6 MiB), since all four trees are held until the differencing releases them (`RepairJob.java:306-357`); the upper side is open, because internode large-message buffers and other direct users share the pool (A4); at d = 10 (4 × 84,000 B = 0.32 MiB) it is recorded only. (vi) d16r equals d16 in (i)–(iv). (vii) `set 9` → `REJECTED …` and `now 20`. Reason: the formula and the line count are wrong as filed by the source, and the filed upper bounds of (v) cannot hold for the same reason; changed before any reading.

**Amendment 2026-10-27 (after run 1, authorised by the user) — B3f (v), measured at the allocation and release points.** This follows run 1's readings: (v) failed at d = 16 and its repeat because the 200 ms poller sampled on both sides of the interval in which the four buffers coexist (results file §4.1–§4.2). The bound itself is kept; the source does not call for a different one: by the B3d amendment of this date the four buffers are all allocated before the first is released (`RepairJob.java:310-357`), and each adds its capacity to the pool the bound is read on. Only the instrument that supplies the peak changes, and a relation on the tree bytes themselves is added. **(v′)** replaces (v) for the re-run; both parts are required:
- **(v-a) Trees held together (Byteman counter `mt`), at every label.** The label's `RSMTD` lines are exactly 4 `alloc` and 4 `release` lines, each with `cap` = the buffer of (i) (82·2^d + 32). All four `alloc` lines come before the first `release` line, so `mt`'s peak in the label is exactly 4 × buffer above its value at the label's start (336,000 · 21,495,936 · 343,933,056 B at d = 10 · 16 · 20). After the fourth `release`, `mt` is back at its value at the label's start. The `alloc` count equals the label's `Allocating direct buffer` count ((ii)).
- **(v-b) Direct pool rise, the frozen bound, at d = 16 and 20.** Peak − baseline ≥ 0.95 × 4 × buffer: **≥ 20,421,139 B at d = 16** and **≥ 326,736,403 B at d = 20**. Peak = the largest `used` among the label's `RSMTD` lines. This is the pool read at every allocation and release, including the two readings taken while all four buffers are held: the fourth `alloc` and the first `release`. Baseline = the median of the poller's samples before the repair starts, as frozen in the B3d amendment (iv). The upper side stays open (other direct users share the pool, A4). At d = 10 (4 × 84,000 B) it is recorded only.
- The poller's own peak is recorded and not judged.
(i)–(iv), (vi), (vii) are unchanged. **What was known when this was written:** all of run 1's cluster readings. That includes 4 `Allocating` lines per repair of 82·2^d + 32 B; poller rises of 10,748,480 / 10,747,968 B at d = 16 and its repeat (2 buffers) and 383,471,706 B at d = 20 (a sample before the fourth allocation: 3 buffers plus other direct memory); and four-buffer intervals of about 12 ms (d = 16) and 96 ms (d = 20), read from the `Allocating` and `Created … sync tasks` log timestamps. The numbers in (v-a) and (v-b) come from (i) and the frozen 0.95 × 4 rule, not from these readings. **Would run 1 pass:** no. Run 1's raw files have no `RSMTD` lines, so (v′) cannot be evaluated on them, and under the B3g amendment of this date run 1 matches the "instrument silent" row (Invalid for (v′)). If its poller peak is used in place of the event peak, (v-b) fails at d = 16 and its repeat, as in run 1. Run 1's log timeline (four `Allocating` lines before the `Created 0 sync tasks` line) is consistent with (v-a), but it is not the counter.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Buffer sizes equal the formula for each d; leaf counts scale ×64 then ×16 | Claim confirmed at node level |
| Buffer size the same for all d | Depth not governing trees on a real repair (claim wrong) |
| d = 20 sizes match 2^19 or lower | Space term binds; raise `repair_session_space` and rerun (not a refutation) |
| 9 accepted | Floor not enforced |

**Amendment 2026-10-25 (step-0 audit) — B3g, rows added.** Row 1 requires all of (i)–(vii) of the B3f amendment.

| Observation | Meaning |
|---|---|
| Buffer sizes follow 2^d but differ from 82·2^d + 32 by a constant | Not confirmed: the audit's formula is wrong (no refutation of B1) |
| Line count ≠ 4 in a repair | Not confirmed for that observable: the off-heap path differs from the trace |
| S exact but n2 `OnHeapLeaf` peak outside its band | Not confirmed for heap |
| Lines exact but the direct rise below the bound at d = 16 or 20 | Not confirmed for direct memory: trees not held together as traced |
| A read-back ≠ the set value on either node | Invalid for that d |
| P/2 ≤ 1,048,576 (data term ≤ 20) | d = 20 bounded by the data; not a refutation |
| d16r ≠ d16 | Not confirmed (unstable) |
| A repair fails, stress reports errors, or a node is down | Invalid; rerun |
| No n2 sample with tree objects | Heap observable silent; not confirmed for heap |

**Amendment 2026-10-27 (after run 1, authorised by the user) — B3g, rows for (v′).** This follows run 1's readings (B3f amendment of this date). For the re-run, row 1 requires all of (i)–(iv), (vi), (vii) of the B3f amendment of 2026-10-25 and both parts of (v′) of the B3f amendment of 2026-10-27. The row "Lines exact but the direct rise below the bound at d = 16 or 20" is read with (v-b), i.e. the event peak. These rows are added:

| Observation | Meaning |
|---|---|
| (v-a) holds but (v-b) is below its bound at d = 16 or 20 | Not confirmed for direct memory: the four trees were held together, but the pool did not rise by their bytes above the baseline |
| (v-a) fails: fewer than 4 `alloc` lines before the first `release` (`mt` peak < 4 × buffer above the label's start), a `cap` ≠ the buffer, or the `release` count ≠ 4 / `mt` not back at its start | Not confirmed: the trees are not held together, or not released, as traced |
| The agent is not loaded, TestScript reports an error, `node.out` has a Byteman error line, or a label's `alloc` count ≠ its `Allocating` count (instrument silent or faulty) | Invalid for (v′) in that run; no direct-memory verdict from it |
| The poller's peak is below the bound while (v′) holds | Not a failure (recorded; the poller cannot see the interval, B3d amendment of 2026-10-27) |

**B3h. Controls.**
- The same data for every d, with no writes between repairs.
- Full repair (`--full`) so that anti-compaction state does not vary.
- `cl=ALL` writes, so trees match and no streaming adds memory.
- A repeat at d = 16.
- Settings applied to both replicas.

**Amendment 2026-10-25 (step-0 audit) — B3h, controls on this host.** "Applied to both replicas" is shown by the read-backs (B3b amendment); "the same data" by the compaction wait and `disableautocompaction` (B3c amendment) and the `Created … P partitions` lines being equal across labels. The cluster tier has no space-binding control (only the unit tier has one); not added (left for stage 3). Reason: the controls' evidence was not named.

**B4. Risks and cleanup.**
- Unit: the d = 20 tree uses about 150–250 MB of a 1 GiB test heap. Do not add d ≥ 21 builds. Remove `/local/c509/build/test/cassandra` afterwards.
- Cluster: about 3 GB of data in total under `/local/n1` and `/local/n2`. After the runs:
  - run `nodetool -p 7199 setlogginglevel org.apache.cassandra.utils.MerkleTree INFO`;
  - kill both pids, and check that `pgrep -f CassandraDaemon`, `pgrep -f cassandra-stress` and `pgrep jmap` are all empty;
  - `rm -rf /local/n1 /local/n2` (keep the logs if needed).

**Amendment 2026-10-25 (step-0 audit) — B4, this host.** Node data `$W/node-rsmtds/{n1,n2}` (≈ 0.5–1 GB per node at RF 2), wiped before and after; full logs under `$W/logs/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth/`; checks `ps -eo command | grep '[C]assandraDaemon'`, `pgrep -f cassandra-stress`, `pgrep jcmd` empty at the end; the copied test is removed from the run clone after the unit runs. Reason: CloudLab paths.

## C. Sources read

- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/service/StorageService.java
- src/java/org/apache/cassandra/service/StorageServiceMBean.java
- src/java/org/apache/cassandra/repair/ValidationManager.java
- src/java/org/apache/cassandra/repair/ValidationPartitionIterator.java
- src/java/org/apache/cassandra/repair/Validator.java
- src/java/org/apache/cassandra/utils/MerkleTree.java
- src/java/org/apache/cassandra/utils/MerkleTrees.java
- src/java/org/apache/cassandra/dht/Murmur3Partitioner.java
- src/java/org/apache/cassandra/service/ActiveRepairService.java
- conf/cassandra.yaml, conf/cassandra-env.sh, build.xml, NEWS.txt
- https://issues.apache.org/jira/browse/CASSANDRA-14096
- https://issues.apache.org/jira/browse/CASSANDRA-5263

## D. Stage-4 feedback

**2026-10-26 — stage 4 run 1** (Claude Opus 5.5, claude-opus-5-5, on the advisor's machine; results: [`../../stage4-runtime-verification/results/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous.md`](../../stage4-runtime-verification/results/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous.md); uncommitted).

- **Unit: Confirmed — caps** (B2g row 1). Three runs: size = 2^d at d = 10, 14, 18, 20 exactly; heap ×4.00–4.06 per +2 (104 B per leaf); control 4,096; 9 and 0 rejected with the value left at 20; 21 and 30 stored with one warning each.
- **Cluster: Not confirmed — caps (per tree)** (B3g added row "direct rise below the bound at d = 16"). Every size and count matched: on n1 four `Allocating direct buffer` lines per repair of 82·2^d + 32 bytes (84,000 · 5,373,984 · 85,983,264), `Prepared` S and the n2 live `OnHeapLeaf` peak both 2·2^d (2,048 · 131,072 · 2,097,152), repeat at 16 identical, 9 rejected with `now 20`. The direct-pool rise at d = 16 showed 2 of the 4 buffers: the four coexist for 12 ms (log timestamps) and B3b's 200 ms poller sampled on both sides of that window. The frozen bound is not met, so the tier stays Not confirmed. A re-run would need a finer direct-pool instrument and a re-frozen B3b/B3f.
- Audit findings for stage 3: (i) the B3f buffer formula counted the true inner nodes, but the code sizes the buffer with the leaf count (`MerkleTree.java:714`, `:782`, `:799-802`), which gives 82·2^d + 32; (ii) the coordinator's own trees are moved off heap too (`Validator.java:295-300`), so a repair logs 2 × ranges lines, not one per range from the peer; (iii) **the fallback "raise `repair_session_space` to 2048MiB" would collapse every tree to depth 1**: `getRepairSessionSpaceInMiB() * 1048576` is an int product (`ValidationManager.java:62`), which overflows at ≥ 2048 MiB, so `rangeAvailableBytes` = 1 (`:71`) and `estimatedMaxDepthForBytes` returns 1 (computed on the built clone). This is a finding on `repair_session_space` (a value accepted by `DatabaseDescriptor.java:612-615` and `:4091-4100` that silently disables tree resolution), not on this entry; (iv) a set takes effect at the next `createMerkleTrees` call (`ValidationManager.java:76`, `:127`) on that node only, and validations already past it keep their size. No in-flight test was run.
- One runbook defect (B2e: the unit output is in the test log, not the XML), fixed by a dated note; §9a unchanged.

**2026-10-27 — stage 4 cluster re-run ("run 1b")** (Claude Opus 5.5, claude-opus-5-5, on the advisor's machine; **authorised by the user (Yang, the advisor) on 2026-10-27**; at the re-frozen sha256 `7384672a…0ea2`; results §7; uncommitted).
- **Cluster: Confirmed — caps (per tree)** (B3g row 1 with the amended B3f (v′)). The four amendments of 2026-10-27 (B3d, B3e, B3f (v), B3g) follow run 1's readings and were written knowing them. They keep the frozen bound (0.95 × 4 × buffer above the pre-repair poller median) and replace only the instrument that supplies the peak: an observe-only Byteman rule on n1 at `MerkleTree.allocate` and `MerkleTree$OffHeapNode.release` (`MerkleTree.java:747-754`, `:985-991`) records an atomic running total of tree bytes and the JVM direct pool at each event. They add (v-a), the four trees held together. Run 1 would not pass the amended relations (no event lines: "instrument silent → Invalid").
- Readings, fresh clones `cassandra-run64`/`-n2`, shakedown first: every run-1 size and count repeated exactly (4 × 82·2^d + 32 B on n1, S = Lmax = 2·2^d, repeat identical, 9 rejected with `now 20`). At every label, 4 allocations came before the first release, and the running total went 0 → 4 × buffer → 0. Direct-pool rise at the events: 29,786,550 B (d = 16), 470,288,515 B (d = 20), 21,495,936 B (repeat), all ≥ the bound. The four buffers coexisted for 31 ms, 102 ms and 2 ms; the 200 ms poller again saw none of them at d = 16.
- Unit tier unchanged (Confirmed — caps, run 1; not re-run). For stage 3: a bound on a transient holding needs an instrument at the allocation and release points.
