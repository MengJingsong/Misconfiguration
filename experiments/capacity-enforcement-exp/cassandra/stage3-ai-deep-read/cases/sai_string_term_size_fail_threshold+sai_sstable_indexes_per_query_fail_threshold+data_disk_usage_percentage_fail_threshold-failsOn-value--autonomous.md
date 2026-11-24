# sai_string_term_size_fail_threshold + sai_sstable_indexes_per_query_fail_threshold + data_disk_usage_percentage_fail_threshold — verification solution  <!-- file: cases/sai_string_term_size_fail_threshold+sai_sstable_indexes_per_query_fail_threshold+data_disk_usage_percentage_fail_threshold-failsOn-value--autonomous.md -->

This target is a capacity set of three places. In this file, "the if statement" means the given line.
The three lines are three different guardrails. All three use the same check,
`Threshold.failsOn(value, state)` ([`Threshold.java:111-114`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Threshold.java#L111-L114)).
Each one compares its own operand against its own `*_fail_threshold` configuration entry. So this case
gives one verdict per place, P1 to P3, and one shared solution with a sub-experiment for each place.

| Field | Value |
|---|---|
| Entry pointer | **P1** [`StorageAttachedIndex.java:823`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java#L823) `if (maxTermSizeGuardrail.failsOn(term.remaining(), state))`; **P2** [`QueryController.java:331`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L331) `if (Guardrails.saiSSTableIndexesPerQuery.failsOn(referencedIndexes, null))`; **P3** [`DiskUsageMonitor.java:194`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java#L194) `if (Guardrails.localDataDiskUsage.failsOn(usagePercentage, null))` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24, autonomous |
| Estimate | **P1 `positive`**: a term larger than `sai_string_term_size_fail_threshold` (or the frozen or vector variant) is left out of the SAI memtable trie and the SSTable index, so the bytes each term adds to SAI heap and disk are capped by the threshold. **P2 `negative`**: the threshold caps how many SSTable indexes one query expression may reference. It aborts the query, but it does not bound how many SSTables or indexes exist or how much memory or disk they use, and the per-query cost it saves is small and short-lived. **P3 `positive` (conditional)**: when the data-disk usage percentage passes the threshold, the node is marked FULL and coordinators reject later CQL writes from ordinary users. This holds only with an authenticating authenticator and for writes that are not single-statement LWTs. Under the default `AllowAllAuthenticator` every client counts as a superuser and nothing is rejected. |
| Ground | P2 only: the operand is a count of index handles referenced by one read (`QueryController.java:326-329`). The references are taken before the check (`QueryViewBuilder.java:98-117`). The check stops only the building of per-index search iterators (`QueryController.java:260-312`). It changes neither the number of SSTables or SAI components on disk nor what they keep resident. Those follow flush and compaction, and the guardrail's stated reason is performance (`Guardrails.java:510`). |

## A. Constraint trace

**A1. The constraint.**

- **P1: `sai_string_term_size_fail_threshold`.** A configuration entry declared at
  [`Config.java:942`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L942).
  It is a `DataStorageSpec.LongBytesBound` with default `8KiB`. Its siblings are `sai_frozen_term_size_fail_threshold`
  (`Config.java:944`, `8KiB`) and `sai_vector_term_size_fail_threshold` (`Config.java:946`, `32KiB`). The warn thresholds
  are 1KiB, 1KiB and 16KiB (`Config.java:941,943,945`). Which of the three guardrails applies at line 823 depends on the
  indexed column's type (`StorageAttachedIndex.java:207-210`): vector, then frozen, then string. The guardrail objects are
  `Guardrails.saiStringTermSize`, `saiFrozenTermSize` and `saiVectorTermSize` (`Guardrails.java:520-551`). They read the
  value as bytes through `sizeToBytes`, which maps null to -1 (`Guardrails.java:1442-1445`). The value can be set in the
  yaml (`conf/cassandra.yaml:2246-2255`, commented defaults), through JMX
  (`GuardrailsMBean.setSaiStringTermSizeThreshold(warn, fail)`, `GuardrailsMBean.java:824`) or with
  `nodetool setguardrailsconfig`. The field is `volatile` and read on every call, so a change takes effect without a
  restart.
- **P2: `sai_sstable_indexes_per_query_fail_threshold`.** A configuration entry declared at
  [`Config.java:940`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L940).
  It is an `int` count with default `-1`, which disables it. The warn threshold defaults to `32` (`Config.java:939`).
  It is validated at `GuardrailsOptions.java:92-95`. It can be set in the yaml (`conf/cassandra.yaml:2240-2243`) or
  through JMX (`setSaiSSTableIndexesPerQueryThreshold(warn, fail)`, `GuardrailsMBean.java:800`), and takes effect live.
  The guardrail object is `Guardrails.saiSSTableIndexesPerQuery` (`Guardrails.java:508-515`).
- **P3: `data_disk_usage_percentage_fail_threshold`.** A configuration entry declared at
  [`Config.java:927`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L927).
  It is an `int` percentage in [1, 100], default `-1` (disabled). Its companions are the warn threshold
  (`Config.java:926`) and `data_disk_usage_max_disk_size` (`Config.java:928`, default null). The latter turns the
  denominator into a fixed size instead of used plus free space. All are validated at `GuardrailsOptions.java:86-87`.
  They can be set in the yaml (`conf/cassandra.yaml:2191-2210`) or through JMX
  (`setDataDiskUsagePercentageThreshold(warn, fail)`, `GuardrailsMBean.java:644`, and
  `setDataDiskUsageMaxDiskSize`, `GuardrailsMBean.java:659`), and take effect live. The monitor period is the JVM
  property `cassandra.disk_usage.monitor_interval_ms`, default 30000 (`CassandraRelevantProperties.java:200`), read once
  at start, so a change needs a restart. The guardrail object is `Guardrails.localDataDiskUsage`, a
  `PercentageThreshold` (`Guardrails.java:432-442`).

These rules are common to all three. `failsOn` returns `enabled(state) && compare(value, failValue(state))`
(`Threshold.java:111-114`). `compare` is `value > threshold`, and a fail value of 0 or less becomes `Long.MAX_VALUE`
(`MaxThreshold.java:50-60`). `enabled(state)` needs `DatabaseDescriptor.isDaemonInitialized()` and either
`state == null` or an ordinary user (`Guardrail.java:93-96`). An ordinary user is one that is neither super nor system,
and **any user counts as super when the authenticator does not require authentication**
(`ClientState.java:594-605`). At all three given lines the state is `null` (P1 is always called with `null` from its
callers, see A3), so the check applies whoever wrote the data.

**A2. What it caps.**

- **P1:** the bytes of one SAI index term, `term.remaining()`. This is heap, or off-heap if the memtable allocation type
  is off-heap, in the memtable index's `InMemoryTrie` (`TrieMemoryIndex.java:218-240`), counted in the memtable's on-heap
  size (`StorageAttachedIndex.java:1002-1007`). It is also disk, in the per-SSTable SAI components (`SSTableIndexWriter.java:205-208`).
  The cap is per term, not a total.
- **P2:** the largest number of SSTable indexes that any one indexed expression of a read references, `referencedIndexes`
  (`QueryController.java:326-329`). The resource is the heap of iterators built for a single query: nothing persistent,
  and no disk.
- **P3:** `ceil(100 * used / total)` (`DiskUsageMonitor.java:107-108`). Here `used` is the sum of `FileUtils.folderSize`
  over all data directories (`Directories.java:787-790`) plus the live data size of every memtable
  (`DiskUsageMonitor.java:154-155`, `:168-180`). `total` is `used + usable space of the data file stores`, capped by
  `data_disk_usage_max_disk_size` (`DiskUsageMonitor.java:138-152`). The resource is disk in the data directories.

**A3. Mechanism.**

*P1: [`StorageAttachedIndex.java:823`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java#L823)*

1. Client path (not the given line). `validate(PartitionUpdate, ClientState)` (`StorageAttachedIndex.java:521-530`) calls
   `validateTermSizeForRow(..., isClientMutation=true, state)`. That checks once more against the warn threshold
   (`:795`), and `validateTermSize` then calls `guard(...)` with the client state (`:817-821`). For an ordinary user a term
   above the fail threshold throws `GuardrailViolatedException` (`Guardrail.java:139-140`). For a superuser, a system
   client, or any client under `AllowAllAuthenticator`, `enabled(state)` is false and the write is accepted whatever its
   size.
2. Index path (the given line). Every indexer calls `validateTermSize(key, term, false, null)`: the memtable trie
   (`TrieMemoryIndex.java:220`, once for each analyzed token, `:101-113`), the vector graph
   (`VectorMemoryIndex.java:90`), and the SSTable writer used for compaction and index build
   (`SSTableIndexWriter.java:207`, on the whole cell value before analysis, `:220-232`). At line 823, a term larger than
   the fail threshold makes the method log `TERM_OVERSIZE_MESSAGE` through a NoSpamLogger, at most once a minute
   (`:145`, `:147`, `:823-830`), and return `false`. The caller then skips the term: no trie insert and no
   `setMinMaxTerm` (`TrieMemoryIndex.java:220-240`), no graph add (`VectorMemoryIndex.java:90-91`), no segment-builder add
   (`SSTableIndexWriter.java:207-208`).
3. Effect: the row is stored in the base table but cannot be found through the index by that term. The SAI heap and disk
   for that term are zero. A term at or below the threshold is indexed in full.
4. Overshoot and bypasses. The cap is per term, so the total index size is not bounded. Any number of terms just under
   the threshold are indexed. With an analyzer, the memtable checks each token while the SSTable writer checks the whole
   cell. A long text with small tokens is therefore indexed from the memtable but skipped entirely at compaction or build.
   The two paths disagree in that direction only; neither path indexes more than the other allows.

*P2: [`QueryController.java:331`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L331)*

1. `getIndexQueryResults` builds a `QueryView` (`QueryController.java:253`). This references every matching SSTable index
   (`QueryViewBuilder.java:98-117`), chosen by term range and key range (`:120-140`).
2. `maybeTriggerGuardrails(queryView)` (`QueryController.java:260`, `:323-342`) takes
   `referencedIndexes = max over expressions of sstableIndexes.size()`. Line 331 compares that with the fail threshold.
3. On fail: a trace message, a `TOO_MANY_REFERENCED_INDEXES_FAIL` message parameter, and a
   `QueryReferencingTooManyIndexesException`, which is a `RejectException` (`QueryController.java:333-340`). The `catch`
   cleans up the builder and releases the references (`:314-318`). On warn: only a message parameter (`:342-345`).
   Otherwise one `IndexSearchResultIterator` is built for each expression over every referenced index
   (`QueryController.java:262-312`, `IndexSearchResultIterator.java:71-110`).
4. Overshoot: the check uses the maximum, not the sum, over expressions. A query with E indexed expressions can therefore
   reference up to E × threshold SSTable indexes. Memtable indexes are not counted. The default fail value is -1, so it
   is off. Nothing here limits how many SSTables or SAI components exist.

*P3: [`DiskUsageMonitor.java:194`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java#L194)*

1. `DiskUsageBroadcaster.startBroadcasting()` is called from `StorageService.java:1236` and runs `DiskUsageMonitor.start`.
   That schedules a task every `cassandra.disk_usage.monitor_interval_ms` (`DiskUsageMonitor.java:80-96`). The task calls
   `updateLocalState(getDiskUsage(), notifier)` only while the guardrail is enabled.
2. `updateLocalState` (`:105-119`) works out `percentageCeiling` and calls `getState` (`:189-200`). Line 194 returns
   `FULL` when `percentageCeiling > fail`; otherwise STUFFED when above warn, else SPACIOUS. It also calls
   `localDataDiskUsage.guard(...)`, which with `state == null` only logs and does not throw (`Guardrail.java:124-140`).
3. When the state changes, the notifier gossips `ApplicationState.DISK_USAGE` (`DiskUsageBroadcaster.java:90-98`). The
   local subscriber is told at once (`Gossiper.java:2245-2259`), and `DiskUsageBroadcaster.onChange` stores it
   (`DiskUsageBroadcaster.java:103-120`).
4. Enforcement is at the coordinator. `ModificationStatement.validateDiskUsage` (`ModificationStatement.java:285-302`),
   called for unconditional writes (`:517`) and for every statement of a batch (`BatchStatement.java:420`), calls
   `Guardrails.replicaDiskUsage.guard(replica)` for each write replica (`Guardrails.java:448-456`). A FULL replica makes
   the write fail with "Write request failed because disk usage exceeds failure threshold", but **only if
   `replicaDiskUsage.enabled(state)`**, which means an ordinary user (`:288`).
5. Bypasses and overshoot:
   - superusers, system clients, and every client under `AllowAllAuthenticator` (`ClientState.java:604`);
   - single-statement conditional writes (LWT): `executeWithCondition` is chosen at `ModificationStatement.java:500-502`
     and never calls `validateDiskUsage`;
   - all non-CQL writers: compaction (it can double data), streaming, repair, hint and batchlog replay, and snapshots
     (snapshots are counted in `used`);
   - writes accepted during the gap of up to one monitor interval;
   - commit log, hints and saved caches on other directories are not counted (`conf/cassandra.yaml:2192-2194`).

**A4. Other consumers.**

- P1: the base table still stores and writes the whole value (memtable, commit log, SSTables). The client-side guard
  (`:819`) protects only ordinary users. The vector graph's own heap per vector depends on dimensions, not on this check.
- P2: the resident SAI state per SSTable (segment metadata, file handles, `IndexFileCacheBytes`,
  `IndexMetrics.java:56-60`), the SSTables themselves, and memtable indexes.
- P3: commit log (`commitlog_total_space`), hints, saved caches, compaction temporary space, and snapshots and backups.
  Snapshots and backups are inside `used` but are not stopped by the guardrail.

**A5. Evidence beyond the source.**

- `NEWS.txt:211-212`: the 5.0 guardrail list includes "maximum referenced SAI indexes" and "size of terms written to an
  SAI index".
- `CHANGES.txt:374`: "SAI in-memory index should check max term size" (CASSANDRA-18926,
  https://issues.apache.org/jira/browse/CASSANDRA-18926; not opened). This explains why the memtable path calls line 823.
- `CHANGES.txt:900`: data disk usage guardrail (CASSANDRA-17150, https://issues.apache.org/jira/browse/CASSANDRA-17150;
  not opened).
- `CHANGES.txt:60`: CASSANDRA-21057 (not opened). This is the source of the disable path at `DiskUsageMonitor.java:84-89`.
- `conf/cassandra.yaml:2191-2199`: the disk guardrail is described as "rejecting user writes" so that background
  processes do not fail.
- Tests:
  - `test/unit/org/apache/cassandra/db/guardrails/GuardrailSaiStringTermSizeTest.java`: client-path thresholds; index
    build keeps a term above warn but below fail.
  - `test/unit/org/apache/cassandra/db/guardrails/GuardrailDiskUsageTest.java:484-560`: FULL rejects ordinary user
    inserts and batches; superuser and system clients are excluded.
- `CassandraRelevantProperties.java:44`: duplicate yaml keys are allowed by default (last wins). The cluster tier relies
  on this to append overrides.
- JDK API relied on (not opened in this session):
  `com.sun.management.ThreadMXBean.getThreadAllocatedBytes(long)`,
  https://docs.oracle.com/en/java/javase/11/docs/api/jdk.management/com/sun/management/ThreadMXBean.html.

## B. Verification solution

**B1. Claim under test.**

- **P1:** with term size S above `sai_string_term_size_fail_threshold`, the SAI memtable index bytes, the SAI on-disk
  bytes and the node heap gained per indexed row stay near zero. Raising the threshold above S makes them grow by at
  least S per row.
- **P2 (negative):** `sai_sstable_indexes_per_query_fail_threshold` does not change node disk usage, SAI disk usage or
  heap retained after GC. It only makes queries over more than the threshold's number of SSTable indexes fail, and the
  heap it saves is the transient cost of one query.
- **P3:** with authentication on, writes by an ordinary user stop being accepted once data-directory usage (plus
  memtables) passes `fail` % of the configured total. Data-directory size then plateaus near that percentage, while
  superuser and LWT writes continue past it.

### B2. Unit tier

**B2a. Environment and build.** JDK 11 and Ant. Work in a copy on local disk, never in the shared tree:

```
export W=/mydata/s4-o207            # local disk, >= 10 GiB free
mkdir -p $W && rsync -a <pinned cassandra-5.0.9 tree>/ $W/cassandra-5.0.9/
export SRC=$W/cassandra-5.0.9
cd $SRC && ant clean jar build-test 2>&1 | tail -5     # needs JDK 11 on PATH
```

Add one test class, `$SRC/test/unit/org/apache/cassandra/db/guardrails/CapacitySetVerifyTest.java` (listed in B2e).
It extends `GuardrailTester` so that it gets an ordinary-user, a superuser and a system `ClientState` with
authentication on (`GuardrailTester.java:112-150`). The JVM options are the ones `testsome` uses (test config
`test/conf/cassandra.yaml`). Data goes under `$SRC/build/test/cassandra/`.

**B2b. Knobs.** Each is set live through `Guardrails.instance` (via `guardrails()`).

- P1: `sai_string_term_size_fail_threshold` ∈ {`8KiB` (default), `1MiB`}, warn `1KiB`. Term size S ∈ {4096 (below both),
  65536 (between the two)}.
- P2: `sai_sstable_indexes_per_query_fail_threshold` ∈ {`-1`, `16`}, warn `-1`, at N ∈ {8, 32, 128} SSTables. 16 sits
  between 8 and 32.
- P3: `data_disk_usage_max_disk_size = 512MiB`, `data_disk_usage_percentage_fail_threshold` ∈ {`50`, `-1`}, warn 40
  (or -1 when fail is -1). Writer ∈ {ordinary user, superuser, ordinary user with `IF NOT EXISTS`}.

**B2c. Workload.**

- P1: 200 rows `(k int, v text)` per cell of the grid, each `v` S random lowercase bytes, written as the superuser. The
  client guard is therefore skipped and only line 823 decides. At S = 65536 the trie would receive
  200 × 64 KiB = 12.5 MiB if the term were indexed. S = 4096 is the control below every threshold
  (800 KiB). For the 1MiB/65536 cell, the threshold is lowered to 8KiB afterwards and the table compacted, to exercise
  `SSTableIndexWriter.java:207`. As a client-path control, one 64 KiB insert is made as the ordinary user at 8KiB.
- P2: one table `(k int PRIMARY KEY, v int)` with SAI on `v` and compaction disabled. Each round inserts 10 rows with
  v = 0..9 and then flushes, so every SSTable's term range contains 5 and `SELECT k ... WHERE v = 5` references all N
  indexes. N reaches 8, then 32, then 128 (8 < 16 < 32 < 128).
- P3: `(k int PRIMARY KEY, v blob)` with compression off. Rounds of 1000 inserts of 4 KiB random blobs (about 4 MiB),
  each followed by a flush, then `getDiskUsage()` and `updateLocalState()`. That last call is what the monitor task does,
  run here by hand instead of on its 30 s timer. Up to 100 rounds (about 400 MiB). With fail = 50 of 512 MiB, FULL
  should appear once used > 256 MiB, which is reachable after about (256 MiB − baseline) / 4 MiB ≈ 55–64 rounds.

**B2d. Observables and instruments.** Each test prints `VERIFY,...` lines.

- P1:
  - `StorageAttachedIndex.memtableIndexManager().estimatedMemIndexMemoryUsed()`: the sum of bytes the trie reports
    (`TrieMemoryIndex.java:94-122`), which is what feeds the `MemtableIndexBytes` gauge.
  - `StorageAttachedIndex.diskUsage()`, after flush and after compaction.
  - the hit count of an index query for the first inserted value.
  - the base table's `liveDiskSpaceUsed`.
  - the outcome of the ordinary-user insert.
- P2:
  - `view().getIndexes().size()`, the result rows, the exception class and message.
  - the median allocated bytes of the calling thread per query (`com.sun.management.ThreadMXBean`) over 50 runs after
    20 warm-ups. Internal execution runs the local read on the calling thread.
  - `liveDiskSpaceUsed` and `diskUsage()`.
- P3, per round: accepted and rejected inserts, the error class, `getDiskUsage()` ratio, `DiskUsageMonitor.state()`,
  the summed `getRawSize()` of all data directories, and the table's `liveDiskSpaceUsed`.
- Not directly observable here: the exact time a background monitor would fire. That timing is covered in B3.

**B2e. Procedure.**

1. Create `$SRC/test/unit/org/apache/cassandra/db/guardrails/CapacitySetVerifyTest.java`:

```java
package org.apache.cassandra.db.guardrails;

import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.Consumer;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.Directories;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.gms.ApplicationState;
import org.apache.cassandra.index.sai.StorageAttachedIndex;
import org.apache.cassandra.service.ClientState;
import org.apache.cassandra.service.StorageService;
import org.apache.cassandra.service.disk.usage.DiskUsageBroadcaster;
import org.apache.cassandra.service.disk.usage.DiskUsageMonitor;
import org.apache.cassandra.service.disk.usage.DiskUsageState;
import org.apache.cassandra.utils.FBUtilities;

public class CapacitySetVerifyTest extends GuardrailTester
{
    @BeforeClass
    public static void noCopies()
    {
        // test/conf has incremental_backups: true; hard links would be double-counted by folderSize
        DatabaseDescriptor.setIncrementalBackupsEnabled(false);
        DatabaseDescriptor.setAutoSnapshot(false);
    }

    private static void out(String s) { System.out.println("VERIFY," + s); }

    private static long threadAllocated()
    {
        return ((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean())
               .getThreadAllocatedBytes(Thread.currentThread().getId());
    }

    private static ByteBuffer ascii(int n)
    {
        byte[] b = new byte[n];
        ThreadLocalRandom r = ThreadLocalRandom.current();
        for (int i = 0; i < n; i++) b[i] = (byte) ('a' + r.nextInt(26));
        return ByteBuffer.wrap(b);
    }

    private static ByteBuffer blob(int n)
    {
        byte[] b = new byte[n];
        ThreadLocalRandom.current().nextBytes(b);
        return ByteBuffer.wrap(b);
    }

    private StorageAttachedIndex sai(String name)
    {
        return (StorageAttachedIndex) getCurrentColumnFamilyStore().indexManager.getIndexByName(name);
    }

    // P1: StorageAttachedIndex.java:823
    @Test
    public void p1TermSize() throws Throwable
    {
        for (String fail : new String[]{ "8KiB", "1MiB" })
            for (int size : new int[]{ 4096, 65536 })
            {
                guardrails().setSaiStringTermSizeThreshold("1KiB", fail);
                createTable("CREATE TABLE %s (k int PRIMARY KEY, v text)");
                String idx = createIndex("CREATE INDEX ON %s(v) USING 'sai'");
                disableCompaction();
                ByteBuffer probe = null;
                for (int i = 0; i < 200; i++)
                {
                    ByteBuffer v = ascii(size);
                    if (i == 0) probe = v.duplicate();
                    execute(superClientState, "INSERT INTO %s (k, v) VALUES (" + i + ", ?)", Collections.singletonList(v));
                }
                long memIdx = sai(idx).memtableIndexManager().estimatedMemIndexMemoryUsed();
                int hits = execute("SELECT k FROM %s WHERE v = ?", probe).size();
                flush();
                out("P1,fail=" + fail + ",termBytes=" + size + ",rows=200,memtableIndexBytes=" + memIdx
                    + ",probeHits=" + hits + ",saiDiskBytes=" + sai(idx).diskUsage()
                    + ",baseLiveDiskBytes=" + getCurrentColumnFamilyStore().metric.liveDiskSpaceUsed.getCount());
                if (fail.equals("1MiB") && size == 65536)
                {
                    guardrails().setSaiStringTermSizeThreshold("1KiB", "8KiB");
                    compact();
                    out("P1-compaction,fail=8KiB-after-1MiB,termBytes=65536,saiDiskBytes=" + sai(idx).diskUsage()
                        + ",probeHits=" + execute("SELECT k FROM %s WHERE v = ?", probe).size());
                }
            }
        guardrails().setSaiStringTermSizeThreshold("1KiB", "8KiB");
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v text)");
        createIndex("CREATE INDEX ON %s(v) USING 'sai'");
        String outcome;
        try { execute(userClientState, "INSERT INTO %s (k, v) VALUES (0, ?)", Collections.singletonList(ascii(65536))); outcome = "accepted"; }
        catch (RuntimeException e) { outcome = e.getClass().getSimpleName(); }
        out("P1-client,user=ordinary,fail=8KiB,termBytes=65536,outcome=" + outcome);
    }

    // P2: QueryController.java:331
    @Test
    public void p2IndexesPerQuery() throws Throwable
    {
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v int)");
        String idx = createIndex("CREATE INDEX ON %s(v) USING 'sai'");
        disableCompaction();
        int made = 0;
        for (int checkpoint : new int[]{ 8, 32, 128 })
        {
            while (made < checkpoint)
            {
                for (int j = 0; j < 10; j++)
                    execute("INSERT INTO %s (k, v) VALUES (?, ?)", made * 10 + j, j);
                flush();
                made++;
            }
            long liveDisk = getCurrentColumnFamilyStore().metric.liveDiskSpaceUsed.getCount();
            long saiDisk = sai(idx).diskUsage();
            int viewSize = sai(idx).view().getIndexes().size();
            for (int fail : new int[]{ -1, 16 })
            {
                guardrails().setSaiSSTableIndexesPerQueryThreshold(-1, fail);
                List<Long> allocs = new ArrayList<>();
                String outcome = "ok";
                int rows = -1;
                for (int rep = 0; rep < 70; rep++)
                {
                    long before = threadAllocated();
                    try { rows = execute("SELECT k FROM %s WHERE v = 5").size(); }
                    catch (RuntimeException e) { outcome = e.getClass().getSimpleName() + ":" + e.getMessage(); }
                    long after = threadAllocated();
                    if (rep >= 20) allocs.add(after - before);
                }
                Collections.sort(allocs);
                out("P2,sstables=" + checkpoint + ",viewIndexes=" + viewSize + ",fail=" + fail + ",rows=" + rows
                    + ",medianAllocBytes=" + allocs.get(allocs.size() / 2) + ",baseLiveDiskBytes=" + liveDisk
                    + ",saiDiskBytes=" + saiDisk + ",outcome=" + outcome.replace(',', ';'));
            }
        }
        guardrails().setSaiSSTableIndexesPerQueryThreshold(32, -1);
    }

    // P3: DiskUsageMonitor.java:194
    @Test
    public void p3DiskUsage() throws Throwable
    {
        Consumer<DiskUsageState> notifier = s -> DiskUsageBroadcaster.instance.onChange(
            FBUtilities.getBroadcastAddressAndPort(), ApplicationState.DISK_USAGE,
            StorageService.instance.valueFactory.diskUsage(s.name()));
        Object[][] variants = { { "user", 50 }, { "super", 50 }, { "user", -1 }, { "user-lwt", 50 } };
        for (Object[] variant : variants)
        {
            String who = (String) variant[0];
            int fail = (Integer) variant[1];
            ClientState state = who.equals("super") ? superClientState : userClientState;
            createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob) WITH compression = {'enabled': false}");
            disableCompaction();
            guardrails().setDataDiskUsageMaxDiskSize("512MiB");
            guardrails().setDataDiskUsagePercentageThreshold(fail > 0 ? 40 : -1, fail);
            DiskUsageMonitor.instance.updateLocalState(DiskUsageMonitor.instance.getDiskUsage(), notifier);
            String insert = "INSERT INTO %s (k, v) VALUES (?, ?)" + (who.equals("user-lwt") ? " IF NOT EXISTS" : "");
            for (int round = 0; round < 100; round++)
            {
                int ok = 0, rejected = 0;
                String err = "";
                for (int i = 0; i < 1000; i++)
                {
                    try { execute(state, insert, Arrays.asList(Int32Type.instance.decompose(round * 1000 + i), blob(4096))); ok++; }
                    catch (RuntimeException e) { rejected++; err = e.getClass().getSimpleName(); }
                }
                flush();
                double ratio = DiskUsageMonitor.instance.getDiskUsage();
                DiskUsageMonitor.instance.updateLocalState(ratio, notifier);
                long raw = 0;
                for (Directories.DataDirectory d : Directories.dataDirectories.getAllDirectories())
                    raw += d.getRawSize();
                out("P3,who=" + who + ",fail=" + fail + ",round=" + round + ",accepted=" + ok + ",rejected=" + rejected
                    + ",err=" + err + ",ratio=" + ratio + ",state=" + DiskUsageMonitor.instance.state()
                    + ",dataDirRawBytes=" + raw
                    + ",tableLiveBytes=" + getCurrentColumnFamilyStore().metric.liveDiskSpaceUsed.getCount());
                if (rejected == 1000) break;
            }
            execute("DROP TABLE %s");
            guardrails().setDataDiskUsagePercentageThreshold(-1, -1);
            DiskUsageMonitor.instance.updateLocalState(0.0, notifier);
        }
        guardrails().setDataDiskUsageMaxDiskSize(null);
    }
}
```

2. Run each method on its own and keep the output:

```
cd $SRC
for m in p1TermSize p2IndexesPerQuery p3DiskUsage; do
  ant testsome -Dtest.name=org.apache.cassandra.db.guardrails.CapacitySetVerifyTest -Dtest.methods=$m 2>&1 | tail -20
  grep -h 'VERIFY,' build/test/output/TEST-org.apache.cassandra.db.guardrails.CapacitySetVerifyTest*.xml > $W/unit-$m.csv
done
```

   (The test-output file name is `TEST-${test.name}-${test.methods}.xml`, `build.xml:608`. If the grep finds nothing,
   use `grep -rh 'VERIFY,' build/test/` instead.)
3. Check that no test JVM is left: `pgrep -f CapacitySetVerifyTest` should print nothing.

**B2f. Predictions.**

- P1:
  - fail 8KiB, S 65536: `memtableIndexBytes` < 256 KiB, `probeHits` = 0, `saiDiskBytes` < 1 MiB.
  - fail 1MiB, S 65536: `memtableIndexBytes` ≥ 12.5 MiB (13,107,200), `probeHits` = 1, `saiDiskBytes` ≥ 10 MiB.
  - S 4096: indexed in both settings. `memtableIndexBytes` ≥ 800 KiB and `probeHits` = 1, equal within ±10% across the
    two fail values.
  - After compaction at 8KiB: `saiDiskBytes` < 1 MiB and `probeHits` = 0.
  - `baseLiveDiskBytes` for S 65536 is the same within ±10% at both fail values (the base data is not capped).
  - `P1-client` outcome = `GuardrailViolatedException`.
- P2:
  - `viewIndexes` = 8, 32, 128.
  - fail -1: `rows` = N and outcome ok at every N.
  - fail 16: N = 8 is ok. N = 32 and 128 give `QueryReferencingTooManyIndexesException` with a message containing
    `(32)` or `(128)` and `max allowed is 16`.
  - `baseLiveDiskBytes` and `saiDiskBytes` grow with N and are printed once per N, the same for both fail values.
  - `medianAllocBytes` at fail -1 grows roughly linearly with N, with a slope of at most 64 KiB per referenced index
    (≤ 8 MiB at N = 128). At fail 16 and N ≥ 32 it is no larger than at fail -1.
- P3, with baseline B0 = the first round's `dataDirRawBytes` minus about 4 MiB:
  - user/50: state goes SPACIOUS → STUFFED (above 204.8 MiB) → FULL (above 256 MiB). The round after FULL has
    `rejected` = 1000 and `err` = `GuardrailViolatedException`, and the loop stops. The final `dataDirRawBytes` is at
    most 256 MiB + 4 MiB plus one round of flush overhead (< 2 MiB).
  - super/50: FULL is reached, but `accepted` = 1000 in every round. `dataDirRawBytes` reaches B0 + about 400 MiB, past
    the 256 MiB limit.
  - user/-1: state `NOT_AVAILABLE` and no rejections across 100 rounds.
  - user-lwt/50: FULL is reached and `accepted` = 1000 in every round (the LWT bypass).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| P1: 65 KiB terms give ~0 index bytes and 0 hits at 8KiB, but ≥ 12.5 MiB and 1 hit at 1MiB | P1 claim confirmed: index bytes follow the threshold |
| P1: index bytes ≥ 12.5 MiB at 8KiB | P1 claim wrong: line 823 does not stop oversize terms reaching the trie |
| P1: compaction at 8KiB keeps ≥ 10 MiB SAI disk | the SSTable-writer path does not enforce it; P1 is only partly true (memtable only) |
| P1: the 4 KiB control differs between the fail values | an effect other than the threshold; P1 not confirmed |
| P2: disk and SAI bytes the same for -1 and 16 at every N, only the query outcome changes, and per-index allocation ≤ 64 KiB | P2 negative confirmed: usage flat while the positive control (N) moves it |
| P2: disk or SAI bytes differ between -1 and 16 | usage follows the knob: P2 negative refuted |
| P2: per-query allocation slope > 1 MiB per referenced index | the transient cost is memory-significant: P2 negative refuted for heap |
| P2: N = 32 at fail 16 is not rejected (limit never reached), or disk does not grow with N (control did not move) | not confirmed |
| P3: user/50 stops at ≈256 MiB while super/50 and user-lwt/50 run past it, and user/-1 never rejects | P3 confirmed, including the bypasses |
| P3: user/50 still accepting after state = FULL | P3 claim wrong |
| P3: FULL first reported at a used value off by more than 1% of 512 MiB from 256 MiB | the formula traced in A2 is wrong |

**B2h. Controls.**

- P1: the S = 4096 rows are identical across thresholds, and the probe query shows that index content changed, not just
  the accounting.
- P2: N is varied while the threshold is fixed; that is the positive control showing that the instruments see changes
  in disk and SAI usage.
- P3: the knob at -1 and the two bypass writers show that the rejections come from line 194's state.
- Incremental backups and auto-snapshot are off, so hard links do not inflate `getRawSize`.

### B3. Cluster tier

**B3a. Environment and build.** One Linux node, JDK 11, built from `$SRC` (B2a) with `ant jar`. Everything goes under
`$W/n1` on local disk. Before starting, check the ports are free:
`ss -ltn | grep -E ':(7000|7199|9042)\b'` must print nothing.

```
export W=/mydata/s4-o207 SRC=$W/cassandra-5.0.9 RUN=$W/n1
fresh() {  # wipe and re-seed the node directory
  rm -rf $RUN && mkdir -p $RUN/{conf,data,commitlog,hints,saved_caches,cdc,logs}
  cp -r $SRC/conf/* $RUN/conf/
  cat >> $RUN/conf/cassandra.yaml <<EOF
cluster_name: 'o207'
data_file_directories: [ $RUN/data ]
commitlog_directory: $RUN/commitlog
hints_directory: $RUN/hints
saved_caches_directory: $RUN/saved_caches
cdc_raw_directory: $RUN/cdc
listen_address: 127.0.0.1
rpc_address: 127.0.0.1
memtable_heap_space: 1024MiB
commitlog_total_space: 512MiB
EOF
}
start() { CASSANDRA_CONF=$RUN/conf CASSANDRA_LOG_DIR=$RUN/logs MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M \
          JVM_EXTRA_OPTS="$EXTRA" $SRC/bin/cassandra -p $RUN/pid > $RUN/logs/stdout 2>&1
          until $SRC/bin/nodetool status 2>/dev/null | grep -q '^UN'; do sleep 2; done; }
stop()  { kill $(cat $RUN/pid); while kill -0 $(cat $RUN/pid) 2>/dev/null; do sleep 1; done; }
```

The appended keys override earlier ones, because duplicate keys are allowed and the last one wins
(`CassandraRelevantProperties.java:44`). Per-experiment keys are appended the same way before `start`.

The workload driver is `$W/load.py`. It needs Python 3.8–3.11 and uses the driver bundled in `lib/`; if that import
fails, run `pip install --user cassandra-driver==3.29.0`.

```python
#!/usr/bin/env python3
# load.py p1 <table> <rows> <bytes> <probe_file> | p2i <round> | p2q <queries>
#         | p3 <user> <pw> <start_key> <max_rows> <lwt 0|1> <csv>
import os, sys, time, random, string, subprocess
sys.path.insert(0, os.environ['SRC'] + '/lib/cassandra-driver-internal-only-3.29.0.zip/cassandra-driver-3.29.0')
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider
from cassandra.concurrent import execute_concurrent_with_args
m = sys.argv[1]
auth = PlainTextAuthProvider(sys.argv[2], sys.argv[3]) if m == 'p3' else None
cl = Cluster(['127.0.0.1'], auth_provider=auth); s = cl.connect(); s.default_timeout = 60
if m == 'p1':
    t, n, size, probe = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
    ps = s.prepare('INSERT INTO verify.%s (k, v) VALUES (?, ?)' % t)
    for i in range(n):
        v = ''.join(random.choices(string.ascii_lowercase, k=size))
        if i == 0: open(probe, 'w').write(v)
        s.execute(ps, (i, v))
elif m == 'p2i':
    r = int(sys.argv[2]); ps = s.prepare('INSERT INTO verify.p2 (k, v) VALUES (?, ?)')
    for j in range(10): s.execute(ps, (r * 10 + j, j))
elif m == 'p2q':
    ok = bad = 0; first = None; rows = None
    for _ in range(int(sys.argv[2])):
        try: rows = len(list(s.execute('SELECT k FROM verify.p2 WHERE v = 5'))); ok += 1
        except Exception as e: bad += 1; first = first or repr(e)[:300]
    print('ok=%d fail=%d rows=%s first_error=%s' % (ok, bad, rows, first))
elif m == 'p3':
    k0, mx, lwt, out = int(sys.argv[4]), int(sys.argv[5]), sys.argv[6] == '1', sys.argv[7]
    ps = s.prepare('INSERT INTO verify.p3 (k, v) VALUES (?, ?)' + (' IF NOT EXISTS' if lwt else ''))
    k, dead = k0, 0
    with open(out, 'a') as f:
        while k < k0 + mx and dead < 3:
            params = [(k + i, os.urandom(4096)) for i in range(2000)]
            res = execute_concurrent_with_args(s, ps, params, concurrency=32, raise_on_first_error=False)
            ok = sum(1 for r in res if r.success)
            err = next((repr(r.result_or_exc)[:200] for r in res if not r.success), '')
            du = int(subprocess.check_output(['du', '-sb', os.environ['RUN'] + '/data']).split()[0])
            f.write('%.1f,%d,%d,%d,%d,%s\n' % (time.time(), k, ok, len(params) - ok, du, err.replace(',', ';')))
            f.flush(); k += 2000; dead = dead + 1 if ok == 0 else 0
cl.shutdown()
```

Helpers:

```
CQL="$SRC/bin/cqlsh 127.0.0.1"
heap() { jcmd $(cat $RUN/pid) GC.run >/dev/null; jcmd $(cat $RUN/pid) GC.heap_info | grep -m1 -i 'used'; }
mx()   { $SRC/bin/nodetool sjk mx -b "$1" -mg -f Value; }
```

**B3b. Knobs.** Each is set in the yaml before a start.

- P1: `sai_string_term_size_fail_threshold` ∈ {`8KiB`, `1MiB`} with `sai_string_term_size_warn_threshold: 1KiB`;
  default `AllowAllAuthenticator`, so line 823 alone decides.
- P2: `sai_sstable_indexes_per_query_fail_threshold` ∈ {`-1`, `50`} with warn `-1`, at N = 200 SSTables.
- P3: `authenticator: PasswordAuthenticator`, `data_disk_usage_max_disk_size: 1GiB`,
  `data_disk_usage_percentage_warn_threshold: 40`, `data_disk_usage_percentage_fail_threshold` ∈ {`50`, `70`}, and
  `EXTRA="-Dcassandra.disk_usage.monitor_interval_ms=1000"`, so the overshoot window is 1 s instead of 30 s.

**B3c. Workload.**

- P1: `verify.p1big` gets 1000 rows of 64 KiB random lowercase text (62.5 MiB of terms). `verify.p1small` gets 1000 rows
  of 4 KiB (3.9 MiB, the control). Both are indexed with SAI. That is about 125 MiB of memtable, under the roughly
  341 MiB flush trigger (1024 MiB × 1/(2+1)), so nothing flushes before measurement.
- P2: `verify.p2 (k int PRIMARY KEY, v int)` with SAI on v and
  `compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'}` (this survives restart). 200 rounds of 10
  rows and `nodetool flush` give N = 200. Then 1000 queries `WHERE v = 5`.
- P3: `verify.p3 (k int PRIMARY KEY, v blob) WITH compression = {'enabled':'false'}`. The ordinary role `writer` inserts
  4 KiB random blobs in chunks of 2000 (8 MiB) at concurrency 32. The target is 262,144 rows (1 GiB); the loader stops
  after 3 fully rejected chunks. The limit is 0.50 × 1 GiB = 512 MiB (or 0.70 × 1 GiB = 716.8 MiB), well within the
  target. Controls in the fail=50 run: the superuser `cassandra` adds 51,200 rows (200 MiB), and `writer` adds 25,600
  LWT rows (100 MiB).

**B3d. Observables and instruments.**

- P1:
  - `MemtableIndexBytes` gauge: `org.apache.cassandra.metrics:type=StorageAttachedIndex,keyspace=verify,table=<t>,index=<t>_v_idx,scope=IndexMetrics,name=MemtableIndexBytes`
    (`IndexMetrics.java:58`, `AbstractMetrics.java:84-96`), read with `nodetool sjk mx`.
  - heap used after a forced full GC (`jcmd GC.run` then `GC.heap_info`).
  - after flush: `system_views.sai_sstable_indexes.per_column_disk_size` (`SSTableIndexesSystemView.java:43,76-77`) and
    `du -cb` of the `*SAI*` files.
  - the probe query count, and `system.log` lines matching `is too large and cannot be indexed`.
  - `nodetool tablestats` "Space used (live)".
- P2:
  - the SSTable count (`ls | grep -c Data.db`), `du -sb` of the table directory, and the summed `per_column_disk_size`.
  - heap after a full GC.
  - the `p2q` result and a `TRACING ON` query in cqlsh, which shows the trace message from `QueryController.java:338`.
  - per-query allocation on read threads: JFR (`jdk.ThreadAllocationStatistics`) recorded across the 1000-query burst,
    summed over threads named `ReadStage-*` and `Native-Transport-Requests-*` (last value minus first), divided by 1000.
- P3:
  - the per-chunk CSV of accepted, rejected, `du -sb $RUN/data` and the first error.
  - `system.log` lines matching `local_data_disk_usage`.
  - `du -sb $RUN/data` after `nodetool flush` and after compactions finish (`nodetool compactionstats` shows 0 pending).
- Not directly observable: the memtable share of P3's `used`. It is estimated as (ratio × total) − du; the flush in step
  P3-5 removes it.

**B3e. Procedure.**

P1, run once with `FAIL=8KiB` and once with `FAIL=1MiB`:

1. `fresh`, then `printf 'sai_string_term_size_warn_threshold: 1KiB\nsai_string_term_size_fail_threshold: %s\n' $FAIL >> $RUN/conf/cassandra.yaml`.
   Then `EXTRA= start`.
2. Create the schema:

   ```
   $CQL -e "CREATE KEYSPACE verify WITH replication={'class':'SimpleStrategy','replication_factor':1};
            CREATE TABLE verify.p1big (k int PRIMARY KEY, v text); CREATE INDEX p1big_v_idx ON verify.p1big (v) USING 'sai';
            CREATE TABLE verify.p1small (k int PRIMARY KEY, v text); CREATE INDEX p1small_v_idx ON verify.p1small (v) USING 'sai';"
   ```

3. Record the starting heap: `heap > $W/p1-$FAIL-heap0.txt`.
4. Load the data:
   `SRC=$SRC RUN=$RUN python3 $W/load.py p1 p1big 1000 65536 $W/probe-big-$FAIL.txt`, then
   `... p1 p1small 1000 4096 $W/probe-small-$FAIL.txt`.
5. Record `heap > $W/p1-$FAIL-heap1.txt`, and `mx` for both tables'
   `MemtableIndexBytes > $W/p1-$FAIL-memidx.txt`.
6. Run the probe queries:

   ```
   $CQL -e "SELECT count(*) FROM verify.p1big WHERE v = '$(cat $W/probe-big-$FAIL.txt)';"
   ```

   and the same for `p1small`. A 64 KiB literal is accepted by cqlsh; if the shell rejects the argument length, put the
   statement into a file and use `-f`.
7. `nodetool flush verify`. Then query
   `SELECT index_name, sstable_name, per_column_disk_size FROM system_views.sai_sstable_indexes WHERE keyspace_name='verify';`,
   run `du -cb $RUN/data/verify/p1*-*/*SAI* | tail -1`, and run `nodetool tablestats verify`.
8. `grep -c 'is too large and cannot be indexed' $RUN/logs/system.log`.
9. Compaction path, only in the `FAIL=1MiB` run: `stop`, then append `sai_string_term_size_fail_threshold: 8KiB`. `start`,
   then `nodetool compact verify p1big`. Repeat step 7's SAI size query and step 6's probe.
10. `stop`.

P2, run once with `FAIL=-1` and once with `FAIL=50` (the second run reuses the data):

1. Run 1 only: `fresh`, then `EXTRA= start`. Create the schema:

   ```
   $CQL -e "CREATE KEYSPACE verify WITH replication={'class':'SimpleStrategy','replication_factor':1};
            CREATE TABLE verify.p2 (k int PRIMARY KEY, v int) WITH compaction={'class':'SizeTieredCompactionStrategy','enabled':'false'};
            CREATE INDEX p2_v_idx ON verify.p2 (v) USING 'sai';"
   ```

   Then build the 200 SSTables:
   `for r in $(seq 0 199); do SRC=$SRC RUN=$RUN python3 $W/load.py p2i $r; $SRC/bin/nodetool flush verify p2; done`.
   Then `stop`.
2. Each run: append `sai_sstable_indexes_per_query_warn_threshold: -1` and
   `sai_sstable_indexes_per_query_fail_threshold: $FAIL`, then `EXTRA= start`.
3. Record `ls $RUN/data/verify/p2-*/ | grep -c 'Data.db'`, `du -sb $RUN/data/verify/p2-*`, the summed
   `per_column_disk_size` for p2, and `heap`.
4. Run the query burst under JFR:

   ```
   jcmd $(cat $RUN/pid) JFR.start name=p2 settings=profile filename=$W/p2-$FAIL.jfr
   SRC=$SRC RUN=$RUN python3 $W/load.py p2q 1000 > $W/p2-$FAIL-q.txt
   jcmd $(cat $RUN/pid) JFR.stop name=p2
   jfr print --events jdk.ThreadAllocationStatistics $W/p2-$FAIL.jfr > $W/p2-$FAIL-alloc.txt
   ```

5. Record `heap` again. In cqlsh run `TRACING ON; SELECT k FROM verify.p2 WHERE v = 5;` and save the output.
6. Positive control, in the `FAIL=50` run only: `nodetool compact verify p2`, then repeat step 3 and `load.py p2q 10`.
7. `stop`.

P3, run once with `FAIL=50` and once with `FAIL=70`:

1. Set up the node:

   ```
   fresh
   printf 'authenticator: PasswordAuthenticator\ndata_disk_usage_max_disk_size: 1GiB\ndata_disk_usage_percentage_warn_threshold: 40\ndata_disk_usage_percentage_fail_threshold: %s\n' $FAIL >> $RUN/conf/cassandra.yaml
   EXTRA="-Dcassandra.disk_usage.monitor_interval_ms=1000" start
   sleep 15   # default superuser creation
   ```

2. Create the schema and the ordinary role:

   ```
   $CQL -u cassandra -p cassandra -e "CREATE KEYSPACE verify WITH replication={'class':'SimpleStrategy','replication_factor':1};
            CREATE TABLE verify.p3 (k int PRIMARY KEY, v blob) WITH compression={'enabled':'false'};
            CREATE ROLE writer WITH LOGIN = true AND PASSWORD = 'writer' AND SUPERUSER = false;"
   ```

3. `du -sb $RUN/data > $W/p3-$FAIL-du0.txt`.
4. Load as the ordinary role:
   `SRC=$SRC RUN=$RUN python3 $W/load.py p3 writer writer 0 262144 0 $W/p3-$FAIL-writer.csv`.
5. Flush, wait for compactions to finish, and measure:

   ```
   $SRC/bin/nodetool flush verify
   until $SRC/bin/nodetool compactionstats | grep -q 'pending tasks: 0'; do sleep 5; done
   du -sb $RUN/data > $W/p3-$FAIL-du1.txt
   grep 'local_data_disk_usage' $RUN/logs/system.log > $W/p3-$FAIL-log.txt
   ```

6. Controls, in the `FAIL=50` run only:
   `... load.py p3 cassandra cassandra 1000000 51200 0 $W/p3-50-super.csv`, then
   `... load.py p3 writer writer 2000000 25600 1 $W/p3-50-lwt.csv`, then
   `... load.py p3 writer writer 3000000 4000 0 $W/p3-50-writer-after.csv`, then repeat step 5 into `du2`.
7. `stop`. Check that `ps -ef | grep -c "[C]assandraDaemon.*$RUN"` is 0.

**B3f. Predictions.**

- P1:
  - `FAIL=8KiB`:
    - `MemtableIndexBytes`(p1big) < 1 MiB and (p1small) ≥ 3.9 MiB.
    - probe count 0 for p1big and 1 for p1small.
    - after flush, p1big SAI disk < 1 MiB and p1small ≥ 3 MiB.
    - the log count is ≥ 1.
  - `FAIL=1MiB`:
    - `MemtableIndexBytes`(p1big) ≥ 62.5 MiB (65,536,000), and p1big probe count 1.
    - p1big SAI disk ≥ 50 MiB.
    - (heap1 − heap0) in this run is at least 50 MiB more than (heap1 − heap0) in the 8KiB run.
    - p1small is the same as in the 8KiB run within ±10%, and so is "Space used (live)" of p1big.
  - The compaction step at 8KiB brings p1big SAI disk to < 1 MiB and the probe count to 0.
- P2:
  - N = 200 in both runs, and the table `du` and SAI disk are identical within ±2%.
  - Heap after GC is within ±5% (or ±20 MiB) between the runs.
  - `FAIL=-1`: ok = 1000 with rows = 200.
  - `FAIL=50`: ok = 0, and the error or trace contains `too many indexes (200) but max allowed is 50`.
  - Read-thread allocation per query: `FAIL=50` ≤ `FAIL=-1`, and `FAIL=-1` ≤ 200 × 64 KiB = 12.5 MiB per query.
  - After the compaction control: N = 1, the SAI disk and file count drop, and queries succeed under `FAIL=50`.
- P3:
  - `FAIL=50`:
    - The writer CSV shows accepted = 2000 per chunk until the estimated used (du plus memtable) reaches about
      512 MiB. After that, rejected = 2000 with the error `Write request failed because disk usage exceeds failure threshold`.
    - `du1` lies in [496, 560] MiB: the limit plus at most one 1 s monitor window and one chunk in flight.
    - The log shows `exceeds failure threshold of 50`.
    - Controls: the super and LWT CSVs show all accepted, `du2` ≥ `du1` + 280 MiB, and the writer-after CSV is all
      rejected.
  - `FAIL=70`: `du1` lies in [700, 765] MiB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| P1: at 8KiB, ~0 SAI heap or disk for 64 KiB terms; at 1MiB, ≥ 62.5 MiB and ≥ 50 MiB more heap | P1 confirmed on the real node |
| P1: at 8KiB, ≥ 62.5 MiB `MemtableIndexBytes` or a heap delta matching the 1MiB run | P1 wrong |
| P1: the p1small control or base-table size differs between runs | a confound; not confirmed |
| P2: disk and heap after GC equal across -1 and 50, queries fail only at 50, and the compaction control moves disk and SAI size | P2 negative confirmed: usage flat while the positive control moves |
| P2: disk, SAI or retained heap differ by more than the stated margins between -1 and 50 | usage follows the knob: P2 negative refuted |
| P2: per-query allocation at -1 > 200 MiB, or `FAIL=50` saves > 1 MiB per index | the transient cost is memory-significant: refuted for heap |
| P2: queries succeed at `FAIL=50` (limit never reached), or compaction does not change N (control did not move) | not confirmed |
| P3: writer rejected near 50% / 70% of 1 GiB, `du` plateaus in the predicted bands, super and LWT exceed it | P3 confirmed, bypasses confirmed |
| P3: writer keeps being accepted beyond 560 MiB (50) or 765 MiB (70) | P3 wrong |
| P3: plateau moves from 50 to 70 by about 205 MiB | usage follows the knob |
| P3: LWT rows rejected | the LWT bypass in A3 is wrong; P3 holds more broadly |

**B3h. Controls.**

- P1: the p1small table is indexed in both runs, the base-table size is the same, and the probe query checks index
  content.
- P2: the compaction step is the positive control (it does change SSTable and index count and size), and the threshold
  is changed with the data held fixed.
- P3: the two fail values, the superuser and LWT writers, and `data_disk_usage_max_disk_size` keep the real disk far
  from full, so a real ENOSPC cannot be mistaken for the guardrail.
- All runs use a fresh node directory, except P2's second run, which deliberately reuses its data.

**B4. Risks and cleanup.**

- Disk:
  - Unit tier: up to about 450 MiB under `$SRC/build/test` (P3, dropped between variants).
  - Cluster tier: P1 under 300 MiB; P2 under 50 MiB; P3 under 1.3 GiB data plus up to 512 MiB commit log
    (`commitlog_total_space`).
  - Everything is under `$W` on local disk, never on shared storage. Check `df -h $W` before starting (at least 5 GiB free).
- Processes: one Cassandra JVM and short-lived nodetool, cqlsh and python processes. After each run:
  `stop`, `pgrep -f "CassandraDaemon" -a | grep $RUN` (must be empty), and `pgrep -f CapacitySetVerifyTest` (must be
  empty).
- Cleanup: copy the CSV, txt and jfr results out of `$W`, then `rm -rf $W/n1 $SRC/build/test/cassandra`. Delete `$W`
  entirely when stage 4 is done.

## C. Sources read

- ~/writeup-ext/playbook-autonomous.md
- ~/writeup-ext/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java
- src/java/org/apache/cassandra/index/sai/plan/QueryController.java
- src/java/org/apache/cassandra/index/sai/plan/QueryViewBuilder.java
- src/java/org/apache/cassandra/index/sai/disk/IndexSearchResultIterator.java
- src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java
- src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java
- src/java/org/apache/cassandra/index/sai/memory/MemtableIndexManager.java
- src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java
- src/java/org/apache/cassandra/index/sai/metrics/IndexMetrics.java
- src/java/org/apache/cassandra/index/sai/metrics/AbstractMetrics.java
- src/java/org/apache/cassandra/index/sai/metrics/TableStateMetrics.java
- src/java/org/apache/cassandra/index/sai/virtual/{SSTableIndexesSystemView,SegmentsSystemView,ColumnIndexesSystemView,StorageAttachedIndexTables}.java
- src/java/org/apache/cassandra/db/virtual/SystemViewsKeyspace.java
- src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java
- src/java/org/apache/cassandra/service/disk/usage/DiskUsageBroadcaster.java
- src/java/org/apache/cassandra/db/guardrails/{Guardrail,Threshold,MaxThreshold,PercentageThreshold,Guardrails,GuardrailsMBean}.java
- src/java/org/apache/cassandra/config/{Config,GuardrailsOptions,CassandraRelevantProperties,DatabaseDescriptor,YamlConfigurationLoader}.java
- src/java/org/apache/cassandra/service/ClientState.java
- src/java/org/apache/cassandra/auth/AuthenticatedUser.java
- src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java
- src/java/org/apache/cassandra/cql3/statements/BatchStatement.java
- src/java/org/apache/cassandra/db/Directories.java
- src/java/org/apache/cassandra/gms/Gossiper.java
- src/java/org/apache/cassandra/service/StorageService.java
- src/java/org/apache/cassandra/tools/nodetool/GuardrailsConfigCommand.java
- conf/cassandra.yaml
- test/conf/cassandra.yaml
- test/unit/org/apache/cassandra/db/guardrails/GuardrailTester.java
- test/unit/org/apache/cassandra/db/guardrails/GuardrailSaiStringTermSizeTest.java
- test/unit/org/apache/cassandra/db/guardrails/GuardrailDiskUsageTest.java
- test/unit/org/apache/cassandra/tools/nodetool/GuardrailsConfigCommandsTest.java
- test/unit/org/apache/cassandra/cql3/CQLTester.java
- build.xml
- bin/cqlsh.py, lib/cassandra-driver-internal-only-3.29.0.zip (listing only)
- NEWS.txt, CHANGES.txt
- Cited, not opened: https://issues.apache.org/jira/browse/CASSANDRA-18926, https://issues.apache.org/jira/browse/CASSANDRA-17150, https://docs.oracle.com/en/java/javase/11/docs/api/jdk.management/com/sun/management/ThreadMXBean.html

## D. Stage-4 feedback

`none yet`
