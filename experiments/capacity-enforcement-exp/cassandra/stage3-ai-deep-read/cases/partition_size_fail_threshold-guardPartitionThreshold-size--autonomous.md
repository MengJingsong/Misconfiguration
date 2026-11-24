# partition_size_fail_threshold (with collection_size_fail_threshold, items_per_collection_fail_threshold at sstable write) — verification solution  <!-- file: cases/partition_size_fail_threshold-guardPartitionThreshold-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given lines, **linked**: [`SortedTableWriter.java:382`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java#L382), [`SortedTableWriter.java:417`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java#L417), [`SortedTableWriter.java:418`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java#L418) (unit kind: verdict, one verdict for the three lines) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `negative`. The three lines are the sstable-write-time checks of the `partition_size`, `partition_tombstones`, `collection_size` and `items_per_collection` guardrails; they are always evaluated with a `null` ClientState, and with a `null` state a fail-threshold breach only logs and publishes a diagnostic event and never throws, so flush/compaction writes the whole partition/collection to disk regardless of the threshold. |
| Ground | Report-only by construction: `Guardrail.fail` throws only `if (state != null)` (`Guardrail.java:139-140`), and every call at the target passes `null` (`SortedTableWriter.java:382,389,417,418,426,427`). The check also runs after the partition is already serialized into the data file (`SortedTableWriter.java:240-244`), so even a throw could not have kept those bytes off disk. `conf/cassandra.yaml:2116-2117` and `:2155`, `:2166` document this ("exceeding the fail threshold ... will only log an error message, without interrupting the operation"). |

## A. Constraint trace

**A1. The constraint.**

- **Primary: `partition_size_fail_threshold`** (and its sibling `partition_size_warn_threshold`).
  Kind: configuration entry (guardrail threshold). First declared at
  [`Config.java:911`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L911)
  as `public volatile DataStorageSpec.LongBytesBound partition_size_fail_threshold = null;` (warn at `Config.java:910`,
  which also `@Replaces` the deprecated `compaction_large_partition_warning_threshold[_mb]`, `Config.java:908-909`).
  Unit: bytes (a data-storage spec such as `100MiB`; converted with `toBytes()` by `Guardrails.sizeToBytes`,
  `Guardrails.java:1442-1445`, `null` → `-1`). Default: `null` = disabled (`MaxThreshold.failValue` maps `<= 0` to
  `Long.MAX_VALUE`, `MaxThreshold.java:56-60`). Wired into the guardrail at `Guardrails.java:332-339`
  (`partitionSize`, name `partition_size`). Validation: both values non-negative, warn ≤ fail
  (`GuardrailsOptions.java:563-574`, `:1207-1222`). Set by: yaml key `partition_size_fail_threshold` (commented out in
  `conf/cassandra.yaml:2121-2122`); at runtime, no restart, via JMX `GuardrailsMBean.setPartitionSizeThreshold(warn, fail)`
  (`GuardrailsMBean.java:496`, `Guardrails.java:924-927`) or `nodetool setguardrailsconfig`
  (`GuardrailsConfigCommand.java:172`). It is read on each check (`volatile` field), so a change takes effect at the next
  flush/compaction.
- **Also checked at the same three lines (same verdict):**
  - `partition_tombstones_fail_threshold` (`Config.java:914`, long count, default `-1`), also passed through line 382
    (`SortedTableWriter.java:245`). It caps a tombstone count, not bytes, so it is noted but not the target of the design.
  - `collection_size_fail_threshold` (`Config.java:918`, bytes, default `null`), the check at line 417
    (`Guardrails.java:368-375`).
  - `items_per_collection_fail_threshold` (`Config.java:920`, int count, default `-1`), the check at line 418
    (`Guardrails.java:380-387`).
  These are set the same way (yaml; JMX `setCollectionSizeThreshold`, `setItemsPerCollectionThreshold`,
  `Guardrails.java:982,1000`).

