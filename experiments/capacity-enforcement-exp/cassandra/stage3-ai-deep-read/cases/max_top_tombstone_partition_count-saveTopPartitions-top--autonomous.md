# max_top_tombstone_partition_count — verification solution (disk: `system.top_partitions` row)  <!-- file: cases/max_top_tombstone_partition_count-saveTopPartitions-top--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the save of the tombstone holder, **linked**: [`TopPartitionTracker.java:110-112`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TopPartitionTracker.java#L110-L112) → [`SystemKeyspace.java:1961-1970`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/SystemKeyspace.java#L1961-L1970) |
| Pinned source | `cassandra-5.0.9` |
| Lead source | config-first |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code (CLI version not shown to the agent), 2026-11-26 |
| Estimate | `positive` — the hourly save writes the tombstone holder's `top` set (≤ N entries, enforced at `TopPartitionTracker.java:239/246`) as one frozen-list cell of `system.top_partitions`, so the row's on-disk size is ≈ N × (key length + 20 B); the footprint is one overwritten row per table, and above `max_mutation_size` (default 16 MiB) the save is rejected, so disk follows N only up to that size. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `max_top_tombstone_partition_count`, cassandra.yaml configuration entry, declared at
[`Config.java:1151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L1151)
(`public volatile int max_top_tombstone_partition_count = 10;`). Unit: partitions (entries). Default 10, a literal
in `Config.java`; not in the shipped `conf/cassandra.yaml` but accepted as a yaml key (public `Config` field). No
validation (`DatabaseDescriptor.java:5092-5100`). Set in yaml (restart) or at runtime through JMX
`org.apache.cassandra.db:type=StorageService` attribute `MaxTopTombstonePartitionCount`
(`StorageService.java:7561-7570`); a runtime change reaches the saved row only after the next repair's merge
and the next hourly save.

**A2. What it caps.** Disk (commit log and the `system.top_partitions` sstables). The quantity is the length of the
`top` column, `frozen<list<tuple<text, bigint>>>` (`SystemKeyspace.java:434-443`), which is built from the
holder's `top` set (`SystemKeyspace.java:1964-1969`) whose size the entry bounds. Serialized size per element ≈
4 (element length) + 4 + K (key as text) + 4 + 8 (bigint) = **K + 20 bytes**, K = the partition key's string
form length.

**A3. Mechanism.**
1. The tombstone holder is bounded to `top.size() <= N` by the admission check
   [`TopPartitionTracker.java:239`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TopPartitionTracker.java#L239)
   and the trim loop `:246-250`, filled during full/validate repairs and installed by `merge` (`:117-134`,
   `ValidationManager.java:151-152`). See the heap case file for the full path.
2. Every table's tracker schedules `save` 60 min after construction and every 60 min after
   (`TopPartitionTracker.java:91`; constructed with the `ColumnFamilyStore`, `ColumnFamilyStore.java:570-573`).
   The task runs on `optionalTasks`; exceptions are suppressed so the schedule continues
   (`ScheduledThreadPoolExecutorPlus.java:92-95`).
3. **The check**
   [`TopPartitionTracker.java:110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TopPartitionTracker.java#L110):
   `if (!tombstones.top.isEmpty() && tombstones.lastUpdate > lastTombstoneSave)` — a write happens only if a merge
   happened since the last save; then `SystemKeyspace.saveTopPartitions(metadata, "TOMBSTONES", tombstones.top, ...)`
   (`:112`).
4. `saveTopPartitions` (`SystemKeyspace.java:1961-1970`) converts each `TopPartition` into a tuple (key string,
   count) and issues one `INSERT` of the whole list with `executeInternal`. The row key is
   `(keyspace_name, table_name, top_type)`: one row per table per type, overwritten each save.
5. The write goes through the commit log, where `CommitLog.add` calls `mutation.validateSize`
   (`CommitLog.java:304`, `Mutation.java:169-177`): if the serialized mutation exceeds `max_mutation_size`
   (default `commitlog_segment_size / 2` = 16 MiB, `DatabaseDescriptor.java:898-899`, `conf/cassandra.yaml:660`)
   it throws `MutationExceededMaxSizeException` ("Rejected an oversized mutation ...",
   `MutationExceededMaxSizeException.java:56`) and marks `CommitLog.OverSizedMutations`; nothing is written and
   `lastTombstoneSave` is not advanced, so the save is retried (and rejected) every hour.

Outcomes: N small → a row of ~N × (K + 20) B in the memtable, commit log, then an sstable; older versions are
shadowed and removed by compaction. N × (K + 20) > ~16 MiB → nothing new on disk.
Overshoot: until `system.top_partitions` compacts, several versions (one per save) coexist on disk; the commit
log holds each saved version until the memtable flushes.

**A4. Other consumers.** The size-type row of the same table (`SIZES`, sibling entry
`max_top_size_partition_count`); all other system tables; the commit log is shared by every write; the user
table's own sstables are orders of magnitude larger.

**A5. Evidence beyond the source.** `NEWS.txt:418-421` (results stored in `system.top_partitions`);
`TopPartitionTrackerTest.testSaveLoad` (`test/unit/org/apache/cassandra/db/TopPartitionTrackerTest.java:140-200`)
calls `save()` directly and reloads; no doc on the disk size.

## B. Verification solution

**B1. Claim under test.** After a repair and the next save, the `TOMBSTONES` row of `system.top_partitions` for a
table holds exactly `min(N, P_q)` tuples and its on-disk size is ≈ `min(N, P_q)` × (K + 20) B, as long as that is
below `max_mutation_size`; above it the save is rejected and the row does not grow.

### B2. Unit tier

**B2a. Environment and build.** As the heap case: JDK 11, Ant, tree copied to local disk:
```
WORK=/local/scratch/tpt-disk      # local disk, >= 10 GB free, not shared storage
mkdir -p $WORK && rsync -a /users/jason92/cassandra-5.0.9/ $WORK/src/
cd $WORK/src && ant jar build-test
```
The unit harness uses `test/conf/cassandra.yaml`, where `commitlog_segment_size: 5MiB` → `max_mutation_size`
= 2,621,440 B. Test class `$WORK/src/test/unit/org/apache/cassandra/db/TopTombstoneCapDiskTest.java`:

```java
package org.apache.cassandra.db;

import java.nio.ByteBuffer;
import java.util.*;
import org.junit.Test;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.dht.*;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.metrics.TopPartitionTracker;
import org.apache.cassandra.utils.ByteBufferUtil;

public class TopTombstoneCapDiskTest extends CQLTester
{
    static final int M = 10_000, K = 500;

    static DecoratedKey key(int i)
    {
        StringBuilder sb = new StringBuilder(String.format("%010d", i));
        Random r = new Random(i);
        while (sb.length() < K) sb.append(Integer.toHexString(r.nextInt(16)));   // poorly compressible
        return Murmur3Partitioner.instance.decorateKey(ByteBufferUtil.bytes(sb.toString()));
    }

    void run(int n)
    {
        ColumnFamilyStore sys = Keyspace.open("system").getColumnFamilyStore("top_partitions");
        DatabaseDescriptor.setMaxTopTombstonePartitionCount(n);
        TopPartitionTracker tpt = new TopPartitionTracker(getCurrentColumnFamilyStore().metadata());
        Range<Token> full = new Range<>(new Murmur3Partitioner.LongToken(0), new Murmur3Partitioner.LongToken(0));
        TopPartitionTracker.Collector c = new TopPartitionTracker.Collector(Collections.singleton(full));
        for (int i = 0; i < M; i++) c.trackTombstoneCount(key(i), i + 1L);
        tpt.merge(c);
        String outcome = "saved";
        try { tpt.save(); } catch (Exception e) { outcome = e.getClass().getSimpleName(); }
        int stored = SystemKeyspace.getTopPartitions(getCurrentColumnFamilyStore().metadata(), "TOMBSTONES").topPartitions.size();
        sys.forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
        long onDisk = 0, uncompressed = 0;
        for (SSTableReader s : sys.getLiveSSTables()) { onDisk += s.onDiskLength(); uncompressed += s.uncompressedLength(); }
        System.out.printf("RESULT N=%d held=%d outcome=%s storedTuples=%d dataOnDisk=%d dataUncompressed=%d%n",
                          n, tpt.topTombstones().top.size(), outcome, stored, onDisk, uncompressed);
        tpt.close();
        sys.truncateBlocking();   // isolate the next run
    }

    @Test
    public void sweep()
    {
        createTable("create table %s (pk text primary key, x int)");
        DatabaseDescriptor.setMinTrackedPartitionTombstoneCount(0);
        for (int n : new int[]{ 10, 1_000, 4_000, 6_000 })
            run(n);
    }
}
```
(each run uses a new table-level tracker for the same table; the stored row of one run is removed by the
truncate before the next.)

**B2b. Knobs.** N via `DatabaseDescriptor.setMaxTopTombstonePartitionCount`: 10 (default), 1,000 and 4,000
(row below the 2.5 MiB unit-harness mutation limit), 6,000 (row above it: shows the overshoot guard).

**B2c. Workload.** M = 10,000 distinct text keys of K = 500 characters (10-digit prefix + pseudo-random hex), counts
1..10,000, threshold 0. M > every N, so the holder is full at N. Expected list bytes ≈ N × 520:
10 → 5.2 KB; 1,000 → 0.52 MB; 4,000 → 2.08 MB (< 2,621,440); 6,000 → 3.12 MB (> 2,621,440).

**B2d. Observables and instruments.** `held` = holder size; `outcome` of `save()` (exception class if thrown);
`storedTuples` = list length read back from `system.top_partitions`; `dataOnDisk` / `dataUncompressed` = sum of
the live `system.top_partitions` sstables after flush. Not observed: the commit log bytes (the unit harness skips
sync), compaction of older versions (avoided by truncating between runs).

**B2e. Procedure.**
1. Build, add class.
2. `cd $WORK/src && ant testsome -Dtest.name=org.apache.cassandra.db.TopTombstoneCapDiskTest 2>&1 | tee $WORK/unit-disk.log`
3. `grep RESULT $WORK/unit-disk.log`.

**B2f. Predictions.**

| N | held | outcome | storedTuples | dataUncompressed |
|---|---|---|---|---|
| 10 | 10 | saved | 10 | ~5 KB + ~0.1 KB row overhead |
| 1,000 | 1,000 | saved | 1,000 | ~0.52 MB (±10%) |
| 4,000 | 4,000 | saved | 4,000 | ~2.08 MB (±10%) |
| 6,000 | 6,000 | `MutationExceededMaxSizeException` | 0 | ~0 (no sstable or empty) |

`dataOnDisk` ≈ 0.55–1.0 × `dataUncompressed` (LZ4 on hex text). If the harness does not route `executeInternal`
through the commit log, row 6,000 instead shows "saved", 6,000 tuples, ~3.1 MB; record which.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| storedTuples = N and bytes ∝ N for N ≤ 4,000; N = 6,000 rejected | claim confirmed (disk follows N up to the mutation limit) |
| storedTuples > N | claim refuted: more than N saved |
| storedTuples = N but bytes do not grow with N | the cell is not stored as estimated; check sstable contents (`tools/bin/sstabledump`) |
| N = 6,000 saved with 6,000 tuples | no mutation-size guard on this path in the harness; the "only up to max_mutation_size" part is not confirmed at unit level, verify in B3 |
| storedTuples = 0 for small N | save skipped (`lastUpdate` not newer, `:110`); test wiring wrong |

**B2h. Controls.** M > N everywhere, threshold 0, distinct keys, so only N limits the list; truncate between runs
so each reading is one version; the 6,000 run is the case where the same workload would exceed the guard.

### B3. Cluster tier

**B3a. Environment and build.** Two nodes on one host (127.0.0.1, 127.0.0.2) built and configured exactly as in
the heap case file B3a (`$WORK/n1`, `$WORK/n2`, JMX 7199/7299, `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`, all
directories under `$WORK`), with these yaml values on both nodes:
```
min_tracked_partition_tombstone_count: 1
max_top_tombstone_partition_count: 10
commitlog_segment_size: 32MiB          # default, stated so max_mutation_size = 16 MiB = 16,777,216 B
```

**B3b. Knobs.** N = 10 (from yaml), then via JMX (heap case B3b `sjk mx ... -ms` command, both nodes) 10,000
(row ≈ 10.2 MB < 16 MiB) and 20,000 (row ≈ 20.4 MB > 16 MiB). Three values because each needs a save cycle
(≥ 60 min).

**B3c. Workload.** P = 30,000 partitions, one partition-level tombstone each, keys of K = 1,000 characters,
pseudo-random hex (so LZ4 does not hide the size):
```
$WORK/src/bin/cqlsh 127.0.0.1 -e "CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':2}; CREATE TABLE ks.t (pk text, ck int, v int, PRIMARY KEY (pk, ck));"
date +%s > $WORK/t0                     # tracker constructed now; saves at t0+60 min, +120, ...
python3 -c '
import random
print("CONSISTENCY ALL;")
for i in range(30000):
    r = random.Random(i)
    k = "%010d" % i + "".join(r.choice("0123456789abcdef") for _ in range(990))
    print("DELETE FROM ks.t WHERE pk=%r;" % k)
' > $WORK/deletes.cql
$WORK/src/bin/cqlsh 127.0.0.1 -f $WORK/deletes.cql > $WORK/load.log 2>&1
$WORK/src/bin/nodetool -p 7199 flush ks; $WORK/src/bin/nodetool -p 7299 flush ks
```
Per element K + 20 = 1,020 B: N = 10 → ~10 KB; 10,000 → ~10.2 MB; 20,000 → ~20.4 MB (rejected). P = 30,000 >
every N. Duration ≈ 3.5 h (three save cycles).

**B3d. Observables and instruments.**
- Row contents: `cqlsh 127.0.0.X -e "SELECT last_update FROM system.top_partitions WHERE keyspace_name='ks' AND table_name='t' AND top_type='TOMBSTONES';"`
  for presence/time; tuple count by
  `cqlsh 127.0.0.X -e "SELECT top FROM system.top_partitions WHERE keyspace_name='ks' AND table_name='t' AND top_type='TOMBSTONES';" | grep -o "('" | wc -l`
  (only for N ≤ 10,000; output ≈ 10 MB).
- Disk: after `nodetool -p P flush system top_partitions` and `nodetool -p P compact system top_partitions`,
  `du -cb $WORK/nX/data/system/top_partitions-*/*-Data.db | tail -1` and `nodetool -p P tablestats system.top_partitions` ("Space used (live)").
- Guard: `grep -c "Rejected an oversized mutation" $WORK/nX/logs/system.log` and
  `nodetool -p P sjk mx -b org.apache.cassandra.metrics:type=CommitLog,name=OverSizedMutations -f Count -mg`.
- Not observable: the exact save time inside the hour (poll); commit-log bytes per save (shared segments).

**B3e. Procedure.**
1. Setup and start both nodes; confirm N = 10 via `sjk mx ... -mg`.
2. B3c schema + load + flush. `nodetool -p 7199 repair --full ks t`.
3. Wait until `last_update` is present (poll every 60 s; expected by t0 + 60 min + 1 min). Measure (B3d) on both nodes → `save1-nX.txt`.
4. Set N = 10,000 on both nodes; `nodetool -p 7199 repair --full ks t`; wait until `last_update` changes (next save, t0 + 120 min); measure → `save2-nX.txt`.
5. Set N = 20,000 on both nodes; repair; wait past t0 + 180 min + 2 min; measure → `save3-nX.txt` (expect `last_update` unchanged, rejection logged).
6. Shutdown, cleanup (B4).

**B3f. Predictions.** Per node:

| Step | N | tuples in row | Data.db of `system.top_partitions` (after compact) | rejection count |
|---|---|---|---|---|
| save1 | 10 | 10 | ~10 KB + base (other tables' rows, < 100 KB) | 0 |
| save2 | 10,000 | 10,000 | ~10.2 MB (×0.6–1.0 after LZ4) | 0 |
| save3 | 20,000 | 10,000 (unchanged) | unchanged from save2 (±5%) | ≥ 1 |

The in-memory holder at save3 holds 20,000 (confirm with `nodetool tablestats -F json ks.t` count, optional).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| tuples = N and Data.db ≈ N × 1,020 B for N = 10 and 10,000; save3 rejected, row unchanged | claim confirmed |
| tuples > N in any step | claim refuted |
| save3 writes ~20 MB row (no rejection) | no mutation-size guard on this path: disk follows N without the 16 MiB ceiling (claim's ceiling part refuted) |
| tuples = N but Data.db does not grow between save1 and save2 | storage not as estimated (compression/format); re-check uncompressed length via `sstablemetadata` |
| no `last_update` after 65 min | save not scheduled / tracker not created (system or tool table?); not confirmed |

**B3h. Controls.** P > every N so N is what limits the list; random hex keys defeat compression; flush + major
compaction of `system.top_partitions` before every reading so only the latest version is counted; both nodes hold
all data (RF=2) and must agree; the save3 step shows that a larger N does not always produce more disk (guard).

**B4. Risks and cleanup.** All data under `$WORK` on local disk (< 1 GB per node); nothing written to the shared
source tree. Stop with `kill $(cat $WORK/n1/pid) $(cat $WORK/n2/pid)`, confirm `pgrep -f CassandraDaemon` lists
none of this run's PIDs (kill -9 if needed), `pgrep -f junit` empty after the unit tier, then
`rm -rf $WORK/n1 $WORK/n2 $WORK/deletes.cql` and `$WORK/src` when done. The run is long (≈ 3.5 h): keep it in a
`tmux`/`nohup` shell and make sure the nodes are stopped even if the session ends.

## C. Sources read

- src/java/org/apache/cassandra/config/Config.java (1140-1160)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (5070-5120, 898-901, 2827-2830)
- src/java/org/apache/cassandra/metrics/TopPartitionTracker.java (whole file)
- src/java/org/apache/cassandra/db/SystemKeyspace.java (170, 425-445, 1955-2003)
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (560-575, 3575-3607, 251)
- src/java/org/apache/cassandra/db/Mutation.java (165-178)
- src/java/org/apache/cassandra/db/MutationExceededMaxSizeException.java (36-60)
- src/java/org/apache/cassandra/db/IMutation.java (31)
- src/java/org/apache/cassandra/db/commitlog/CommitLog.java (296-310)
- src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java (93)
- src/java/org/apache/cassandra/metrics/CommitLogMetrics.java (48, 55)
- src/java/org/apache/cassandra/metrics/TableMetrics.java (139, 678)
- src/java/org/apache/cassandra/concurrent/ScheduledThreadPoolExecutorPlus.java (92-100)
- src/java/org/apache/cassandra/concurrent/ExecutionFailure.java (96-124)
- src/java/org/apache/cassandra/db/marshal/TupleType.java (366-370)
- src/java/org/apache/cassandra/repair/ValidationManager.java (105-180)
- src/java/org/apache/cassandra/service/StorageService.java (7540-7580)
- test/unit/org/apache/cassandra/db/TopPartitionTrackerTest.java (140-200, 311-314)
- test/conf/cassandra.yaml (commitlog_segment_size)
- conf/cassandra.yaml (652-660 and grep)
- NEWS.txt (410-425)

## D. Stage-4 feedback

none yet
