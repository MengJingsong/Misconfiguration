# max_top_size_partition_count — verification solution (system.top_partitions row)  <!-- file: cases/max_top_size_partition_count-saveTopPartitions-top.size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the save gate that writes the size set to disk, **linked**: [`TopPartitionTracker.java:103`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TopPartitionTracker.java#L103) → `SystemKeyspace.saveTopPartitions` ([`SystemKeyspace.java:1961`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/SystemKeyspace.java#L1961)) |
| Pinned source | `cassandra-5.0.9` |
| Lead source | config-first |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code (CLI version not exposed to the agent), 2026-11-26 |
| Estimate | `positive`. The hourly save writes the whole in-memory size set, which `TopHolder.track` keeps at ≤ N entries, as one frozen-list cell in `system.top_partitions`; so that row (on disk and in the commit log) holds at most N tuples of ≈ 2 × key length + 20 B each. Small at the default N = 10; it scales linearly with N until the row exceeds `max_mutation_size`, when the save fails and nothing is written. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `max_top_size_partition_count`, a cassandra.yaml entry (a `Config` field),
declared at [`Config.java:1150`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L1150),
`public volatile int max_top_size_partition_count = 10;`. Unit: a count of partitions. Default 10 (a
literal; no derivation and no validation in `DatabaseDescriptor`, getter/setter at
`DatabaseDescriptor.java:5082-5090`). Not in the shipped `conf/cassandra.yaml`; set by adding
`max_top_size_partition_count: <int>` (read at startup), or at runtime through JMX attribute
`MaxTopSizePartitionCount` on `org.apache.cassandra.db:type=StorageService`
(`StorageService.java:7549-7558`). No nodetool setter. A runtime change reaches the saved row only after
the next eligible repair validation rebuilds the in-memory set (see the sibling case
`max_top_size_partition_count-TopHolder.track-top.size--autonomous.md`, A3 step 5), and then the next
hourly save.

**A2. What it caps.** Disk (and commit log): the size of the row
`(keyspace_name, table_name, 'SIZES')` in `system.top_partitions`
(`SystemKeyspace.java:434-444`: `top frozen<list<tuple<text, bigint>>>`). The quantity bounded is
`sizes.top.size()`, the number of entries written into that list (`SystemKeyspace.java:1964-1969`).
Each list element is the partition key as text (`partitionKeyType.getString`, for a blob key the hex
string, 2 × key bytes) plus a bigint; serialized ≈ 4 + (4 + text) + (4 + 8) bytes, e.g. 148 B for a
64-byte blob key.

**A3. Mechanism.**

1. Each non-system table's tracker schedules `save` every 60 minutes, first run 60 minutes after the
   tracker is built (table creation or node startup) on `ScheduledExecutors.optionalTasks`
   (`TopPartitionTracker.java:91`); the executor wraps the task so a thrown exception is logged and the
   schedule continues (`ScheduledThreadPoolExecutorPlus.java:92-95`).
