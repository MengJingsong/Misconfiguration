# max_top_size_partition_count — verification solution  <!-- file: cases/max_top_size_partition_count-TopHolder.track-top.size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the admission check in `TopHolder.track(DecoratedKey, long)`, **linked**: [`TopPartitionTracker.java:239`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TopPartitionTracker.java#L239) (with its eviction loop [`TopPartitionTracker.java:246`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TopPartitionTracker.java#L246)) |
| Pinned source | `cassandra-5.0.9` |
| Lead source | config-first |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code (CLI version not exposed to the agent), 2026-11-26 |
| Estimate | `positive`. The entry is the hard upper bound on the number of entries in every per-table "top partitions by size" set (the per-validation `Collector` and the long-lived per-table holder); each entry pins a heap copy of a partition key, so the heap these sets hold is at most N × (key length + ~180 B) per set. It is a small consumer at the default N = 10, but the bound is real and scales linearly with the entry. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `max_top_size_partition_count`, a cassandra.yaml entry (a `Config` field),
declared at [`Config.java:1150`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L1150)
as `public volatile int max_top_size_partition_count = 10;`. Unit: a count of partitions (entries).
Default 10, a literal; nothing derives it and `DatabaseDescriptor` does not validate it (no lower or
upper bound check; getter/setter only, `DatabaseDescriptor.java:5082-5090`). The key is not present in
the shipped `conf/cassandra.yaml`; it is set by adding the line `max_top_size_partition_count: <int>`
(read at startup). It is also settable at runtime through JMX: attribute `MaxTopSizePartitionCount` on
MBean `org.apache.cassandra.db:type=StorageService` (`StorageServiceMBean.java:1276-1277`,
`StorageService.java:7549-7558`); there is no nodetool setter. A runtime change has no immediate effect
on the long-lived set: it is read when a new `Collector` is built (at the start of each eligible repair
validation) and when a table's tracker is built (table creation or node startup); see A3.

**A2. What it caps.** Heap. The quantity compared is `top.size()`, the number of `TopPartition`
entries in a `TopHolder`'s `TreeSet` (`TopPartitionTracker.java:199`, `:239`, `:246`). Each entry is a
`TopPartition` (key + long) whose key is `key.retainable()` (`:240`), i.e. a key whose `ByteBuffer` is
cloned to an exact-size heap array when it is a slice of a larger buffer
(`DecoratedKey.java:202-207`, `ByteBufferUtil.java:715-718`). Per entry on a 64-bit JVM with compressed
oops: TreeMap.Entry ~40 B + TopPartition 24 B + BufferDecoratedKey 24 B + LongToken 24 B +
HeapByteBuffer ~48 B + byte[] (16 B + key length) ≈ **key length + ~176 B**. Partition keys may be up to
65,535 bytes, so a set of N entries holds at most about N × 64 KiB.

**A3. Mechanism.**

1. Startup / table creation: every non-system table's `ColumnFamilyStore` builds a
   `TopPartitionTracker` (`ColumnFamilyStore.java:570-573`). Its constructor builds the long-lived size
   holder with `DatabaseDescriptor.getMaxTopSizePartitionCount()` and the stored list from
   `system.top_partitions` (`TopPartitionTracker.java:85-87`); each stored entry goes through
   `track(TopPartition)` (`:230-231`) and so through the eviction loop.
2. A full repair, or a preview/validate repair (`isTopPartitionSupported`,
   `ValidationManager.java:165-178`), with `top_partitions_enabled: true` builds a fresh
   `TopPartitionTracker.Collector(validator.desc.ranges)` (`ValidationManager.java:117-119`), whose size
   holder is created with the current N (`TopPartitionTracker.java:176-178`).
3. For every partition validated, `Validator.add` calls
   `topPartitionCollector.trackPartitionSize(key, rowHash.size)` (`Validator.java:188-192`;
   `rowHash.size` = bytes fed to the digest, `Validator.java:207-216`), which calls
   `TopHolder.track(key, value)` (`TopPartitionTracker.java:186-188`).