**A2. What it caps.** Nominally disk (and indirectly read-path heap): the size of one partition as written into one
sstable. The quantity compared is `rowSize = dataWriter.position() - partitionWriter.getInitialPosition()`
(`SortedTableWriter.java:242-243`), the **uncompressed** serialized length of the partition in the Data component
(`SequentialWriter.position()` returns `current()`, `SequentialWriter.java:271-274`; the compressed writer overrides only
`getOnDiskFilePointer`, `CompressedSequentialWriter.java:110`). For lines 417/418 the operands are
`liveCells.dataSize()` (sum of the live cells' `dataSize()`, `ComplexColumnData.java:134-140`) and
`liveCells.cellsCount()` (`ComplexColumnData.java:73-76`) of one non-frozen collection column in one row
(`SortedTableWriter.java:410-415`).

**A3. Mechanism.**

1. Every sstable write (memtable flush, `Flushing.java:171`; compaction/rewrite, `SSTableRewriter.java:136`; both BIG and
   BTI formats, `BigTableWriter.java:69`, `BtiTableWriter.java:64`) calls `SortedTableWriter.append`
   (`SortedTableWriter.java:132`).
2. For each static row and each row, `guardCollectionSize` runs **before** the row is written
   (`SortedTableWriter.java:191`, `:210`). It returns early unless one of the two guardrails is enabled
   (`:395-396`), skips system keyspaces (`:398`), purges dead cells (`:410`), then the check at
   [`SortedTableWriter.java:417-418`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java#L417-L418)
   (`triggersOn(…, null)`). If either triggers, it calls `guard(cellsSize, msg, true, null)` and
   `guard(cellsCount, msg, true, null)` (`:426-427`). Whatever the outcome, control returns and the row is written in full
   at `:212` (`partitionWriter.addUnfiltered(row)`).
3. After the whole partition has been serialized (`partitionWriter.finish()`, `:240`), `endPartition` computes `rowSize`
   (`:242-243`) and calls `guardPartitionThreshold(Guardrails.partitionSize, key, rowSize)` (`:244`) and the tombstone
   variant (`:245`). The check at
   [`SortedTableWriter.java:382`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java#L382)
   is `guardrail.triggersOn(size, null)`; if true it formats a message and calls `guardrail.guard(size, message, true, null)`
   (`:389`).
4. `Threshold.triggersOn` = `enabled(state) && (value > warn || value > fail)` (`Threshold.java:101-104`,
   `MaxThreshold.java:50-53`); `enabled(null)` = `DatabaseDescriptor.isDaemonInitialized()` and a positive threshold
   (`Guardrail.java:93-96`, `Threshold.java:80-86`).
5. `Threshold.guard` (`Threshold.java:128-143`): if `value > fail` → `triggerFail` → `Guardrail.fail(message, redacted, state)`
   (`Threshold.java:145-149`). `fail` logs at ERROR, adds a client warning (ignored outside a request), traces, publishes a
   `GuardrailEvent` FAILED, and **throws `GuardrailViolatedException` only if `state != null`** (`Guardrail.java:124-141`).
   Here `state == null`, so nothing is thrown. Else, if `value > warn` → `warn(...)` (log WARN + event, `Guardrail.java:103-117`).
6. Outcome when the limit is reached: an ERROR log line
   `Guardrail partition_size violated: Partition <ks>.<tbl>:<key> on sstable <file> has size <N>, this exceeds the failure threshold of <T>. Too large partitions can cause performance problems.`
   (`Guardrails.java:337-339`, `Guardrail.java:144-156`) and a diagnostic event; the partition stays in the sstable, the flush
   or compaction completes, the sstable becomes live.

Bypass / overshoot:
- **Post-hoc by position.** Line 382 runs after the bytes are in the writer (`:240-244`); no path rolls them back.
- **Per-sstable only.** A partition spread across several sstables is never summed (`conf/cassandra.yaml:2118`); it is
  seen only when compaction merges it.
- **Uncompressed operand.** `rowSize` is uncompressed length, so the on-disk (compressed) size may be lower than the operand.
- **Offline tools.** With `isDaemonInitialized()` false (offline sstable tools), the guardrail is disabled
  (`Guardrail.java:95`).
- **Memtable.** Nothing here bounds the partition while it sits in the memtable.
- **Collections at query time.** The query-time checks (`Lists.java:531,540`, `Sets.java:399,410`, `Maps.java:480,488`)
  do throw for ordinary users, but they see only the fragment being written (`Lists.java:527-529` comment), so appends grow a
  collection past the threshold without limit; the sstable-time check at 417/418 is the only place that sees the whole
  collection, and it only reports.

**A4. Other consumers.** Disk: other partitions and sstables of the table, the sstable's Index/Partitions/Rows, Filter,
Statistics, CompressionInfo components, the commit log, hints, snapshots and compaction temporary space. The only disk
guardrail that can refuse writes is `data_disk_usage_*` (separate). Memory: memtables (`memtable_heap_space` /
`memtable_offheap_space`), the read path materializing a large partition, compaction buffers. None of these are governed by
`partition_size_*` or the collection thresholds at sstable write.

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:2115-2122` (partition size: "exceeding the fail threshold on that moment will only log an error
  message, without interrupting the operation"), `:2124-2131` (partition tombstones, same), `:2150-2169` (collection
  size/items: at sstable write "exceeding the fail threshold will only log an error message").
- `CHANGES.txt:493` CASSANDRA-18500 (partition size guardrail), `:489` CASSANDRA-17194 (partition tombstones), `:945`
  CASSANDRA-17153 (collection guardrails); `NEWS.txt:348-353`.
  https://issues.apache.org/jira/browse/CASSANDRA-18500 , https://issues.apache.org/jira/browse/CASSANDRA-17153
- Tests that already treat a breach at flush/compaction as an event only, never an exception:
  `test/unit/org/apache/cassandra/db/guardrails/GuardrailPartitionSizeTest.java` (asserts `listener.assertFailed` after
  `flush()`/`compact()` with the flush succeeding), `test/distributed/.../guardrails/GuardrailPartitionSizeTest.java`,
  `GuardrailCollectionSizeOnSSTableWriteTest.java`, `GuardrailItemsPerCollectionOnSSTableWriteTest.java`.

## B. Verification solution

**B1. Claim under test.** With `partition_size_fail_threshold = T` (and, separately, `collection_size_fail_threshold` /
`items_per_collection_fail_threshold`), a partition (collection) larger than `T` that reaches flush or compaction is written
to disk in full: the sstable's Data size and the readable row/element count are the same as with the threshold disabled,
and the only effect is an ERROR log line / FAILED guardrail event. The claim is refuted if any enabled threshold makes the
written size or readable rows fall (toward `T`), or makes the flush/compaction fail.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Work on a private local copy, never in the shared tree:

```bash
export W=/mydata/$USER-s3-o208          # any LOCAL disk with >= 5 GiB free; check with: df -h $(dirname $W)
mkdir -p $W && rsync -a ~/cassandra-5.0.9/ $W/cassandra/
cd $W/cassandra && ant jar build-test     # JDK 11 on PATH (java -version → 11)
```

Test source: `$W/cassandra/test/unit/org/apache/cassandra/db/guardrails/O208SSTableWriteGuardrailTest.java` (below). It
extends `GuardrailTester` (`test/unit/.../guardrails/GuardrailTester.java`), which starts an in-JVM CQLTester instance
(so `isDaemonInitialized()` is true), enables diagnostic events (`GuardrailTester.java:118`) and provides an
**ordinary-user** `ClientState` (`userClientState`, `:122-128`) so that query-time guardrails apply to the control.
JVM options: Ant defaults for `testsome` (no change needed).

```java
package org.apache.cassandra.db.guardrails;

import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Consumer;

import com.google.common.collect.ImmutableList;
import org.junit.*;

import org.apache.cassandra.db.marshal.*;
import org.apache.cassandra.diag.DiagnosticEventService;
import org.apache.cassandra.io.sstable.format.SSTableReader;

public class O208SSTableWriteGuardrailTest extends GuardrailTester
{
    static final int ROWS = 160, VALUE = 64 * 1024;   // one partition: 160 x 64 KiB = 10,485,760 B of values
    static final int ITEMS = 200, ITEM = 16 * 1024;   // one list:      200 x 16 KiB =  3,276,800 B of values
    final List<String> failed = new CopyOnWriteArrayList<>();
    final List<String> warned = new CopyOnWriteArrayList<>();
    final Consumer<GuardrailEvent> sink = e -> {
        String m = e.toMap().get("name") + " | " + e.toMap().get("message");
        if (e.getType() == GuardrailEvent.GuardrailEventType.FAILED) failed.add(m); else warned.add(m);
    };
    final Random rnd = new Random(208);

    @Before public void sub()   { DiagnosticEventService.instance().subscribe(GuardrailEvent.class, sink); }
    @After  public void unsub() {
        DiagnosticEventService.instance().unsubscribe(sink);
        Guardrails g = guardrails();
        g.setPartitionSizeThreshold(null, null); g.setColumnValueSizeThreshold(null, null);
        g.setCollectionSizeThreshold(null, null); g.setItemsPerCollectionThreshold(-1, -1);
    }

    ByteBuffer blob(int n) { byte[] b = new byte[n]; rnd.nextBytes(b); return ByteBuffer.wrap(b); }

    void report(String tag, String knob, int rejected, long readable) {
        long disk = 0, raw = 0; int n = 0;
        for (SSTableReader r : getCurrentColumnFamilyStore().getLiveSSTables()) { disk += r.onDiskLength(); raw += r.uncompressedLength(); n++; }
        System.out.printf("O208 %s knob=%s sstables=%d dataOnDisk=%d dataUncompressed=%d rejected=%d readable=%d failed=%s warned=%s%n",
                          tag, knob, n, disk, raw, rejected, readable, failed, warned);
        failed.clear(); warned.clear();
    }

    long rows() throws Throwable { return execute("SELECT count(*) FROM %s WHERE k = 1").one().getLong("count"); }

    int insertRows(int from, int to) {
        int rejected = 0;
        for (int c = from; c < to; c++)
            try { execute(userClientState, "INSERT INTO %s (k, c, v) VALUES (1, ?, ?)",
                          Arrays.asList(Int32Type.instance.decompose(c), blob(VALUE))); }
            catch (RuntimeException e) { rejected++; }
        return rejected;
    }

    void partitionRun(String fail) throws Throwable {
        guardrails().setPartitionSizeThreshold(null, fail);
        createTable("CREATE TABLE %s (k int, c int, v blob, PRIMARY KEY (k, c)) WITH compression = {'enabled':'false'}");
        disableCompaction();
        int rej = insertRows(0, ROWS);
        failed.clear(); warned.clear();
        flush();   report("P-flush",   String.valueOf(fail), rej, rows());
        compact(); report("P-compact", String.valueOf(fail), rej, rows());
    }

    @Test public void p0_disabled() throws Throwable { partitionRun(null); }
    @Test public void p1_8MiB()     throws Throwable { partitionRun("8MiB"); }
    @Test public void p2_4MiB()     throws Throwable { partitionRun("4MiB"); }
    @Test public void p3_2MiB()     throws Throwable { partitionRun("2MiB"); }

    // partition split over two sstables of ~5 MiB each: invisible at flush, seen at compaction
    @Test public void p4_split8MiB() throws Throwable {
        guardrails().setPartitionSizeThreshold(null, "8MiB");
        createTable("CREATE TABLE %s (k int, c int, v blob, PRIMARY KEY (k, c)) WITH compression = {'enabled':'false'}");
        disableCompaction();
        int rej = insertRows(0, ROWS / 2); failed.clear(); flush();
        rej += insertRows(ROWS / 2, ROWS); flush();
        report("S-flushx2", "8MiB", rej, rows());
        compact(); report("S-compact", "8MiB", rej, rows());
    }

    // POSITIVE CONTROL: same rows, a cap that binds (query-time column_value_size, ordinary user)
    @Test public void pc_columnValueSize() throws Throwable {
        guardrails().setColumnValueSizeThreshold(null, "32KiB");
        partitionRun("2MiB");
    }

    void collectionRun(String tag, String sizeFail, int itemsFail, boolean whole) throws Throwable {
        guardrails().setCollectionSizeThreshold(null, sizeFail);
        guardrails().setItemsPerCollectionThreshold(-1, itemsFail);
        createTable("CREATE TABLE %s (k int PRIMARY KEY, l list<blob>) WITH compression = {'enabled':'false'}");
        disableCompaction();
        int rej = 0;
        if (whole) {
            List<ByteBuffer> all = new ArrayList<>();
            for (int i = 0; i < ITEMS; i++) all.add(blob(ITEM));
            try { execute(userClientState, "INSERT INTO %s (k, l) VALUES (1, ?)",
                          Collections.singletonList(ListType.getInstance(BytesType.instance, true).decompose(all))); }
            catch (RuntimeException e) { rej++; }
        } else {
            for (int i = 0; i < ITEMS; i++)
                try { execute(userClientState, "UPDATE %s SET l = l + ? WHERE k = 1",
                              Collections.singletonList(ListType.getInstance(BytesType.instance, true).decompose(ImmutableList.of(blob(ITEM))))); }
                catch (RuntimeException e) { rej++; }
        }
        failed.clear(); warned.clear();
        flush();
        List<?> l = execute("SELECT l FROM %s WHERE k = 1").isEmpty() ? null
                  : execute("SELECT l FROM %s WHERE k = 1").one().getList("l", BytesType.instance);
        report(tag + "-flush", sizeFail + "/" + itemsFail, rej, l == null ? 0 : l.size());
    }

    @Test public void c0_disabled()   throws Throwable { collectionRun("C0", null,   -1,  false); }
    @Test public void c1_enabled()    throws Throwable { collectionRun("C1", "1MiB", 100, false); }
    // POSITIVE CONTROL: the same 200 x 16 KiB in ONE statement is checked at query time with the user's state
    @Test public void cc_wholeInsert() throws Throwable { collectionRun("CC", "1MiB", 100, true); }
}
```

**B2b. Knobs.**
- `partition_size_fail_threshold` ∈ {`null` (disabled), `8MiB`, `4MiB`, `2MiB`}, warn left `null`; set per test through
  `Guardrails.setPartitionSizeThreshold(null, fail)` (the JMX setter, `Guardrails.java:924`). All three enabled values are
  below the 10 MiB partition, at roughly 0.8×, 0.4× and 0.2× of it, so if the cap bound, the written size would have to
  drop to (at most) the threshold, a factor 1.25–5 change.
- Split case: `8MiB` with the partition in two 5 MiB halves (below the threshold per sstable, above it once merged).
- `collection_size_fail_threshold` ∈ {`null`, `1MiB`} together with `items_per_collection_fail_threshold` ∈ {`-1`, `100`}
  (lines 417/418): 1 MiB and 100 items are ~0.3× and 0.5× of the collection.
- Positive controls: `column_value_size_fail_threshold = 32KiB` (half of each 64 KiB value), and the collection thresholds
  applied to a single 200-element INSERT.

**B2c. Workload.**
- Partition: one partition `k = 1`, 160 rows of 65,536 random bytes (uncompressible), table compression off:
  160 × 65,536 = 10,485,760 B of values; with per-row headers the serialized partition is ~10.49 MB, above 8/4/2 MiB
  (8,388,608 / 4,194,304 / 2,097,152 B). Each INSERT is 64 KiB, far below the mutation size limit (half of
  `commitlog_segment_size` 32 MiB). Compaction disabled; `flush()` writes one sstable; `compact()` (major) rewrites it, so
  the check runs twice per test.
- Collection: one row, `list<blob>` built by 200 appends of one 16 KiB element each: 200 × 16,384 = 3,276,800 B, 200 items,
  above 1 MiB (1,048,576 B) and 100 items. Each append is 1 item / ~16.4 KB, under the query-time thresholds, so it is
  accepted (`Lists.java:531,540` check only the fragment).

**B2d. Observables and instruments.**
- Operand of the check: the value in the FAILED guardrail event message (`… has size <N>, this exceeds the failure threshold
  of <T>`; the redacted variant keeps value and threshold, `Threshold.java:71-74`), collected by the test's own
  `Consumer<GuardrailEvent>`; for 417/418, `Detected collection <redacted> of size <N>` / `with <N> items`.
- Resource: `SSTableReader.onDiskLength()` (Data component on disk) and `uncompressedLength()` summed over live sstables
  (`SSTableReader.java:961,983`), printed after each flush and compaction.
- Readable data: `SELECT count(*)` rows of `k = 1`; list length for the collection.
- Rejections at the client: count of exceptions from the inserts (`GuardrailViolatedException` extends
  `InvalidRequestException`).
- Output: lines starting `O208 ` in `build/test/output/TEST-org.apache.cassandra.db.guardrails.O208SSTableWriteGuardrailTest.xml`
  (system-out) and the ERROR lines in `build/test/logs/` for the same class.
- Not directly observable: `rowSize` itself (a local variable) — taken from the event message.

**B2e. Procedure.**
1. B2a commands; write the test file into the copy.
2. `cd $W/cassandra && ant testsome -Dtest.name=org.apache.cassandra.db.guardrails.O208SSTableWriteGuardrailTest`
3. `grep -h '^O208 ' build/test/output/TEST-org.apache.cassandra.db.guardrails.O208SSTableWriteGuardrailTest.xml` (or grep the
   `<system-out>` section) and record every line in a table.
4. `grep -rh 'Guardrail \(partition_size\|collection_size\|items_per_collection\) violated' build/test/logs/ | head`
5. Check the JUnit result: all tests pass (no exception from `flush()`/`compact()`).
6. Cleanup per B4.

**B2f. Predictions.** (stated before any run)
- `P-flush`/`P-compact`, knob `null`: `sstables=1`, `dataUncompressed` ≈ `dataOnDisk` in [10,485,760; 10,520,000] B,
  `readable=160`, `rejected=0`, `failed=[]`.
- Knobs `8MiB`, `4MiB`, `2MiB`: identical `dataOnDisk` to the `null` run within ±0.1 % (same bytes; random seed fixed),
  `readable=160`, `rejected=0`; `failed` holds exactly one `partition_size` entry per step whose value N is in
  [10,485,760; 10,520,000] and whose threshold is 8,388,608 / 4,194,304 / 2,097,152. No exception; flush and compaction
  complete.
- `S-flushx2`: `sstables=2`, each ~5.24 MB, `failed=[]` (each half < 8 MiB); `S-compact`: `sstables=1`, ~10.49 MB, one
  `partition_size` failure with N ≈ 10.49 M, `readable=160`.
- `pc_columnValueSize` (positive control): `rejected=160`, `readable=0`, `sstables=0`, `dataOnDisk=0` (nothing reaches the
  memtable; flush of an empty memtable writes no sstable).
- `C0`: list length 200, Data ≈ 3.28–3.30 MB, `failed=[]`. `C1`: same size and length 200, `rejected=0`, `failed` has one
  `collection_size` (value ≈ 3.28 M > 1,048,576) and one `items_per_collection` (200 > 100) entry.
- `CC` (positive control): `rejected=1`, list absent (length 0), `sstables=0`.
- Wrong if: any enabled run shows `dataOnDisk` ≤ threshold or materially (> 1 %) below the `null` run, `readable < 160` (or
  list < 200), a non-zero `rejected` outside the controls, or `flush()`/`compact()` throws.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Enabled runs: same Data size and 160 rows / 200 items as disabled run, FAILED event with N > T; controls show `rejected` = all and 0 bytes | Claim confirmed: the threshold reports but does not cap disk; the instruments do see a binding cap |
| Enabled runs: Data size drops toward T, or rows/items lost, or flush/compaction throws | Claim refuted: the threshold caps (or blocks) the write |
| Enabled runs: no FAILED event at all and size unchanged | Not confirmed: limit not reached as configured (check the knob was applied, `isDaemonInitialized`, event subscription) |
| Controls: inserts not rejected / Data written | Not confirmed: the positive control did not move, so a flat reading proves nothing (check ordinary-user state) |
| `S-flushx2` shows a failure event | Mechanism differs from the trace (per-sstable claim wrong) — record, claim itself still decided by size/rows |

**B2h. Controls.**
- `null` run is the baseline for the same bytes (fixed `Random(208)`).
- Positive controls on the same data volume (`column_value_size` per row; one-statement collection insert) show that a
  binding guardrail empties the sstable and that `rejected`/`dataOnDisk` detect it.
- Compression off and random bytes make operand and on-disk size coincide, so no compression effect can masquerade as a cap.
- Compaction disabled except the explicit major compaction, so sstable count changes only by the test's steps.
- The FAILED event's value proves the check actually ran with N > T in that run.

### B3. Cluster tier

**B3a. Environment and build.** One node on the local Linux machine, JDK 11, built from the copy in B2a (`ant jar`, already
done). Run directory on local disk: `export RUN=$W/node` (≥ 5 GiB free). Non-default ports to avoid other users:
storage 17000, native 19042, JMX 17199. Heap `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M`.

```bash
cd $W/cassandra
mkdir -p $RUN/{conf,data,commitlog,hints,saved_caches,cdc_raw,logs,client}
cp -r conf/* $RUN/conf/
sed -i 's/^JMX_PORT="7199"/JMX_PORT="17199"/' $RUN/conf/cassandra-env.sh
cat >> $RUN/conf/cassandra.yaml <<EOF
data_file_directories: [$RUN/data]
commitlog_directory: $RUN/commitlog
hints_directory: $RUN/hints
saved_caches_directory: $RUN/saved_caches
cdc_raw_directory: $RUN/cdc_raw
memtable_heap_space: 2048MiB
read_request_timeout: 60000ms
EOF
sed -i -e 's/^storage_port: 7000/storage_port: 17000/' -e 's/^native_transport_port: 9042/native_transport_port: 19042/' \
       -e 's/^authenticator: AllowAllAuthenticator/authenticator: PasswordAuthenticator/' \
       -e 's/^authorizer: AllowAllAuthorizer/authorizer: CassandraAuthorizer/' $RUN/conf/cassandra.yaml
grep -nE '^(storage_port|native_transport_port|authenticator|authorizer|data_file_directories|memtable_heap_space)' $RUN/conf/cassandra.yaml
ss -ltn | grep -E ':(17000|19042|17199)\b' && echo "PORT BUSY - pick others"
```

PasswordAuthenticator is required for the positive control only: with `AllowAllAuthenticator` every client is a superuser
(`ClientState.java:602-605`) and query-time guardrails are skipped (`Guardrail.java:95`). The sstable-time check uses
`state == null` and is unaffected by auth.

Client (`$RUN/client/O208Client.java`, Java driver 3.x from `build/lib/jars`, dependency at
`.build/cassandra-deps-template.xml:147-151`):

```java
import com.datastax.driver.core.*;
import java.nio.ByteBuffer;
import java.util.*;

public class O208Client {
    public static void main(String[] a) {
        String mode = a[0], user = a[1], pass = a[2];
        int n = a.length > 3 ? Integer.parseInt(a[3]) : 0, size = a.length > 4 ? Integer.parseInt(a[4]) : 0;
        Cluster cl = Cluster.builder().addContactPoint("127.0.0.1").withPort(19042).withCredentials(user, pass)
                            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(120000)).build();
        Session s = cl.connect();
        Random r = new Random(208);
        int ok = 0, rej = 0; String err = null;
        switch (mode) {
            case "setup":
                s.execute("CREATE ROLE IF NOT EXISTS o208 WITH PASSWORD = 'o208' AND LOGIN = true");
                s.execute("CREATE KEYSPACE IF NOT EXISTS s3o208 WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
                s.execute("CREATE TABLE IF NOT EXISTS s3o208.big (k int, c int, v blob, PRIMARY KEY (k, c)) WITH compression = {'enabled':'false'}");
                s.execute("CREATE TABLE IF NOT EXISTS s3o208.coll (k int PRIMARY KEY, l list<blob>) WITH compression = {'enabled':'false'}");
                s.execute("GRANT ALL PERMISSIONS ON KEYSPACE s3o208 TO o208");
                break;
            case "truncate":
                s.execute("TRUNCATE s3o208.big"); s.execute("TRUNCATE s3o208.coll"); break;
            case "rows": {
                PreparedStatement p = s.prepare("INSERT INTO s3o208.big (k, c, v) VALUES (1, ?, ?)");
                for (int i = 0; i < n; i++) { byte[] b = new byte[size]; r.nextBytes(b);
                    try { s.execute(p.bind(i, ByteBuffer.wrap(b))); ok++; } catch (Exception e) { rej++; if (err == null) err = e.toString(); } }
                break; }
            case "append": {
                PreparedStatement p = s.prepare("UPDATE s3o208.coll SET l = l + ? WHERE k = 1");
                for (int i = 0; i < n; i++) { byte[] b = new byte[size]; r.nextBytes(b);
                    try { s.execute(p.bind(Collections.singletonList(ByteBuffer.wrap(b)))); ok++; } catch (Exception e) { rej++; if (err == null) err = e.toString(); } }
                break; }
            case "whole": {
                List<ByteBuffer> l = new ArrayList<>();
                for (int i = 0; i < n; i++) { byte[] b = new byte[size]; r.nextBytes(b); l.add(ByteBuffer.wrap(b)); }
                try { s.execute(s.prepare("INSERT INTO s3o208.coll (k, l) VALUES (1, ?)").bind(l)); ok++; } catch (Exception e) { rej++; err = e.toString(); }
                break; }
            case "count": {
                long rows = s.execute("SELECT count(*) FROM s3o208.big WHERE k = 1").one().getLong(0);
                Row row = s.execute("SELECT l FROM s3o208.coll WHERE k = 1").one();
                System.out.println("O208COUNT rows=" + rows + " listItems=" + (row == null ? 0 : row.getList(0, ByteBuffer.class).size()));
                break; }
        }
        System.out.println("O208CLIENT mode=" + mode + " ok=" + ok + " rejected=" + rej + " firstErr=" + err);
        cl.close();
    }
}
```

```bash
cd $RUN/client && javac -cp "$W/cassandra/build/lib/jars/*" O208Client.java
CLIENT="java -cp $RUN/client:$W/cassandra/build/lib/jars/* O208Client"
```

**B3b. Knobs.** Set in `$RUN/conf/cassandra.yaml` before each start (append at the end; one value per run, restart between
runs so yaml loading is what is tested), and verified with `bin/nodetool -p 17199 getguardrailsconfig | grep -E 'partition_size|collection_size|items_per_collection|column_value_size'`:
- Run R0: no threshold lines (defaults: disabled).
- Run R1: `partition_size_fail_threshold: 64MiB`, `collection_size_fail_threshold: 1MiB`, `items_per_collection_fail_threshold: 100`.
- Run R2: `partition_size_fail_threshold: 16MiB`, `collection_size_fail_threshold: 1MiB`, `items_per_collection_fail_threshold: 100`.
- Run RC (positive control): R2's lines plus `column_value_size_fail_threshold: 32KiB`.
Why: 64 MiB and 16 MiB are 0.5× and 0.125× of the 128 MiB partition, so a binding cap would cut usage by 2× or 8×.

**B3c. Workload.** Per run, as the ordinary user `o208`:
- W1: `$CLIENT rows o208 o208 2048 65536` → one partition of 2048 × 65,536 B = 134,217,728 B (128 MiB) of random bytes.
  In-memtable footprint ~150 MB is well below the flush trigger (`memtable_heap_space` 2048 MiB × cleanup threshold 1/3 ≈
  683 MiB, `cassandra.yaml:811`), so the partition goes to one sstable at the explicit `nodetool flush`. Commit log grows by
  ~135 MB (5 segments of 32 MiB), within default limits.
- W2: `$CLIENT append o208 o208 512 16384` → one list of 512 elements × 16,384 B = 8,388,608 B (8 MiB), 512 items:
  8× and 5× over the R1/R2 collection thresholds; each append is 1 item / ~16.4 KB, under them.
- RC adds W1 (expected all rejected) and `$CLIENT whole o208 o208 128 16384` (2 MiB, 128 items in one statement; expected
  rejected by the query-time check).
- Duration: < 5 minutes per run.

**B3d. Observables and instruments.**
- Disk, actual resource: `du -sb $RUN/data/s3o208/big-*/ $RUN/data/s3o208/coll-*/` and
  `ls -l $RUN/data/s3o208/big-*/*-Data.db` after flush and after `nodetool compact`.
- Node view: `bin/nodetool -p 17199 tablestats s3o208.big s3o208.coll` → `Space used (live)`, `SSTable count`,
  `Compacted partition maximum bytes` (`TableStatsPrinter.java:100,141`).
- Per-partition size per sstable: `tools/bin/sstablepartitions $RUN/data/s3o208/big-*/*-Data.db` (offline reader; run
  after the node is stopped, or on a copy).
- Check operand and outcome: `grep -c 'Guardrail partition_size violated' $RUN/logs/system.log` and the printed size/threshold;
  same for `collection_size` / `items_per_collection`; `grep -E 'Exception|ERROR' $RUN/logs/system.log` for anything else.
- Readable data: `$CLIENT count o208 o208` (rows of `k = 1`, items in the list).
- Client rejects: `O208CLIENT ... rejected=` line.
- Not directly observable: the in-writer `rowSize`; taken from the log line.

**B3e. Procedure.** For each run R ∈ {R0, R1, R2, RC}:

```bash
cd $W/cassandra
# 1. knobs: restore a clean yaml tail, then append R's lines
cp $RUN/conf/cassandra.yaml.base $RUN/conf/cassandra.yaml 2>/dev/null || cp $RUN/conf/cassandra.yaml $RUN/conf/cassandra.yaml.base
printf '%s\n' "<R's threshold lines>" >> $RUN/conf/cassandra.yaml
# 2. start (fresh data each run)
rm -rf $RUN/data/* $RUN/commitlog/* $RUN/hints/* $RUN/saved_caches/* $RUN/logs/*
CASSANDRA_CONF=$RUN/conf CASSANDRA_LOG_DIR=$RUN/logs MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M bin/cassandra -p $RUN/pid
until grep -q 'Starting listening for CQL clients' $RUN/logs/system.log 2>/dev/null; do sleep 2; done; sleep 15   # default superuser setup delay
bin/nodetool -p 17199 getguardrailsconfig | grep -E 'partition_size|collection_size|items_per_collection|column_value_size'
# 3. schema and role (as default superuser), disable autocompaction
$CLIENT setup cassandra cassandra
bin/nodetool -p 17199 disableautocompaction s3o208
# 4. workload as ordinary user
$CLIENT rows   o208 o208 2048 65536
$CLIENT append o208 o208 512  16384
[ RC ] && $CLIENT whole o208 o208 128 16384
bin/nodetool -p 17199 tablestats s3o208 | grep -E 'Table:|SSTable count|Memtable data size'   # expect 0 sstables before flush
# 5. flush, measure
bin/nodetool -p 17199 flush s3o208
du -sb $RUN/data/s3o208/*/ ; ls -l $RUN/data/s3o208/*/*-Data.db
bin/nodetool -p 17199 tablestats s3o208 | grep -E 'Table:|SSTable count|Space used \(live\)|Compacted partition maximum bytes'
grep -E 'Guardrail (partition_size|collection_size|items_per_collection|column_value_size) violated' $RUN/logs/system.log | cut -c1-300
$CLIENT count o208 o208
# 6. major compaction, measure again
bin/nodetool -p 17199 compact s3o208
(same measurements as step 5)
# 7. stop, offline per-partition view, confirm no process left
bin/nodetool -p 17199 stopdaemon || kill $(cat $RUN/pid)
while kill -0 $(cat $RUN/pid) 2>/dev/null; do sleep 1; done
tools/bin/sstablepartitions $RUN/data/s3o208/big-*/*-Data.db | tail -20
pgrep -u $USER -f CassandraDaemon && echo "LEFTOVER PROCESS"
```

If `SSTable count` before step 5 is not 0 (an automatic flush happened), record it; step 6 still merges into one sstable and
its measurements decide.

**B3f. Predictions.** (stated before any run)
- R0: `big` Data.db ≈ 134.2–134.6 MB (≥ 134,217,728 B), `du` of the `big` dir within +1 % of that; `count` rows=2048;
  `coll` Data.db ≈ 8.4–8.5 MB, listItems=512; no guardrail log lines; client `rejected=0`.
- R1 and R2: the same sizes as R0 within ±0.5 % after flush and after compaction; rows=2048, listItems=512; client
  `rejected=0`; system.log has, after flush and again after compaction, one `partition_size violated` line with size ≈ 134.2–134.6 M
  and threshold 67,108,864 (R1) / 16,777,216 (R2), plus one `collection_size` (size ≈ 8.4–8.5 M > 1,048,576) and one
  `items_per_collection` (512 > 100) line; `Compacted partition maximum bytes` ≥ 134,217,728 (histogram bucket at or above
  the true size). Flush and compaction complete with no exception.
- RC (positive control): W1 `rejected=2048`, `whole` rejected (`Guardrail column_value_size violated` /
  `collection_size violated` in the error); after flush `big` has no Data.db (`SSTable count: 0`), rows=0; `coll` holds only
  the W2 appends (≈ 8.4 MB, 512 items, logged as violation at flush), not the rejected whole-list insert.
- Wrong if: R1/R2 `big` Data size ≤ threshold or > 1 % below R0, rows < 2048, list < 512, a client rejection in W1/W2, or a
  flush/compaction error.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| R1/R2 disk size and readable rows/items equal R0; violation lines present with size > threshold; RC shows W1 fully rejected and no `big` sstable | Claim confirmed: the thresholds do not govern disk use at sstable write; a binding cap on the same workload is visible to the same instruments |
| R1/R2 disk size falls toward 64/16 MiB, rows/items lost, or flush/compaction fails | Claim refuted: usage follows the threshold |
| No violation lines in R1/R2 and sizes equal R0 | Not confirmed: limit not reached or knob not loaded (check `getguardrailsconfig`) |
| RC W1 not rejected or `big` sstable written | Not confirmed: positive control did not move (likely client is a superuser / auth not enabled) |
| R1/R2 sizes differ from R0 by > 1 % without lost rows | Investigate (e.g. an auto flush splitting the partition); decide on post-compaction numbers |

**B3h. Controls.**
- R0 baseline with identical bytes (`Random(208)`), schema, compression off, and autocompaction off.
- RC positive control on the same workload and same user shows a query-time cap empties the sstable.
- The `getguardrailsconfig` output proves each knob was loaded; the log lines prove the check fired with N > T.
- Fresh data directories per run, so no residue from a previous run adds to `du`.
- Same ordinary user in all runs, so auth state cannot explain a difference between R0 and R1/R2.

**B4. Risks and cleanup.**
- Disk: unit tier writes < 200 MB under `$W/cassandra/build/test/`; cluster tier < 1 GB per run (128 MiB sstable, compaction
  temporary copy, ~135 MB commit log) under `$RUN`. Both on local disk, checked with `df -h` first. Nothing on shared storage;
  the shared source tree is only read by `rsync`.
- Processes: unit tier JVMs end with `ant`; cluster tier stopped with `nodetool stopdaemon` / `kill $(cat $RUN/pid)`, then
  `pgrep -u $USER -f CassandraDaemon` must print nothing; also `pgrep -u $USER -f O208Client`.
- Ports: non-default ports checked free before start.
- Cleanup: `rm -rf $RUN/data $RUN/commitlog $RUN/hints $RUN/saved_caches` after recording; `rm -rf $W` when the case is done.

## C. Sources read

src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java
src/java/org/apache/cassandra/db/guardrails/Threshold.java
src/java/org/apache/cassandra/db/guardrails/MaxThreshold.java
src/java/org/apache/cassandra/db/guardrails/Guardrail.java
src/java/org/apache/cassandra/db/guardrails/Guardrails.java
src/java/org/apache/cassandra/db/guardrails/GuardrailsMBean.java
src/java/org/apache/cassandra/db/guardrails/GuardrailEvent.java
src/java/org/apache/cassandra/db/guardrails/GuardrailsDiagnostics.java
src/java/org/apache/cassandra/db/guardrails/GuardrailViolatedException.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/config/GuardrailsOptions.java
src/java/org/apache/cassandra/service/ClientState.java
src/java/org/apache/cassandra/cql3/Lists.java
src/java/org/apache/cassandra/cql3/Sets.java (grep)
src/java/org/apache/cassandra/cql3/Maps.java (grep)
src/java/org/apache/cassandra/db/rows/ComplexColumnData.java
src/java/org/apache/cassandra/io/util/SequentialWriter.java
src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java
src/java/org/apache/cassandra/io/sstable/format/SortedTablePartitionWriter.java
src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java
src/java/org/apache/cassandra/io/sstable/format/bti/BtiTableWriter.java
src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java
src/java/org/apache/cassandra/io/sstable/SSTableRewriter.java
src/java/org/apache/cassandra/db/memtable/Flushing.java
src/java/org/apache/cassandra/tools/nodetool/GuardrailsConfigCommand.java
src/java/org/apache/cassandra/tools/nodetool/stats/TableStatsPrinter.java
conf/cassandra.yaml
conf/cassandra-env.sh
CHANGES.txt
NEWS.txt
build.xml
.build/cassandra-deps-template.xml
.build/parent-pom-template.xml
test/unit/org/apache/cassandra/db/guardrails/GuardrailPartitionSizeTest.java
test/unit/org/apache/cassandra/db/guardrails/GuardrailTester.java
test/unit/org/apache/cassandra/db/guardrails/ThresholdTester.java (grep)
test/unit/org/apache/cassandra/db/guardrails/GuardrailCollectionSizeTest.java (grep)
test/unit/org/apache/cassandra/cql3/CQLTester.java
test/distributed/org/apache/cassandra/distributed/test/guardrails/GuardrailPartitionSizeTest.java
test/distributed/org/apache/cassandra/distributed/test/guardrails/GuardrailCollectionSizeOnSSTableWriteTest.java
https://issues.apache.org/jira/browse/CASSANDRA-18500 (cited from CHANGES.txt, not fetched)
https://issues.apache.org/jira/browse/CASSANDRA-17153 (cited from CHANGES.txt, not fetched)

## D. Stage-4 feedback

none yet