2. **The check**: [`if (!sizes.top.isEmpty() && sizes.lastUpdate > lastSizeSave)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TopPartitionTracker.java#L103)
   — true → `SystemKeyspace.saveTopPartitions(metadata, "SIZES", sizes.top, sizes.lastUpdate)`
   (`:105`); false → nothing written (no set, or no repair merged since the last save).
3. The set written is the long-lived holder, which only changes through `track(...)`, whose
   [`while (top.size() > maxTopPartitionCount)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TopPartitionTracker.java#L246)
   loop keeps it at ≤ N = `getMaxTopSizePartitionCount()` (admission [`:239`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TopPartitionTracker.java#L239),
   collector built with N at `:176-178`, merged holder keeps the collector's N at `:263-278`).
4. `saveTopPartitions` builds a list of `topPartitions.size()` tuples (`SystemKeyspace.java:1964-1969`)
   and runs one `INSERT` with `executeInternal` (`:1970`): one mutation, one cell, overwriting the
   previous version (older versions remain in older sstables until compaction).
5. The mutation is size-checked against `max_mutation_size` (default half of
   `commitlog_segment_size`, `DatabaseDescriptor.java:898-899`; `Mutation.java:169-176`, called from
   `CommitLog.java:304`). Above it, `MutationExceededMaxSizeException` is thrown, the save is lost and
   logged, and `lastSizeSave` is not advanced (`:106` not reached), so the save is retried hourly.

Bypasses/overshoots: none adds entries beyond N to the written set. The row is a single cell, so the
disk cost per table is one list of ≤ N elements plus, until compaction, superseded copies of it in older
sstables (at most one new copy per hour, and only after a repair changed `lastUpdate`). The commit log
receives each saved mutation too.

**A4. Other consumers.** The sibling `TOMBSTONES` row of the same table
(`TopPartitionTracker.java:109-114`, bounded by `max_top_tombstone_partition_count`); every other
system table, user sstables, commit log, hints, snapshots. The heap side of the same set is the sibling
case file.

**A5. Evidence beyond the source.** `NEWS.txt:418-421` (top partitions are stored in
`system.top_partitions`); `test/unit/org/apache/cassandra/db/TopPartitionTrackerTest.java` (count
limit, `:85-107`); none on the save path specifically.

## B. Verification solution

**B1. Claim under test.** After a save, the `SIZES` row of a table in `system.top_partitions` holds
min(N, P) elements and its serialized and on-disk size grow ∝ min(N, P), where N =
`max_top_size_partition_count` and P = the table's partitions at or above `min_tracked_partition_size`;
it never holds more than N elements. Wrong if the stored list exceeds N, or its size grows with P at a
fixed N < P.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant; `export W=/local/<user>/tpsave` (local, non-shared,
≥ 5 GiB free); `rsync -a /users/jason92/cassandra-5.0.9/ $W/src/`. Add
`$W/src/test/unit/org/apache/cassandra/db/TopSizeSaveProbeTest.java`. The test JVM is `build.xml`'s
`testsome` fork (1 GiB heap). The unit-test config (`test/conf/cassandra.yaml:10`,
`commitlog_segment_size: 5MiB`) makes `max_mutation_size` = 2,560 KiB = 2,621,440 B.

```java
package org.apache.cassandra.db;

import java.nio.ByteBuffer;
import java.util.Collections;
import java.util.Random;

import org.junit.Test;

import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.cql3.QueryProcessor;
import org.apache.cassandra.cql3.UntypedResultSet;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.dht.IPartitioner;
import org.apache.cassandra.dht.Range;
import org.apache.cassandra.metrics.TopPartitionTracker;
import org.apache.cassandra.schema.SchemaConstants;
import org.apache.cassandra.schema.TableMetadata;

public class TopSizeSaveProbeTest extends CQLTester
{
    static final int KEY_BYTES = 64;

    @Test
    public void probe() throws Throwable
    {
        DatabaseDescriptor.setMinTrackedPartitionSizeInBytes(new DataStorageSpec.LongBytesBound("0B"));
        ColumnFamilyStore tp = Keyspace.open(SchemaConstants.SYSTEM_KEYSPACE_NAME).getColumnFamilyStore(SystemKeyspace.TOP_PARTITIONS);
        tp.disableAutoCompaction();
        for (int n : new int[]{ 10, 100, 1_000, 10_000, 100_000 })
            runOne(tp, "RUN", n, 15_000);
        runOne(tp, "MUTATION-LIMIT", 100_000, 20_000);   // list ~2.96 MB > 2.5 MiB
    }

    private void runOne(ColumnFamilyStore tp, String label, int n, int m) throws Throwable
    {
        createTable("CREATE TABLE %s (k blob PRIMARY KEY, v int)");
        TableMetadata md = getCurrentColumnFamilyStore().metadata();
        IPartitioner p = md.partitioner;
        DatabaseDescriptor.setMaxTopSizePartitionCount(n);
        TopPartitionTracker tpt = new TopPartitionTracker(md);
        TopPartitionTracker.Collector c = new TopPartitionTracker.Collector(
            Collections.singleton(new Range<>(p.getMinimumToken(), p.getMinimumToken())));
        Random r = new Random(7);
        for (int i = 0; i < m; i++)
        {
            byte[] b = new byte[KEY_BYTES];
            r.nextBytes(b);
            ByteBuffer.wrap(b).putInt(0, i);
            c.trackPartitionSize(p.decorateKey(ByteBuffer.wrap(b)), 1_000_000L + r.nextInt(1_000_000_000));
        }
        tpt.merge(c);
        int inMemory = tpt.topSizes().top.size();
        long before = tp.metric.liveDiskSpaceUsed.getCount();
        String err = "none";
        try { tpt.save(); } catch (Throwable t) { err = t.getClass().getSimpleName(); }
        tp.forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
        long after = tp.metric.liveDiskSpaceUsed.getCount();
        UntypedResultSet rs = QueryProcessor.executeInternal(
            "SELECT top FROM system.top_partitions WHERE keyspace_name = ? AND table_name = ? AND top_type = 'SIZES'",
            md.keyspace, md.name);
        int stored = 0; long storedBytes = 0;
        if (!rs.isEmpty())
            for (ByteBuffer bb : rs.one().getList("top", BytesType.instance)) { stored++; storedBytes += 4 + bb.remaining(); }
        System.out.printf("PROBE label=%s n=%d m=%d inMemory=%d saveError=%s stored=%d storedListBytes=%d diskDelta=%d%n",
                          label, n, m, inMemory, err, stored, storedBytes, after - before);
        tpt.close();
    }
}
```

**B2b. Knobs.** N via `DatabaseDescriptor.setMaxTopSizePartitionCount` (same field as the yaml entry):
10, 100, 1,000, 10,000 (below M) and 100,000 (> M; positive control). `min_tracked_partition_size` =
`0B`. One extra run at N = 100,000 with M = 20,000 probes the `max_mutation_size` ceiling.

**B2c. Workload.** M = 15,000 distinct 64-byte keys offered to a full-range collector, merged, then
`save()` called directly (the public `@VisibleForTesting` method; the hourly schedule is not waited
for). Element = 4 + 4 + 128 + 4 + 8 = 148 B, so the list at N ≥ M is 15,000 × 148 ≈ 2.22 MB, below
the 2,621,440 B limit; at M = 20,000 it is ≈ 2.96 MB, above it.

**B2d. Observables and instruments.** `inMemory` (set size written), `stored` (elements read back from
the row: the operand on disk), `storedListBytes` (serialized list bytes), `diskDelta` (change of
`system.top_partitions` `LiveDiskSpaceUsed` across one flush, with autocompaction off so each save is its
own sstable), `saveError`. Read from `PROBE` lines in
`$W/src/build/test/output/TEST-org.apache.cassandra.db.TopSizeSaveProbeTest.xml`. Not observable here: the
commit-log bytes of the save mutation.

**B2e. Procedure.**
1. `cd $W/src && ant jar > $W/build.log 2>&1`
2. `ant testsome -Dtest.name=org.apache.cassandra.db.TopSizeSaveProbeTest > $W/unit.log 2>&1`
3. `grep -o 'PROBE[^<]*' $W/src/build/test/output/TEST-org.apache.cassandra.db.TopSizeSaveProbeTest.xml`
4. `pgrep -f TopSizeSaveProbeTest` returns nothing.

**B2f. Predictions.**

| label | N | inMemory = stored | storedListBytes | diskDelta | saveError |
|---|---|---|---|---|---|
| RUN | 10 | 10 | 1,480 | ≤ ~20 KB (sstable component overhead dominates) | none |
| RUN | 100 | 100 | 14,800 | overhead + 0.5–1.1 × 14.8 KB | none |
| RUN | 1,000 | 1,000 | 148,000 | overhead + 0.5–1.1 × 148 KB | none |
| RUN | 10,000 | 10,000 | 1,480,000 | overhead + 0.5–1.1 × 1.48 MB | none |
| RUN | 100,000 | 15,000 (= M) | 2,220,000 | overhead + 0.5–1.1 × 2.22 MB | none |
| MUTATION-LIMIT | 100,000 | 20,000 in memory, stored 0 | 0 | ≈ 0 (empty or no flush) | `MutationExceededMaxSizeException` (or a wrapper) |

(0.5–1.1: the system table's default compression on hex text.) storedListBytes is exactly 148 × stored.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| stored = min(N, 15,000) and storedListBytes = 148 × stored; diskDelta − (N = 10 delta) ∝ stored | claim holds |
| stored > N for any N | claim wrong: the saved list is not bounded by N |
| stored = 15,000 for N < 15,000 | claim wrong |
| N = 100,000 run stores < 15,000 | workload did not reach the save; not confirmed |
| MUTATION-LIMIT run stores 20,000 | the mutation ceiling is not on this path (A3 step 5 wrong); does not affect the N claim |

**B2h. Controls.** N > M is the positive control (same workload, row grows to M where the cap does not
bind). A fresh table per run gives a separate row and a fresh tracker (`lastSizeSave` = 0, so the gate at
`:103` passes). Autocompaction off on `system.top_partitions` so each flush adds exactly one sstable.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host (≥ 8 GiB RAM, ≥ 10 GiB local disk at `$W`), JDK 11,
Ant, Python 3 for cqlsh. Two instances on 127.0.0.1 / 127.0.0.2 (RF 2 is needed: repair has nothing to
do at RF 1, `StorageService.java:4798`, `RepairCoordinator.java:387-396`). Build `cd $W/src && ant jar
stress-build`; `rsync -a $W/src/ $W/n1/; rsync -a $W/src/ $W/n2/`. In each `$W/nK/conf/cassandra.yaml`:
`cluster_name: 'tpsave'`, `num_tokens: 16`, seeds `"127.0.0.1:7000"`, `listen_address`/`rpc_address`
127.0.0.K, `min_tracked_partition_size: 0B`, `top_partitions_enabled: true`,
`max_top_size_partition_count: <N>`; leave `commitlog_segment_size` at 32MiB (so `max_mutation_size` =
16 MiB = 16,777,216 B). `$W/n2/conf/cassandra-env.sh`: `JMX_PORT="7299"`. Heap `MAX_HEAP_SIZE=2G
HEAP_NEWSIZE=400M`.

**B3b. Knobs.** `max_top_size_partition_count` = 10 (default), 10,000, 1,000,000 (> P, positive
control), each by restart of both nodes.

**B3c. Workload.** Keyspace `tp` RF 2, table `small_keys (k blob PRIMARY KEY, v blob)`, P = 80,000
partitions, 64-byte keys, 64-byte values, loaded once with cassandra-stress at CL=ALL. Profile
`$W/small_keys.yaml`:

```yaml
keyspace: tp
keyspace_definition: CREATE KEYSPACE tp WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2};
table: small_keys
table_definition: CREATE TABLE small_keys (k blob PRIMARY KEY, v blob);
columnspec:
  - name: k
    size: fixed(64)
    population: seq(1..80000)
  - name: v
    size: fixed(64)
insert:
  partitions: fixed(1)
  select: fixed(1)/1
  batchtype: UNLOGGED
```

A full repair then makes each node's set hold min(N, 80,000) entries; the save writes it. Row at N ≥ P:
80,000 × 148 B ≈ 11.84 MB, below the 16 MiB mutation limit. Duration: ≥ 62 minutes per N value (the
first save is 60 minutes after node start), ≈ 3.5 hours for three values.

**B3d. Observables and instruments.** On node 1 (node 2 optional, same commands with `-p 7299` /
127.0.0.2), after the save:
- `nodetool info | grep Uptime` (must exceed 3,720 s before measuring);
- `cqlsh 127.0.0.1 -e "SELECT last_update FROM system.top_partitions WHERE keyspace_name='tp' AND table_name='small_keys' AND top_type='SIZES'"` (must be after the repair finished: the save happened);
- element count: `cqlsh 127.0.0.1 -e "SELECT top FROM system.top_partitions WHERE keyspace_name='tp' AND table_name='small_keys' AND top_type='SIZES'" > $W/top-N.txt; grep -o "('" $W/top-N.txt | wc -l`;
- disk: `nodetool flush system top_partitions; nodetool compact system top_partitions; nodetool tablestats system.top_partitions | grep 'Space used (live)'` (compaction leaves one sstable with the latest row version).
Not observable directly: the commit-log share of the save (mixed with other writes).

**B3e. Procedure.**
1. Prepare and start both nodes (as in B3a; start node 1, wait for `UN`, start node 2:
   `cd $W/nK && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M bin/cassandra -p $W/nK.pid > $W/nK.out 2>&1`).
2. Load: `$W/src/tools/bin/cassandra-stress user profile=$W/small_keys.yaml "ops(insert=1)" n=80000 cl=ALL no-warmup -node 127.0.0.1 -rate threads=8`;
   flush `tp` on both nodes.
3. For N in 10, 10,000, 1,000,000:
   a. Stop both nodes (`kill $(cat $W/n2.pid) $(cat $W/n1.pid)`; wait for exit); set N in both yaml files; start both.
   b. Within 30 minutes of start: `$W/n1/bin/nodetool repair --full tp small_keys`; wait for success; note the time.
   c. Wait until node 1 uptime > 3,720 s; check `last_update` is later than step b.
   d. Measure (B3d) and record count and Space used (live).
4. Clean up (B4).

**B3f. Predictions.** Node 1, P = 80,000, element 148 B.

| N | elements in the stored list | serialized list | Space used (live), system.top_partitions |
|---|---|---|---|
| 10 | 10 | 1,480 B | ≤ ~20 KB (component overhead) |
| 10,000 | 10,000 | 1.48 MB | 0.75–1.65 MB |
| 1,000,000 (control) | 80,000 | 11.84 MB | 6–13 MB |

The N = 1,000,000 space is 7–9 × the N = 10,000 space (ratio 8 by element count).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| elements = min(N, 80,000); space follows elements | claim holds on a node |
| elements > N | claim wrong |
| elements = 80,000 at N = 10,000 | claim wrong |
| control row < 80,000 elements or `last_update` not refreshed | save or repair did not happen (not confirmed); check log for `MutationExceededMaxSizeException` or a failed repair |
| space flat across N while elements follow N | on-disk size dominated by overhead/compression; the element count still decides the claim |

**B3h. Controls.** Same data, same repair, only N changes; the N = 1,000,000 run is the positive control.
`last_update` proves each measured row was written by that run's save. Compaction before measuring
removes superseded row versions from earlier runs.

**B4. Risks and cleanup.** All files under `$W` on local disk (< 1 GB of node data). Never build in
`/users/jason92/cassandra-5.0.9`. Do not set N ≤ 0 (table open can throw, sibling case A3). Keep P × 148
B under 16 MiB or the save fails silently (logged). Cleanup: kill both pids, `pkill -f "$W/n"`;
`pgrep -f "$W"` and `pgrep -f cassandra-stress` must be empty; `rm -rf $W`.

## C. Sources read

- src/java/org/apache/cassandra/config/Config.java (1140-1160)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (898-901, 2827, 5077-5110)
- src/java/org/apache/cassandra/service/StorageService.java (4798, 7540-7600)
- src/java/org/apache/cassandra/metrics/TopPartitionTracker.java (whole file)
- src/java/org/apache/cassandra/db/SystemKeyspace.java (170, 425-445, 1955-2005)
- src/java/org/apache/cassandra/db/Mutation.java (160-180), src/java/org/apache/cassandra/db/IMutation.java (31, 49-56)
- src/java/org/apache/cassandra/db/commitlog/CommitLog.java (304)
- src/java/org/apache/cassandra/concurrent/ScheduledThreadPoolExecutorPlus.java (92-95)
- src/java/org/apache/cassandra/repair/ValidationManager.java (85-178), Validator.java (170-217), RepairCoordinator.java (387-405)
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (560-580, 1114, 2996, 3575-3610)
- src/java/org/apache/cassandra/metrics/TableMetrics.java (139-143, 678)
- src/java/org/apache/cassandra/tools/nodetool/Info.java (64-66), stats/TableStatsPrinter.java (100)
- test/unit/org/apache/cassandra/db/TopPartitionTrackerTest.java, test/unit/org/apache/cassandra/cql3/CQLTester.java (418), test/conf/cassandra.yaml
- conf/cassandra.yaml, conf/cassandra-env.sh, build.xml, NEWS.txt, CHANGES.txt, tools/cqlstress-example.yaml, tools/stress/src/org/apache/cassandra/stress/settings/SettingsCommand.java (124)

## D. Stage-4 feedback

none yet