4. **The check**: [`TopPartitionTracker.java:236-240`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TopPartitionTracker.java#L236-L240).
   Values below `min_tracked_partition_size` (default 1 MiB, `Config.java:1152`) are dropped (`:236`).
   Then [`if (top.size() < maxTopPartitionCount || value > currentMinValue)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TopPartitionTracker.java#L239):
   - true → a new `TopPartition` with a retained key copy is added (`:240`, `:245`), then
     [`while (top.size() > maxTopPartitionCount)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TopPartitionTracker.java#L246)
     evicts the smallest (`pollLast`, `:248`) until the size is back to N;
   - false → nothing is allocated; the partition is not tracked.
   After every `track` call the set holds at most N entries; inside the call it briefly holds N + 1.
5. When the validation ends (also on failure, `finally`), `cfs.topPartitions.merge(collector)`
   (`ValidationManager.java:151-152`) replaces the long-lived holder by CAS
   (`TopPartitionTracker.java:117-125`) with `holder.cloneForMerging(...)` of the collector's holder
   (`:263-265`, `:275-278`), which keeps the **collector's** N, and re-adds old entries outside the
   validated ranges through `track(TopPartition)` (`:266-271`), i.e. through the eviction loop. So a
   runtime change of N reaches the long-lived set at the next eligible validation.

Bypasses and overshoots:
- Transient: during a merge the old holder, the collector and the new clone coexist (≤ 3N entries,
  sharing the same key objects); with several concurrent validations on one table each has its own
  collector (≤ N each).
- `top` is a `public final NavigableSet` (`:199`); no production code adds to it directly.
- The stored list is read whole into an `ArrayList` before trimming (`SystemKeyspace.java:1987-1995`),
  so at startup after N was lowered, the previous (larger) list is on heap transiently.
- `currentMinValue` can drift below the true minimum (`:249-251`, when the just-added entry is the one
  evicted on the merge/load path); this only causes extra add-then-evict work, not extra retained entries.
- Edge, not a knob value to use: with N ≤ 0, any `track(TopPartition)` on the merge or load path adds
  one entry, `pollLast` empties the set and `top.last()` (`:249`) throws `NoSuchElementException`
  (e.g. at table open when `system.top_partitions` holds a stored list).

**A4. Other consumers.** Outside this entry's control, on the same heap: the sibling tombstone holder
(`max_top_tombstone_partition_count`, `TopPartitionTracker.java:88-90`, `:173-175`); the Merkle trees of
the same validation (bounded by `repair_session_space`, far larger); the `LinkedHashMap` of hex-string
keys built per JMX/nodetool tablestats call (`TopPartitionTracker.java:293-302`,
`ColumnFamilyStore.java:3578-3583`, `TableStatsHolder.java:392`), bounded by the same set's size but
about 2 × key length per entry; memtables, key cache, chunk cache and all other node heap.

**A5. Evidence beyond the source.**
- `NEWS.txt:418-421` (feature note: top partitions tracked per table during full/validation repair,
  stored in `system.top_partitions`, exposed via JMX and nodetool tablestats).
- `test/unit/org/apache/cassandra/db/TopPartitionTrackerTest.java:85-107` (`testCountLimit`: N = 5, ten
  candidates, set size stays 5) and `:52-81` (`testSizeLimit`).
- `test/distributed/org/apache/cassandra/distributed/test/TopPartitionsTest.java:251-257` (sets the count
  through `DatabaseDescriptor`).

## B. Verification solution

**B1. Claim under test.** After an eligible repair validation, the number of tracked "top by size"
entries for a table, and the heap they retain, equal min(N, P) entries and ≈ min(N, P) × (key length +
~176 B), where N = `max_top_size_partition_count` and P = the number of the table's partitions at or
above `min_tracked_partition_size`; the set never exceeds N, however many partitions are validated.
The claim is wrong if the set holds more than N entries, or if its retained heap grows with P while N
is fixed below P.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11 (`export JAVA_HOME=<jdk11>`; `java -version` shows 11),
Ant. Work on local disk: `export W=/local/<user>/tpsize` (any non-shared local directory with ≥ 5 GiB
free). Copy the tree: `rsync -a /users/jason92/cassandra-5.0.9/ $W/src/` (never build in the shared
copy). Add the test file below as
`$W/src/test/unit/org/apache/cassandra/db/TopSizeCapProbeTest.java`. The unit-test JVM is the one
`build.xml` forks for `testsome` (`maxmemory="1024m"`, jamm agent attached, `build.xml:1153-1159`),
so heap is 1 GiB and `ObjectSizes.measureDeep` works.

```java
package org.apache.cassandra.db;

import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.Collection;
import java.util.Collections;
import java.util.Random;

import org.junit.Test;

import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.dht.IPartitioner;
import org.apache.cassandra.dht.Range;
import org.apache.cassandra.dht.Token;
import org.apache.cassandra.metrics.TopPartitionTracker;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.utils.ObjectSizes;

public class TopSizeCapProbeTest extends CQLTester
{
    static final int M = 40_000;          // candidate partitions offered per run
    static final int KEY_BYTES = 2_048;   // partition key length

    @Test
    public void probe() throws Exception
    {
        DatabaseDescriptor.setMinTrackedPartitionSizeInBytes(new DataStorageSpec.LongBytesBound("0B"));
        for (int n : new int[]{ 10, 100, 1_000, 10_000, 100_000 })
            runOne("RUN", n);
        // threshold control: every value (< 1.001e9) is below 1 GiB, so nothing may be admitted
        DatabaseDescriptor.setMinTrackedPartitionSizeInBytes(new DataStorageSpec.LongBytesBound("1GiB"));
        runOne("CONTROL-THRESHOLD", 100_000);
    }

    private void runOne(String label, int n) throws Exception
    {
        createTable("CREATE TABLE %s (k blob PRIMARY KEY, v int)");
        TableMetadata md = getCurrentColumnFamilyStore().metadata();
        IPartitioner p = md.partitioner;
        DatabaseDescriptor.setMaxTopSizePartitionCount(n);
        Collection<Range<Token>> full = Collections.singleton(new Range<>(p.getMinimumToken(), p.getMinimumToken()));
        TopPartitionTracker tpt = new TopPartitionTracker(md);
        TopPartitionTracker.Collector c = new TopPartitionTracker.Collector(full);
        Field f = TopPartitionTracker.Collector.class.getDeclaredField("sizes");
        f.setAccessible(true);
        TopPartitionTracker.TopHolder cs = (TopPartitionTracker.TopHolder) f.get(c);

        Random r = new Random(42);
        int maxSeen = 0;
        for (int i = 0; i < M; i++)
        {
            byte[] b = new byte[KEY_BYTES];
            r.nextBytes(b);
            ByteBuffer.wrap(b).putInt(0, i);                       // unique keys
            c.trackPartitionSize(p.decorateKey(ByteBuffer.wrap(b)), 1_000_000L + r.nextInt(1_000_000_000));
            maxSeen = Math.max(maxSeen, cs.top.size());            // operand after every check
        }
        long collectorBytes = ObjectSizes.measureDeep(cs.top);
        tpt.merge(c);
        int merged = tpt.topSizes().top.size();
        long mergedBytes = ObjectSizes.measureDeep(tpt.topSizes().top);
        System.out.printf("PROBE label=%s n=%d m=%d keyBytes=%d collectorMax=%d collectorFinal=%d collectorDeepBytes=%d merged=%d mergedDeepBytes=%d%n",
                          label, n, M, KEY_BYTES, maxSeen, cs.top.size(), collectorBytes, merged, mergedBytes);
        tpt.close();
    }
}
```

**B2b. Knobs.** `max_top_size_partition_count` set through `DatabaseDescriptor.setMaxTopSizePartitionCount`
(the same field the yaml entry fills) to 10 (default), 100, 1,000, 10,000 (four decades below M) and
100,000 (> M: the cap cannot bind; positive control that the workload can fill the set to M).
`min_tracked_partition_size` is held at `0B` so the threshold does not mask the count cap, then set to
`1GiB` for the threshold control.

**B2c. Workload.** M = 40,000 distinct 2,048-byte keys, each offered once with a random size value in
[1,000,000, 1,000,999,999]. For every N < 40,000 the operand reaches N after the first N offers and
then the check runs 40,000 − N more times at the limit. Retained heap at N ≥ M: 40,000 × ~2,224 B ≈
89 MB, within the 1 GiB test heap.

**B2d. Observables and instruments.** `collectorMax` (largest `top.size()` seen after any `track` call;
the check's operand), `collectorFinal`, `merged` (long-lived holder size after `merge`), and
`collectorDeepBytes` / `mergedDeepBytes` (`ObjectSizes.measureDeep`, jamm, retained heap of the set).
Read from the `PROBE` lines in `$W/src/build/test/output/TEST-org.apache.cassandra.db.TopSizeCapProbeTest.xml`
(`<system-out>`). Not observable: the transient N + 1 inside a single `track` call (sampled only between
calls).

**B2e. Procedure.**
1. `cd $W/src && ant jar` (build) — log to `$W/build.log`.
2. `ant testsome -Dtest.name=org.apache.cassandra.db.TopSizeCapProbeTest > $W/unit.log 2>&1`
3. `grep -o 'PROBE[^<]*' $W/src/build/test/output/TEST-org.apache.cassandra.db.TopSizeCapProbeTest.xml`
4. `pgrep -f TopSizeCapProbeTest` returns nothing (the forked JVM has exited).

**B2f. Predictions.** Per-entry deep size e ≈ 2,224 B (± 10 %).

| label | N | collectorMax = collectorFinal = merged | mergedDeepBytes (≈ count × e) |
|---|---|---|---|
| RUN | 10 | 10 | ≈ 22 KB |
| RUN | 100 | 100 | ≈ 222 KB |
| RUN | 1,000 | 1,000 | ≈ 2.2 MB |
| RUN | 10,000 | 10,000 | ≈ 22 MB |
| RUN | 100,000 | 40,000 (= M) | ≈ 89 MB |
| CONTROL-THRESHOLD | 100,000 | 0 | < 1 KB |

`collectorDeepBytes` ≈ `mergedDeepBytes` (the merged clone holds the same entries). Bytes per entry
(mergedDeepBytes / merged) are constant across N, between 2,100 and 2,450.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| count = min(N, 40,000) in every RUN row and bytes ∝ count | claim holds: N caps the set and its heap |
| any `collectorMax` or `merged` > N | claim wrong: the count cap is not enforced |
| count = 40,000 for N < 40,000 | claim wrong: the check does not bind |
| bytes per entry far above ~2.2 KB, or growing with M at fixed N | something else is retained per offer; the claim about heap is wrong |
| N = 100,000 row < 40,000 | workload did not reach the set; the run cannot confirm (fix the generator) |
| CONTROL-THRESHOLD > 0 | the threshold is not applied; the test setup is wrong |

**B2h. Controls.** N = 100,000 > M shows the same workload fills the set to M when the cap does not
bind (positive control). The threshold control shows entries are admitted only through `track`. A new
table per run gives a fresh tracker, so no state carries over between N values (each new tracker loads
an empty stored list, since nothing calls `save`).

### B3. Cluster tier

**B3a. Environment and build.** One Linux host (≥ 8 GiB RAM, ≥ 10 GiB free local disk at `$W`),
JDK 11, Ant; two Cassandra instances on 127.0.0.1 and 127.0.0.2 (two hosts also work: use their
addresses and drop the JMX-port edit). Build once: `cd $W/src && ant jar stress-build`. Make two node
copies: `rsync -a $W/src/ $W/n1/ && rsync -a $W/src/ $W/n2/`. In each `$W/nK/conf/cassandra.yaml` set:
`cluster_name: 'tpsize'`, `num_tokens: 16`, seeds `"127.0.0.1:7000"`, `listen_address` and
`rpc_address` = 127.0.0.K, `min_tracked_partition_size: 0B`, `key_cache_size: 0MiB`,
`top_partitions_enabled: true`, `max_top_size_partition_count: <N>`. Data, commit log, hints and logs
stay under `$W/nK` (defaults are relative to the node copy). In `$W/n2/conf/cassandra-env.sh` change
`JMX_PORT="7199"` to `JMX_PORT="7299"`. Heap: `export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` before each
start.

**B3b. Knobs.** `max_top_size_partition_count` in both nodes' yaml, values 10 (default), 10,000, 50,000
(half of P), 1,000,000 (> P, positive control), each applied by restarting both nodes. Threshold control:
N = 1,000,000 with `min_tracked_partition_size` back to its default `1MiB` (every partition here is
~2.1 KB, so nothing qualifies).

**B3c. Workload.** Keyspace `tp` RF 2, table `big_keys (k blob PRIMARY KEY, v blob)` with compression
off, P = 100,000 partitions, 2,048-byte keys, 64-byte values, written once with cassandra-stress at
CL=ALL so both nodes hold every partition. Profile `$W/big_keys.yaml`:

```yaml
keyspace: tp
keyspace_definition: CREATE KEYSPACE tp WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2};
table: big_keys
table_definition: CREATE TABLE big_keys (k blob PRIMARY KEY, v blob) WITH compression = {'enabled': 'false'};
columnspec:
  - name: k
    size: fixed(2048)
    population: seq(1..100000)
  - name: v
    size: fixed(64)
insert:
  partitions: fixed(1)
  select: fixed(1)/1
  batchtype: UNLOGGED
```

Each `nodetool repair --full tp big_keys` validates all 100,000 partitions on each node (RF 2 on 2
nodes: each node replicates every range), so the check runs 100,000 times per node per repair. Retained
heap at N ≥ P: 100,000 × ~2,224 B ≈ 222 MB per node, measurable against a 2 GiB heap. Disk per node
≈ 0.5 GB. Duration: load ~5 min; per N value ~10 min (restart, repair, measure).

**B3d. Observables and instruments.** Per node, after each repair:
- live `TopPartition` instances: `jcmd $PID GC.class_histogram | awk '$4=="org.apache.cassandra.metrics.TopPartitionTracker$TopPartition"{print $2}'`
  (forces a full GC first; counts live objects; the tombstone holder stays empty because the workload
  has no tombstones);
- heap used after full GC: `jcmd $PID GC.run; jcmd $PID GC.heap_info | grep -o 'used [0-9]*K'`;
- `nodetool -p <port> tablestats tp.big_keys | grep 'Number of partitions'` (P check, once).
Not observable directly: the transient collector + clone during the merge (≤ 3N); retained bytes are
inferred as count × per-entry size and cross-checked by the heap delta.
Do **not** run `nodetool tablestats tp.big_keys` (it builds a hex-string map, ~4 KB per entry) at N ≥
10,000; it is used once, at N = 10 only, to see 10 names under "Top partitions by size".

**B3e. Procedure.**
1. Build and prepare nodes (B3a). Write `$W/big_keys.yaml` (B3c).
2. For node K = 1 then 2 (start node 2 after node 1 shows `UN`):
   `cd $W/nK && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M bin/cassandra -p $W/nK.pid > $W/nK.out 2>&1`;
   wait until `$W/n1/bin/nodetool status` shows two `UN`.
3. Load once: `$W/src/tools/bin/cassandra-stress user profile=$W/big_keys.yaml "ops(insert=1)" n=100000 cl=ALL no-warmup -node 127.0.0.1 -rate threads=8`;
   `$W/n1/bin/nodetool flush tp; $W/n1/bin/nodetool -p 7299 flush tp`; check P ≈ 100,000.
4. Baseline (no repair yet, N = 10): restart both nodes with N = 10 (steps 6a–6b), measure B3d twice,
   5 minutes apart: this gives the heap-noise band.
5. For N in 10, 10,000, 50,000, 1,000,000, then the threshold control:
   a. `kill $(cat $W/n2.pid) $(cat $W/n1.pid)`; wait until both pids are gone.
   b. Edit both yaml files (`max_top_size_partition_count`, and for the control `min_tracked_partition_size: 1MiB`); start both nodes (step 2).
   c. `$W/n1/bin/nodetool repair --full tp big_keys`; wait for it to report success.
   d. On each node: B3d measurements, three times one minute apart; record the median.
   e. At N = 10 only: `nodetool tablestats tp.big_keys` and count the "Top partitions by size" lines.
   Keep each run under 50 minutes after node start (the hourly save, `TopPartitionTracker.java:91`, is
   not needed here; if it fires, the stored list is re-trimmed to the new N at the next start, A3 step 1).
6. Clean up (B4).

**B3f. Predictions.** Per node, P = 100,000, key 2,048 B.

| N | `TopPartition` instances | heap used after full GC, minus the N = 10 run |
|---|---|---|
| 10 | 10 | 0 (within the baseline noise band) |
| 10,000 | 10,000 | ≈ +22 MB (may sit inside noise) |
| 50,000 | 50,000 | ≈ +111 MB |
| 1,000,000 (control) | 100,000 | ≈ +222 MB |
| 1,000,000, min 1 MiB (threshold control) | 0 | 0 (within noise) |

The 50,000 delta is 0.4–0.6 of the 1,000,000 delta.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| instances = min(N, 100,000) and heap delta ∝ instances | claim holds: the entry caps the set's heap on a real node |
| instances > N for any N < 100,000 | claim wrong: the cap does not bind on the real path |
| instances = 100,000 at N = 10,000 or 50,000 | claim wrong |
| heap delta at N = 50,000 ≈ delta at 1,000,000 | heap is not following the entry (something else retains the keys); claim wrong for heap |
| control (N = 1,000,000) shows < 100,000 instances, or 0 everywhere | the workload never reached the tracker (repair not eligible, `top_partitions_enabled` off, min threshold not 0B): not confirmed |
| threshold control > 0 | yaml not applied; repeat |

**B3h. Controls.** Same data and same repair for every N; only the yaml value changes. The N =
1,000,000 run is the positive control (same workload, set fills to P where the cap does not bind). The
threshold control shows instances come only from tracked validations. Key cache off and memtables
flushed so no other per-key structure differs between runs; the baseline pair gives the noise band.

**B4. Risks and cleanup.** Both tiers run only under `$W` on local disk (≈ 1 GB for the nodes, ≈ 2 GB
for the build). Never build in `/users/jason92/cassandra-5.0.9`. Do not use N ≤ 0 (A3: table open can
throw). Do not run `nodetool tablestats` on `tp.big_keys` at large N. Cleanup: `kill $(cat $W/n1.pid)
$(cat $W/n2.pid)`; `pkill -f "$W/n"` if any remains; `pgrep -f "$W"` and `pgrep -f cassandra-stress`
must return nothing; then `rm -rf $W`.

## C. Sources read

- src/java/org/apache/cassandra/config/Config.java (1140-1160)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (5077-5110, 898-901, 2827)
- src/java/org/apache/cassandra/service/StorageService.java (7540-7600)
- src/java/org/apache/cassandra/service/StorageServiceMBean.java (1275-1277)
- src/java/org/apache/cassandra/metrics/TopPartitionTracker.java (whole file)
- src/java/org/apache/cassandra/repair/ValidationManager.java (85-175)
- src/java/org/apache/cassandra/repair/Validator.java (170-217)
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (560-580, 3575-3610, 1114, 2996)
- src/java/org/apache/cassandra/db/SystemKeyspace.java (170, 425-445, 1955-2005)
- src/java/org/apache/cassandra/db/DecoratedKey.java (195-215)
- src/java/org/apache/cassandra/utils/ByteBufferUtil.java (715-719)
- src/java/org/apache/cassandra/utils/ObjectSizes.java (40-70, 225-255)
- src/java/org/apache/cassandra/tools/nodetool/stats/TableStatsHolder.java (380-400), TableStatsPrinter.java (100, 150-155)
- src/java/org/apache/cassandra/tools/nodetool/Repair.java (options)
- src/java/org/apache/cassandra/concurrent/ScheduledThreadPoolExecutorPlus.java (92-95)
- test/unit/org/apache/cassandra/db/TopPartitionTrackerTest.java
- test/unit/org/apache/cassandra/cql3/CQLTester.java (418)
- test/distributed/org/apache/cassandra/distributed/test/TopPartitionsTest.java (240-270)
- test/conf/cassandra.yaml, conf/cassandra.yaml, conf/cassandra-env.sh, conf/jvm11-server.options, bin/cassandra.in.sh, build.xml, NEWS.txt, CHANGES.txt, tools/stress/README.txt

## D. Stage-4 feedback

none yet

## Config-first: places found

Entry `max_top_size_partition_count` (declared [`Config.java:1150`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L1150)).
Value path: `Config.max_top_size_partition_count` → `DatabaseDescriptor.getMaxTopSizePartitionCount()` /
`setMaxTopSizePartitionCount()` (`DatabaseDescriptor.java:5082-5090`; JMX `StorageService.java:7549-7558`)
→ `TopHolder.maxTopPartitionCount` (`TopPartitionTracker.java:200`, `:213`, `:224`).

1. `TopPartitionTracker.java:239` — admission check in `TopHolder.track(key, value)`: whether a new
   entry (with a retained heap copy of the partition key) is allocated. **This case file.**
2. `TopPartitionTracker.java:246-250` — eviction loop in `TopHolder.track(TopPartition)`: hard bound
   `top.size() ≤ N` after every insert (admission, merge `:270`, load `:231`). Covered by this case file.
3. `TopPartitionTracker.java:176-178` (reached from `ValidationManager.java:117-119`) — per-validation
   `Collector` built with N: bounds the transient heap set built during each full/preview repair
   validation. Covered by this case file (B2 measures the collector).
4. `TopPartitionTracker.java:85-87` (from `ColumnFamilyStore.java:570-573`) — long-lived per-table
   holder built with N from the stored list at table creation / startup: bounds the steady-state heap set
   (the stored list is read whole first, `SystemKeyspace.java:1987-1995`). Covered by this case file (B3).
5. `TopPartitionTracker.java:263-278` — `merge` / `cloneForMerging`: the new long-lived holder takes the
   collector's N and re-tracks kept old entries under it (how a runtime change takes effect). Covered by
   this case file.
6. `TopPartitionTracker.java:103-105` → `SystemKeyspace.java:1961-1970` — hourly save (`:91`) writes the
   ≤ N set as one frozen list row into `system.top_partitions`: bounds that row's disk and commit-log
   size (one mutation, also limited by `max_mutation_size`). **Case file
   `max_top_size_partition_count-saveTopPartitions-top.size--autonomous.md`.**
7. `TopPartitionTracker.java:293-302` via `ColumnFamilyStore.java:3578-3583` and
   `TableStatsHolder.java:392` — JMX `getTopSizePartitions` / nodetool tablestats builds a map of ≤ N
   hex-string keys (~2 × key length each) on heap per call. Left for a later unit.

Non-restricting uses: the getter/setter pairs above, and the dtest/unit tests that set it.
