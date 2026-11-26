# max_top_tombstone_partition_count — verification solution (heap: tombstone top-partition holders)  <!-- file: cases/max_top_tombstone_partition_count-track-top_size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the admission check in `TopHolder.track`, **linked**: [`TopPartitionTracker.java:239`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TopPartitionTracker.java#L239) (with its trim loop at [`:246`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TopPartitionTracker.java#L246)) |
| Pinned source | `cassandra-5.0.9` |
| Lead source | config-first |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code (CLI version not shown to the agent), 2026-11-26 |
| Estimate | `positive` — the entry is the capacity of each tombstone `TopHolder` `TreeSet` (one per non-system table, plus one per running validation); admission and trimming keep `top.size() <= N`, and each entry retains a heap copy of a partition key, so heap held by the holder follows `min(N, qualifying partitions)`. The object is small at the default 10 and becomes memory-significant only when N is raised (the int has no upper bound) and many partitions qualify. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `max_top_tombstone_partition_count`, a cassandra.yaml configuration entry
(`Config` field), declared at
[`Config.java:1151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L1151):
`public volatile int max_top_tombstone_partition_count = 10;`. Unit: a count of partitions (entries).
Default 10, a literal in `Config.java`; the key is not present in the shipped `conf/cassandra.yaml`
(grep finds no `max_top`), but the yaml loader maps any public `Config` field, so the key can be added.
No validation anywhere: `DatabaseDescriptor.getMaxTopTombstonePartitionCount()` / `set...` at
`DatabaseDescriptor.java:5092-5100` read/write the field directly. Settable (a) in cassandra.yaml (read at
start, needs restart), (b) at runtime through JMX `org.apache.cassandra.db:type=StorageService`, attribute
`MaxTopTombstonePartitionCount` (`StorageServiceMBean.java:1278-1279`, `StorageService.java:7561-7570`);
no nodetool sub-command. A runtime change takes effect for the next validation's `Collector`
(read at construction) and for the per-table holder at the next merge (repair) or restart.

**A2. What it caps.** Heap. The quantity compared is `top.size()`, the number of `TopPartition` entries in a
`TopHolder.top` `TreeSet` (`TopPartitionTracker.java:199`). Each entry is a `TreeMap.Entry` + `TopPartition`
(`:311-320`) + a `DecoratedKey` made by `key.retainable()` (`:240`, `DecoratedKey.java:202-207`, which clones
the key bytes onto the heap when the buffer is a slice) + its `Token`. Estimated per-entry retained size
(compressed oops): ~40 (tree entry) + 24 (`TopPartition`) + 24 (`BufferDecoratedKey`) + 24 (`LongToken`) +
48 (`HeapByteBuffer`) + 16 (`byte[]` header) ≈ **176 B + key length K**. Partition keys may be up to 64 KiB,
so an entry is between ~0.2 KB and ~64 KB.

Two kinds of holder are bounded by the entry:
- the per-table, long-lived holder `topTombstones`, built when a `ColumnFamilyStore` of a non-system table is
  created (`ColumnFamilyStore.java:570-573` → `TopPartitionTracker.java:88-90`), and replaced at each merge;
- a transient holder inside each `TopPartitionTracker.Collector`, created per validation
  (`ValidationManager.java:117-119` → `TopPartitionTracker.java:173-175`).

**A3. Mechanism.**
1. A full (`--full`), validate (`--validate`) or full-preview repair runs a validation compaction; when
   `top_partitions_enabled` (default true, `Config.java:1154`) and the repair kind is supported
   (`ValidationManager.java:118`, `:165-180`), a `Collector` is built with capacity
   `DatabaseDescriptor.getMaxTopTombstonePartitionCount()` (`TopPartitionTracker.java:173-175`).
2. The validation iterator wraps the merged partitions with `TombstoneCounter`
   (`CompactionIterator.java:157-158`), which counts partition-level deletions, row deletions, cell tombstones
   and range-tombstone markers per partition (`TopPartitionTracker.java:351-385`) and, on partition close,
   calls `collector.trackTombstoneCount(key, count)` (`:388-391` → `:181-184`).
3. `TopHolder.track(key, value)` (`:234-241`): partitions below `min_tracked_partition_tombstone_count`
   (default 5000, `Config.java:1153`) are skipped (`:236`). **The check**
   [`TopPartitionTracker.java:239`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TopPartitionTracker.java#L239):
   `if (top.size() < maxTopPartitionCount || value > currentMinValue)` admits the partition (allocating a
   `TopPartition` with a retained key copy). Then the trim loop
   [`:246-250`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TopPartitionTracker.java#L246-L250)
   `while (top.size() > maxTopPartitionCount) top.pollLast();` evicts the smallest, so after every call
   `top.size() <= N`.
   - Below the limit: every qualifying partition is added (heap grows by one entry).
   - At the limit: a partition whose count is not larger than the current minimum is not allocated at all;
     a larger one is allocated, inserted, and the smallest is evicted (heap stays at N entries; the evicted
     entry becomes garbage).
4. After the validation, `cfs.topPartitions.merge(collector)` (`ValidationManager.java:151-152` →
   `TopPartitionTracker.java:117-134`) builds the new long-lived holder as a clone of the collector's holder
   (`:265`, `:275-278`: `new TreeSet<>(top)` with the collector's `maxTopPartitionCount`) and re-adds old entries
   outside the repaired ranges through `track(TopPartition)` (`:266-270`, `:243-252`), which skips the
   minimum-count filter but still trims to N.
5. At startup the holder is rebuilt from the stored list (`SystemKeyspace.getTopPartitions`,
   `SystemKeyspace.java:1973-2002`) through `track(TopPartition)` with the current N (`:220-232`), so a lowered
   N truncates on restart (exercised by `TopPartitionTrackerTest.java:177-182`).

Bypasses / overshoot:
- During `merge` the old holder (≤ N), the collector holder (≤ N) and the clone (≤ N tree entries sharing the
  collector's `TopPartition` objects) coexist: transient peak ≈ 2N distinct entries + N extra tree nodes per
  table.
- Several validations at once (concurrent repairs, sub-range sessions, up to `concurrent_validations`) each hold
  their own collector of up to N.
- The cap is per table: total ≈ (number of non-system tables) × N × (176 + K).
- `SystemKeyspace.getTopPartitions` reads the whole stored list into an `ArrayList` before trimming
  (`SystemKeyspace.java:1987-1995`); that list is bounded by N at save time, not by the current N.
- JMX/nodetool reads (`ColumnFamilyStore.java:3594-3599` → `TopPartitionTracker.java:293-302`) build a transient
  `LinkedHashMap` of up to N string keys.
- Edge: N ≤ 0 is accepted; `track(TopPartition)` then does `top.last()` on an empty set after `pollLast`
  (`:246-249`) and throws `NoSuchElementException` (at load or merge) — a failure, not a larger footprint.

**A4. Other consumers.** The sibling `max_top_size_partition_count` holders (same `TopPartition` class; kept
empty in this design by leaving `min_tracked_partition_size` at 1MiB with tiny partitions); Merkle trees of the
same validation (`repair_session_space`); the validation compaction's read buffers and chunk cache; memtables;
key cache; everything else on the heap. None is controlled by this entry.

**A5. Evidence beyond the source.**
- `NEWS.txt:418-421` (feature description: top partitions tracked per table during full/validation repairs,
  stored in `system.top_partitions`, exposed via JMX and `nodetool tablestats`).
- `test/unit/org/apache/cassandra/db/TopPartitionTrackerTest.java` (size limit, save/load and truncation to a
  lowered count, `:140-200`).
- `test/distributed/org/apache/cassandra/distributed/test/TopPartitionsTest.java` (2-node in-JVM cluster,
  `min_tracked_partition_tombstone_count: 0`, `setCount` at `:248-254`).

## B. Verification solution

**B1. Claim under test.** After a full repair, the number of `TopPartitionTracker$TopPartition` objects held for a
table's tombstone holder, and the heap they retain, equal `min(N, P_q)` entries × (≈176 B + key length), where N
is `max_top_tombstone_partition_count` and `P_q` the number of partitions with at least
`min_tracked_partition_tombstone_count` tombstones; raising N above `P_q` lets heap grow to `P_q` entries,
and lowering N releases it at the next repair.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Copy the tree to local disk and build there:
```
WORK=/local/scratch/tpt            # any local disk with >= 10 GB free, not shared storage
mkdir -p $WORK && rsync -a /users/jason92/cassandra-5.0.9/ $WORK/src/
cd $WORK/src && ant jar build-test
```
Add the test class below as `$WORK/src/test/unit/org/apache/cassandra/db/TopTombstoneCapHeapTest.java`. The
`testsome` target runs it with `-Xmx4G` and the jamm agent (build.xml `testmacro`), which `ObjectSizes` needs.

```java
package org.apache.cassandra.db;

import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.*;
import org.junit.Test;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.dht.*;
import org.apache.cassandra.metrics.TopPartitionTracker;
import org.apache.cassandra.utils.ObjectSizes;

public class TopTombstoneCapHeapTest extends CQLTester
{
    static final int M = 200_000;      // partitions offered
    static final int K = 512;          // key length in bytes

    static DecoratedKey key(int i)
    {
        byte[] b = new byte[K];
        Arrays.fill(b, (byte) 'x');
        byte[] d = String.format("%010d", i).getBytes();
        System.arraycopy(d, 0, b, 0, d.length);
        return Murmur3Partitioner.instance.decorateKey(ByteBuffer.wrap(b));
    }

    static TopPartitionTracker.TopHolder collectorHolder(TopPartitionTracker.Collector c) throws Exception
    {
        Field f = TopPartitionTracker.Collector.class.getDeclaredField("tombstones");
        f.setAccessible(true);
        return (TopPartitionTracker.TopHolder) f.get(c);
    }

    void run(int n, boolean increasing) throws Exception
    {
        DatabaseDescriptor.setMaxTopTombstonePartitionCount(n);
        TopPartitionTracker tpt = new TopPartitionTracker(getCurrentColumnFamilyStore().metadata());
        Range<Token> full = new Range<>(new Murmur3Partitioner.LongToken(0), new Murmur3Partitioner.LongToken(0));
        TopPartitionTracker.Collector c = new TopPartitionTracker.Collector(Collections.singleton(full));
        for (int i = 0; i < M; i++)
            c.trackTombstoneCount(key(i), increasing ? i + 1L : (long) (M - i));
        TopPartitionTracker.TopHolder h = collectorHolder(c);
        long cSize = h.top.size(), cBytes = ObjectSizes.measureDeep(h.top);
        tpt.merge(c);
        long tSize = tpt.topTombstones().top.size(), tBytes = ObjectSizes.measureDeep(tpt.topTombstones().top);
        System.out.printf("RESULT N=%d order=%s collectorSize=%d collectorBytes=%d trackerSize=%d trackerBytes=%d%n",
                          n, increasing ? "inc" : "dec", cSize, cBytes, tSize, tBytes);
        tpt.close();
    }

    @Test
    public void sweep() throws Exception
    {
        createTable("create table %s (pk blob primary key, x int)");
        DatabaseDescriptor.setMinTrackedPartitionTombstoneCount(0);
        for (int n : new int[]{ 10, 1_000, 10_000, 100_000, Integer.MAX_VALUE })
            for (boolean inc : new boolean[]{ true, false })
                run(n, inc);
    }
}
```

**B2b. Knobs.** `max_top_tombstone_partition_count` via `DatabaseDescriptor.setMaxTopTombstonePartitionCount`
(same field as the yaml key): 10 (default), 1,000, 10,000, 100,000 (all < M, so the cap binds), and
`Integer.MAX_VALUE` (cap never binds: positive control). `min_tracked_partition_tombstone_count` = 0 so the
threshold filter at `:236` never removes a partition.

**B2c. Workload.** M = 200,000 distinct keys of K = 512 bytes offered to one `Collector`, each with a distinct
tombstone count. Two orders: increasing counts (every new key beats the minimum, so every offer allocates and,
once full, evicts: worst-case churn through `:239` and `:246`), and decreasing counts (once full, every later
offer is rejected at `:239`). M > every capped N, so the limit is reached after N offers and passed by
M − N = 199,990 … 100,000 offers.

**B2d. Observables and instruments.** `TopHolder.top.size()` of the collector (via reflection) and of the
tracker after merge; `ObjectSizes.measureDeep(top)` (jamm) for retained bytes. Printed as one `RESULT` line per
run. Not observable here: the transient peak during `merge`, and GC timing (not needed; sizes are reachability
based).

**B2e. Procedure.**
1. B2a build; add the class.
2. `cd $WORK/src && ant testsome -Dtest.name=org.apache.cassandra.db.TopTombstoneCapHeapTest 2>&1 | tee $WORK/unit-heap.log`
3. `grep RESULT $WORK/unit-heap.log` (also under `build/test/output/` / `build/test/logs/`).
4. Fill the table in B2f.

**B2f. Predictions.** Per-entry retained ≈ 176 + 512 = ~690 B (allow 600–800 B).

| N | collectorSize = trackerSize | collectorBytes ≈ trackerBytes |
|---|---|---|
| 10 | 10 | ~7 KB (+ small fixed TreeMap overhead) |
| 1,000 | 1,000 | ~0.69 MB |
| 10,000 | 10,000 | ~6.9 MB |
| 100,000 | 100,000 | ~69 MB |
| `Integer.MAX_VALUE` (control) | 200,000 | ~138 MB |

Same sizes for both orders. Bytes scale linearly with size (bytes/size constant within ±10% across rows).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| size = min(N, 200,000) and bytes ∝ size in every row, control = 200,000 | claim confirmed at unit level |
| size > N for any capped N | claim refuted: the check does not bound the holder |
| capped rows show size = N but bytes not ∝ size (e.g. same bytes at N = 1,000 and 100,000) | entries do not retain what was estimated; recompute per-entry size before cluster tier |
| control stays at a value below 200,000 | another filter (threshold, equal keys) is removing partitions; workload invalid |
| tracker size ≠ collector size | merge path differs from trace (A3 step 4); investigate |

**B2h. Controls.** The `Integer.MAX_VALUE` run shows the same workload grows the holder when the cap does not
bind. Threshold set to 0 and keys distinct, so only the count limit can limit size. Two offer orders exercise
both branches of the check. Each run uses a new tracker and collector, so no state carries over.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, JDK 11, two Cassandra nodes from the B2a build on loopback
addresses 127.0.0.1 and 127.0.0.2 (repair needs a second replica). `cd $WORK/src && ant jar` (already done).
Per node X ∈ {1, 2}: `cp -r $WORK/src/conf $WORK/n$X/conf`, then in `$WORK/n$X/conf/cassandra.yaml`:
```
cluster_name: 'tpt'
listen_address: 127.0.0.X
rpc_address: 127.0.0.X
seed_provider: ... seeds: "127.0.0.1:7000"
data_file_directories: [ $WORK/nX/data ]
commitlog_directory: $WORK/nX/commitlog
saved_caches_directory: $WORK/nX/saved_caches
hints_directory: $WORK/nX/hints
cdc_raw_directory: $WORK/nX/cdc_raw
min_tracked_partition_tombstone_count: 1
max_top_tombstone_partition_count: 1000       # initial value, checks the yaml path
```
(write `$WORK` expanded). In `$WORK/n2/conf/cassandra-env.sh` set `JMX_PORT="7299"` (node 1 keeps 7199).
Start each node:
```
CASSANDRA_CONF=$WORK/nX/conf CASSANDRA_LOG_DIR=$WORK/nX/logs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M \
  $WORK/src/bin/cassandra -p $WORK/nX/pid
```
(node 2 after node 1 is `UN` in `$WORK/src/bin/nodetool -p 7199 status`).

**B3b. Knobs.** `max_top_tombstone_partition_count` on both nodes: 1,000 from yaml at start (yaml path), then
via JMX 10 (default), 10,000, 100,000, 1,000,000 (> P: control, cap does not bind), then back to 10
(release). JMX set on each node:
```
$WORK/src/bin/nodetool -p 7199 sjk mx -b org.apache.cassandra.db:type=StorageService -f MaxTopTombstonePartitionCount -ms -v <N>
$WORK/src/bin/nodetool -p 7199 sjk mx -b org.apache.cassandra.db:type=StorageService -f MaxTopTombstonePartitionCount -mg
```
(same with `-p 7299`). If the bundled `sjk` rejects these flags, use jmxterm:
`java -jar jmxterm-1.0.4-uber.jar -l localhost:7199 -n` → `set -b org.apache.cassandra.db:type=StorageService MaxTopTombstonePartitionCount <N>`.

**B3c. Workload.** P = 200,000 partitions, each with one partition-level tombstone (counted once at
`TopPartitionTracker.java:376-377`, so every partition has count 1 ≥ the threshold 1), key length K = 1,000:
```
$WORK/src/bin/cqlsh 127.0.0.1 -e "CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':2}; CREATE TABLE ks.t (pk text, ck int, v int, PRIMARY KEY (pk, ck));"
python3 -c '
print("CONSISTENCY ALL;")
for i in range(200000):
    print("DELETE FROM ks.t WHERE pk=%s;" % repr("%010d" % i + "x"*990))
' > $WORK/deletes.cql
$WORK/src/bin/cqlsh 127.0.0.1 -f $WORK/deletes.cql > $WORK/load.log 2>&1
$WORK/src/bin/nodetool -p 7199 flush ks; $WORK/src/bin/nodetool -p 7299 flush ks
```
Disk: ~200 MB sstables + commit log per node before compression, well under 2 GB. Tombstones are not purged
(default `gc_grace_seconds` 10 days). Each node replicates all 200,000 partitions, so P = 200,000 on both.
With all counts equal to 1, once a holder is full no further partition is admitted at `:239`; the size is
exactly min(N, P). Per entry ≈ 176 + ~1,000 ≈ 1.2 KB. Duration: load a few minutes, each repair minutes.

**B3d. Observables and instruments.**
- Primary operand: live instance count and shallow bytes of `org.apache.cassandra.metrics.TopPartitionTracker$TopPartition`
  from `jcmd <pid> GC.class_histogram` (forces a full GC; live objects only). The size holder stays empty
  (partitions ≈ 1 KB < `min_tracked_partition_size` 1MiB), so all such instances belong to tombstone holders.
- Actual heap: `jcmd <pid> GC.heap_info` taken right after the histogram (post-full-GC used heap), delta
  against a baseline taken after the load and flush, before the first repair.
- Cross-check for N ≤ 10,000: `nodetool -p 7199 tablestats -F json ks.t` and count the entries of
  `top_tombstone_partitions` (`TableStatsHolder.java:174`).
- Not directly observable: the transient peak during `merge`; heap noise from other consumers (~±20 MB), so
  heap deltas below ~20 MB (N ≤ 10,000) are judged by instance count only.

**B3e. Procedure.**
1. B3a setup; start both nodes; check `nodetool -p 7199 status` shows two `UN`.
2. Verify yaml value: `nodetool -p 7199 sjk mx ... -mg` returns 1000 on both nodes.
3. B3c schema + load + flush.
4. Baseline on each node: `jcmd $(cat $WORK/nX/pid) GC.class_histogram | grep 'TopPartitionTracker\$TopPartition' ; jcmd $(cat $WORK/nX/pid) GC.heap_info` → save as `base-nX.txt`.
5. `nodetool -p 7199 repair --full ks t` (blocks until done). Record histogram + heap_info on both nodes (`N1000-nX.txt`).
6. For N in 10, 10000, 100000, 1000000, 10: set N on both nodes (B3b), confirm with `-mg`, run step 5, record `N<N>-nX.txt`.
7. Shutdown and B4 cleanup.

**B3f. Predictions.** Per node, after the repair of each step:

| N | `TopPartition` live instances | post-GC heap delta vs baseline |
|---|---|---|
| 1,000 (yaml) | 1,000 | ~1.2 MB (below noise) |
| 10 | 10 | ~0 |
| 10,000 | 10,000 | ~12 MB (below/near noise) |
| 100,000 | 100,000 | ~120 MB (±30%) |
| 1,000,000 (control) | 200,000 (= P) | ~240 MB (±30%) |
| 10 (again) | 10 | back to ~0 (±20 MB) |

Relation: instances = min(N, P) on both nodes; the heap delta of N = 100,000 is about half the control's.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| instances = min(N, P) at every step and heap delta follows (≈ 120 MB at 100k, ≈ 240 MB at control, ≈ 0 after returning to 10) | claim confirmed: the entry caps the holders' heap |
| instances > N at any capped step (after the full GC of the histogram) | claim refuted |
| instances = min(N, P) but heap delta at 100k ≈ control or ≈ 0 | holder count is capped but heap does not follow it (per-entry size wrong, or other consumers dominate); not confirmed |
| control stays below 200,000 | not all partitions reached the collector (repair kind unsupported, threshold, load incomplete); workload invalid, recheck B3c |
| instances stay at the old value after a JMX change + repair | the JMX path does not reach the collector or the repair did not run a validation (check logs for `Validation`) |
| return to 10 leaves the heap high | the old holder is retained elsewhere (leak); refutes "releases at next repair" |

**B3h. Controls.** The N = 1,000,000 step shows the same data moves heap when the cap does not bind. The
return-to-10 step shows the effect is reversible and tied to N, not to time or data growth. The histogram's
full GC removes garbage (evicted entries) from the reading. The size holder is kept empty by the 1MiB
threshold, so `TopPartition` instances are attributable to tombstone holders. Both nodes are read, and both hold
all data (RF=2), so they should agree.

**B4. Risks and cleanup.**
- Everything under `$WORK` on local disk; nothing in `/users/jason92/cassandra-5.0.9` is modified.
- Disk: < 2 GB per node; check `df $WORK` before loading.
- Stop: `kill $(cat $WORK/n1/pid) $(cat $WORK/n2/pid)`; wait; `pgrep -f CassandraDaemon` must print nothing
  started by this run (kill -9 the remaining PIDs from the pid files if needed). The unit tier's JUnit JVM exits
  with Ant; check `pgrep -f junit` is empty.
- Remove data: `rm -rf $WORK/n1 $WORK/n2 $WORK/deletes.cql` (keep logs/readings if wanted), and `$WORK/src`
  when done.
- Ports 7000/9042 on 127.0.0.1-2 and JMX 7199/7299 must be free before starting; another Cassandra on the host
  would collide.

## C. Sources read

- src/java/org/apache/cassandra/config/Config.java (1140-1160, 669-673)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (5070-5120, 898-901, 2513-2516, 2827-2830)
- src/java/org/apache/cassandra/metrics/TopPartitionTracker.java (whole file)
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (560-575, 3575-3607, 251)
- src/java/org/apache/cassandra/db/SystemKeyspace.java (170, 425-440, 1955-2003)
- src/java/org/apache/cassandra/db/DecoratedKey.java (202-207)
- src/java/org/apache/cassandra/repair/ValidationManager.java (105-180)
- src/java/org/apache/cassandra/repair/Validator.java (110-125, 180-195)
- src/java/org/apache/cassandra/db/compaction/CompactionIterator.java (150-162)
- src/java/org/apache/cassandra/db/repair/CassandraValidationIterator.java (grep hits 109-111, 177, 224)
- src/java/org/apache/cassandra/service/StorageService.java (7540-7580)
- src/java/org/apache/cassandra/service/StorageServiceMBean.java (1278-1279)
- src/java/org/apache/cassandra/tools/nodetool/stats/TableStatsHolder.java (90-125, 174, 392-397)
- src/java/org/apache/cassandra/tools/nodetool/stats/TableStatsPrinter.java (100, 159-164)
- src/java/org/apache/cassandra/utils/ObjectSizes.java (225-255)
- src/java/org/apache/cassandra/concurrent/ScheduledThreadPoolExecutorPlus.java (92-100)
- src/java/org/apache/cassandra/repair/RepairSession.java (307)
- test/unit/org/apache/cassandra/db/TopPartitionTrackerTest.java (1-80, 140-200, 311-314)
- test/distributed/org/apache/cassandra/distributed/test/TopPartitionsTest.java (75-140, 240-275)
- conf/cassandra.yaml (grep: no `max_top`/`min_tracked`; ports, directories), conf/cassandra-env.sh (228-238)
- build.xml (jamm agent, `-Xmx${maxMemory}`, `testsome`)
- NEWS.txt (410-425)

## D. Stage-4 feedback

none yet

## Config-first: places found

Every place the value of `max_top_tombstone_partition_count` flows to (declaration
[`Config.java:1151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L1151)):

1. `DatabaseDescriptor.java:5092-5100` — getter/setter, no validation (any int accepted). Restricts nothing itself.
2. `StorageService.java:7561-7570` (`StorageServiceMBean.java:1278-1279`) — JMX attribute `MaxTopTombstonePartitionCount`; runtime switch of the limit.
3. `TopPartitionTracker.java:173-175` — per-validation `Collector` tombstone `TopHolder` capacity (transient heap, one per running full/validate repair validation per table). **Case file: this file.**
4. `TopPartitionTracker.java:88-90` (via `ColumnFamilyStore.java:570-573`) — per-table long-lived tombstone `TopHolder` capacity, applied when loading the stored list at table creation/startup (heap for the table's lifetime). **This file.**
5. `TopPartitionTracker.java:239` and `:246-250` — the admission check and the trim loop that enforce `top.size() <= N` for both holders (heap). **This file (Entry pointer).**
6. `TopPartitionTracker.java:263-278` — `merge`/`cloneForMerging` carry the collector's N into the new long-lived holder; existing out-of-range entries re-added but trimmed to N (heap).
7. `TopPartitionTracker.java:109-112` → `SystemKeyspace.java:1961-1970` — the hourly save writes the ≤ N tuples as one frozen list cell in `system.top_partitions` (disk; commit log + sstable). **Case file: `max_top_tombstone_partition_count-saveTopPartitions-top--autonomous.md`.**
8. `SystemKeyspace.java:1987-1995` — on load, the stored list (≤ N at save time) is read whole into an `ArrayList` before trimming to the current N (transient heap).
9. `TopPartitionTracker.java:293-302` via `ColumnFamilyStore.java:3594-3599` and `TableStatsHolder.java:395` — JMX / `nodetool tablestats` builds a `LinkedHashMap` of ≤ N keys per call (transient heap, client output size).
