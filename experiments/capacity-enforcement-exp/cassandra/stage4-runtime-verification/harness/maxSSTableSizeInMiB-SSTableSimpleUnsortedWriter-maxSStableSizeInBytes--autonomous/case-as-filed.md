# maxSSTableSizeInMiB (CQLSSTableWriter buffer size) — verification solution  <!-- file: cases/maxSSTableSizeInMiB-SSTableSimpleUnsortedWriter-maxSStableSizeInBytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (a capacity-set place: the byte limit of the unsorted writer's in-memory buffer is set), **linked**: [`SSTableSimpleUnsortedWriter.java:74`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java#L74) — `this.maxSStableSizeInBytes = maxSSTableSizeInMiB * 1024L * 1024L;` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `positive` — the value set at line 74 is the threshold at which the unsorted bulk writer hands its buffered partitions to the disk thread and starts an empty buffer ([`:110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java#L110) then `sync()` at :153-161), so the heap that buffered rows hold, and the size of each SSTable written, follow the knob. Two qualifications: the counted quantity is the *serialized* size, not heap bytes, so heap is a constant multiple of the knob (about 1-2x per buffer, up to 2 buffers live); and a workload of partition-level DELETEs is never checked (bypass, A3). |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**

- **Name:** `maxSSTableSizeInMiB`, the "buffer size" / "max SSTable size" of the bulk SSTable
  writer API `org.apache.cassandra.io.sstable.CQLSSTableWriter`. Set by the builder methods
  `withMaxSSTableSizeInMiB(int)` (5.0), and the deprecated aliases `withBufferSizeInMiB(int)`
  (deprecated since 5.0, CQLSSTableWriter.java:563-567) and `withBufferSizeInMB(int)`
  (deprecated since 4.1, CQLSSTableWriter.java:583-587), which both forward to it.
- **Kind:** a client-side configuration entry of a public Java API (a builder parameter). It is
  not a `cassandra.yaml` key, not a `-D` property and not a JMX attribute. A running Cassandra node
  never constructs this writer: in `src/java` the only constructor call of
  `SSTableSimpleUnsortedWriter` is CQLSSTableWriter.java:740 (`grep -rln SSTableSimpleUnsortedWriter src`
  finds only the class itself, `CQLSSTableWriter`, and `SSTableSimpleWriter`'s javadoc). The
  stress tool has its own copy (`tools/stress/.../StressCQLSSTableWriter.java:367`,
  `bufferSizeInMiB = 128`), which is not this constraint.
- **First declared:** the builder field
  [`CQLSSTableWriter.java:407`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java#L407)
  (`private long maxSSTableSizeInMiB = -1L;`), with its unsorted default the constant
  [`CQLSSTableWriter.java:395`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java#L395)
  (`DEFAULT_BUFFER_SIZE_IN_MIB_FOR_UNSORTED = 128L`).
- **Unit:** MiB in the API; converted to bytes at the target line 74 (`* 1024L * 1024L`, long
  arithmetic, no overflow for any `int` input).
- **Default and derivation:** the field starts at `-1`. In `build()`
  (CQLSSTableWriter.java:676-680), if the value is `<= 0` (`isMaxSSTableSizeUnset()`, :761-764)
  it becomes `-1` for the sorted writer (no limit) and `128` for the unsorted writer. So for the
  unsorted writer (the default, `sorted = false` at :406) the effective limit is
  `128 MiB = 134217728 bytes`, and any non-positive value given by the user (which logs a warning
  at :539-544 saying it "disables the size limiting") is silently replaced by 128 MiB: the unsorted
  limit cannot be disabled.
- **How it is set / restart:** per writer instance, in Java code, before `build()`. It is read
  once into the final field at line 74; changing it means building a new writer. No restart
  concept (no server).

**A2. What it caps.**

- **Resource:** heap of the process that runs `CQLSSTableWriter` (the bulk-load client JVM),
  through the size of the in-memory `Buffer` (a `TreeMap<DecoratedKey, PartitionUpdate.Builder>`,
  SSTableSimpleUnsortedWriter.java:204). Secondary: the size of each SSTable written to disk
  (each buffer becomes one SSTable, :216-225); the *total* disk output is not capped.
- **Quantity compared:** `currentSize`, the running sum of
  `PartitionUpdate.serializer.serializedSize(...)` of an empty update for each new partition in the
  buffer (:89) plus `UnfilteredSerializer.serializer.serializedSize(row, ...)` of each row added
  (:103). This is a serialized size at the messaging version, not heap bytes; the class's own
  comment (:98-102) says the count "is closer to the serialized value" while the buffer "will take a
  lot more space in memory" and that the size "is first and foremost used to avoid OOM".

**A3. Mechanism.**

1. `CQLSSTableWriter.Builder.build()` resolves the value (:676-680) and, when not sorted,
   constructs `new SSTableSimpleUnsortedWriter(directory, ref, columns, maxSSTableSizeInMiB)`
   (:738-740).
2. The constructor sets the byte limit at
   [`SSTableSimpleUnsortedWriter.java:74`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java#L74)
   and starts the `DiskWriter` thread (:77).
3. Each `addRow`/`rawAddRow` (CQLSSTableWriter.java:265-316) calls `writer.getUpdateFor(key)`; for a
   key not yet in the buffer, :85-91 adds the serialized size of an empty partition update to
   `currentSize` and puts a new builder in the `TreeMap`. **No check here.**
4. The statement adds rows to that builder; the anonymous builder's `add(Row)` (:126-131) adds the
   row, counts it (`countRow`, :103) and calls `maybeSync()`.
5. **The check:**
   [`SSTableSimpleUnsortedWriter.java:110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java#L110)
   `if (currentSize > maxSStableSizeInBytes) sync();`
   - **true:** `sync()` (:153-161) puts the whole buffer on `writeQueue` and replaces it with a new
     empty `Buffer`, `currentSize = 0`. `writeQueue` is `newBlockingQueue(0)` (:68), which is a
     `SynchronousQueue` (utils/concurrent/BlockingQueues.java:43-47), so `put` (:163-178) blocks
     the caller until the `DiskWriter` takes it. The `DiskWriter` (:206-237) writes the buffer as
     one SSTable and drops it. Hence at most two buffers are live: the one the disk thread is
     writing and one full buffer waiting in `put` (the caller cannot add while it waits).
   - **false:** the row stays in the buffer; no other action.
   - An `IOException` from the disk thread surfaces as `SyncException` (:113-118), unwrapped in
     CQLSSTableWriter.java:311-316.
6. `close()` (:136-151) syncs the last buffer, sends a sentinel and joins the disk thread.

**Overshoot and bypass paths.**

- **One row overshoot:** the check runs after the row is counted, so the buffer (and its SSTable)
  can exceed the limit by one row plus one partition header. A single row larger than the limit
  produces an SSTable larger than the limit (test `testSyncWithinPartition`, test/unit/.../CQLSSTableWriterTest.java:220-246, relies on this).
- **Partition-header-only updates are never checked:** `getUpdateFor` (:89) grows `currentSize`
  without calling `maybeSync()`. A partition-level DELETE (`DELETE FROM t WHERE k = ?`) only calls
  `addPartitionDeletion` (cql3/statements/DeleteStatement.java:70-72), never `add(Row)`, so a
  DELETE-only workload buffers every partition until `close()`, regardless of the knob.
- **Heap is not what is counted:** in-memory objects (TreeMap entries, `DecoratedKey`s, cell and
  row objects, `ByteBuffer` wrappers) are not counted; heap per buffer is a multiple of the knob.
  Re-writing the same row overcounts (each `add` is counted although rows merge), making syncs
  earlier, not later.
- **Sorted writer:** with `.sorted()` the same value is passed to `SSTableSimpleWriter`, which
  uses it differently: it switches SSTable when `getOnDiskBytesWritten() > maxSSTableSizeInBytes`
  (SSTableSimpleWriter.java:103-106) and keeps only one partition in memory; the default there is
  no limit.

**A4. Other consumers.**

- Heap of the same JVM outside the buffer: the disk thread's SSTable writer (`SSTableTxnWriter`,
  index/summary/statistics builders), the schema and keyspace metadata loaded in client mode, the
  per-partition garbage from :89 (an update is built just to size it), the user's own objects,
  and SAI index building when `withIndexes` is used.
- Off-heap: bloom filter and compression buffers of the SSTable being written (not governed).
- Disk: the total size of all SSTables written (the knob only splits it into pieces); the
  non-Data components (Index/Partitions/Rows, Filter, Summary, Statistics, TOC, Digest); compression
  shrinks `Data.db` below the serialized size.
- On a node, after `sstableloader`: the node's disk and memtables, governed by node settings, not
  by this value.

**A5. Evidence beyond the source.**

- Builder javadoc, CQLSSTableWriter.java:549-562: "This defines how much data will be buffered
  before being written as a new SSTable ... The default is 128MiB, which should be reasonable for
  a 1GiB heap. If you experience OOM while using the writer, you should lower this value."
- Docs: `doc/modules/cassandra/pages/managing/operating/bulk_loading.adoc:836-841`
  (`withBufferSizeInMiB`: buffer size, default 128MB) and :847-855 (sorted writer ignores it; stale
  since CASSANDRA-18941).
- CHANGES.txt:386 CASSANDRA-18941 (max SSTable size in sorted writer, which introduced
  `withMaxSSTableSizeInMiB`); CHANGES.txt:842 CASSANDRA-17675 (deprecation of `withBufferSizeInMB`);
  CHANGES.txt:4402 CASSANDRA-7360 (sync within partitions); CHANGES.txt:3745 CASSANDRA-9071.
- Tests: `CQLSSTableWriterTest.testSyncWithinPartition` (:220-246) and `testSyncNoEmptyRows`
  (:248-268) use a 1 MiB buffer; `CQLSSTableWriterClientTest` (:28-49) shows client-mode setup.
- JDK: `java.util.concurrent.SynchronousQueue` (capacity zero, `offer` with timeout waits for a
  taker), https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/SynchronousQueue.html

## B. Verification solution

**B1. Claim under test.** For the unsorted `CQLSSTableWriter`, the value set at line 74 bounds
the buffered data: every buffer hand-off happens when the serialized count first exceeds
`knob x 2^20` bytes (so each SSTable's `Data.db` is at most the knob plus one row), and the heap
retained by buffered rows grows linearly with the knob and stays within two buffers' worth;
conversely, a partition-DELETE-only workload is not bounded by it.

### B2. Unit tier

**B2a. Environment and build.**

- Linux, JDK 11 (`java -version` 11.x), Ant 1.10+.
- Copy the tree to local disk, never build in the shared copy:
  `SRC=/mydata/$USER-s4/cassandra-5.0.9; rsync -a <shared copy of tag cassandra-5.0.9>/ $SRC/`
  (`RUN` below is also on local disk with at least 4 GiB free:
  `RUN=/mydata/$USER-s4/maxsstable; mkdir -p $RUN`).
- `cd $SRC && ant -q jar` (first build downloads dependencies to `build/lib/jars`).
- Test source: add the file below as
  `$SRC/test/unit/org/apache/cassandra/io/sstable/MaxSSTableSizeProbeTest.java` (local copy only).
- JVM: the `testsome` target forks with `maxmemory="1024m"` (build.xml:1153); probe parameters go
  through `-Dtest.jvm.args` (build.xml:1192).

```java
package org.apache.cassandra.io.sstable;

import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.*;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.CassandraRelevantProperties;
import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.utils.ByteBufferUtil;

public class MaxSSTableSizeProbeTest
{
    static final String OUT  = System.getProperty("probe.out");                 // existing empty dir .../probe_ks/t
    static final int    MIB  = Integer.getInteger("probe.mib", -1);             // -1: builder method not called
    static final String MODE = System.getProperty("probe.mode", "unsorted");    // unsorted | sorted | delete
    static final int    ROWS = Integer.getInteger("probe.rows", 147456);
    static final int    VAL  = Integer.getInteger("probe.value", 1024);         // blob bytes per row
    static final int    RPP  = Integer.getInteger("probe.rpp", 16);             // rows per partition

    @BeforeClass
    public static void setUp()
    {
        DatabaseDescriptor.clientInitialization(true, () -> { Config c = new Config(); c.data_file_directories = new String[]{ OUT }; return c; });
        CassandraRelevantProperties.FORCE_LOAD_LOCAL_KEYSPACES.setBoolean(true);
        DatabaseDescriptor.setPartitionerUnsafe(Murmur3Partitioner.instance);
        Keyspace.setInitialized();
    }

    static long heapAfterGc()
    {
        for (int i = 0; i < 3; i++) System.gc();
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    @Test
    public void probe() throws Exception
    {
        String schema = "CREATE TABLE probe_ks.t (k bigint, c int, v blob, PRIMARY KEY (k, c)) WITH compression = {'enabled': 'false'}";
        boolean delete = MODE.equals("delete");
        String stmt = delete ? "DELETE FROM probe_ks.t WHERE k = ?" : "INSERT INTO probe_ks.t (k, c, v) VALUES (?, ?, ?)";
        CQLSSTableWriter.Builder b = CQLSSTableWriter.builder().inDirectory(OUT).forTable(schema).using(stmt);
        if (MIB != -1) b.withMaxSSTableSizeInMiB(MIB);
        if (MODE.equals("sorted")) b.sorted();
        CQLSSTableWriter w = b.build();

        Field wf = CQLSSTableWriter.class.getDeclaredField("writer"); wf.setAccessible(true);
        Object sw = wf.get(w);
        Field cs = null; long limit = -1;
        if (sw instanceof SSTableSimpleUnsortedWriter)
        {
            cs = SSTableSimpleUnsortedWriter.class.getDeclaredField("currentSize"); cs.setAccessible(true);
            Field mf = SSTableSimpleUnsortedWriter.class.getDeclaredField("maxSStableSizeInBytes"); mf.setAccessible(true);
            limit = mf.getLong(sw);
        }
        System.out.println("PROBE writer=" + sw.getClass().getSimpleName() + " limitBytes=" + limit);

        // partition keys; for the sorted writer they must be fed in Murmur3 token order
        int parts = delete ? ROWS : (ROWS + RPP - 1) / RPP;
        Long[] keys = new Long[parts];
        for (int p = 0; p < parts; p++) keys[p] = (long) p;
        if (MODE.equals("sorted"))
            Arrays.sort(keys, Comparator.comparing(k -> Murmur3Partitioner.instance.getToken(ByteBufferUtil.bytes(k))));

        long base = heapAfterGc();
        System.out.println("PROBE baselineHeap=" + base);
        Random rnd = new Random(42);
        long prev = 0, maxCs = 0, maxInc = 0; int syncs = 0, heapSamples = 0; boolean sampledThisBuffer = false;
        for (int i = 0; i < ROWS; i++)
        {
            if (delete) w.addRow(keys[i]);
            else
            {
                byte[] v = new byte[VAL]; rnd.nextBytes(v);                 // fresh buffer per row
                w.addRow(keys[i / RPP], i % RPP, ByteBuffer.wrap(v));
            }
            if (cs != null)
            {
                long now = cs.getLong(sw);
                if (now < prev)
                {
                    syncs++; sampledThisBuffer = false;
                    System.out.println("PROBE sync=" + syncs + " preSyncSample=" + prev + " limit=" + limit + " row=" + i);
                }
                else maxInc = Math.max(maxInc, now - prev);
                maxCs = Math.max(maxCs, now); prev = now;
                if (!sampledThisBuffer && heapSamples < 3 && now > 0.95 * limit)
                {
                    sampledThisBuffer = true; heapSamples++;
                    System.out.println("PROBE heapSample=" + heapSamples + " currentSize=" + now + " retained=" + (heapAfterGc() - base));
                }
            }
            else if (i == ROWS / 4 || i == ROWS / 2 || i == 3 * ROWS / 4)
                System.out.println("PROBE sortedHeap row=" + i + " retained=" + (heapAfterGc() - base));
        }
        System.out.println("PROBE syncs=" + syncs + " maxCurrentSize=" + maxCs + " maxIncrement=" + maxInc + " endCurrentSize=" + prev);
        w.close();
        java.io.File[] data = new java.io.File(OUT).listFiles((d, n) -> n.endsWith("-Data.db"));
        Arrays.sort(data, Comparator.comparing(java.io.File::getName));
        long tot = 0;
        for (java.io.File f : data) { tot += f.length(); System.out.println("PROBE data " + f.getName() + " " + f.length()); }
        System.out.println("PROBE dataFiles=" + data.length + " totalDataBytes=" + tot);
    }
}
```

**B2b. Knobs.** `probe.mib` (passed to `withMaxSSTableSizeInMiB`):

| Run | mode | probe.mib | Why |
|---|---|---|---|
| U1 | unsorted | 1 | smallest positive; many hand-offs (count check only, heap too small to read against GC noise) |
| U4 | unsorted | 4 | heap reading, low |
| U16 | unsorted | 16 | heap reading, mid |
| U64 | unsorted | 64 | heap reading, high (2 buffers x ~2 x 64 MiB fits the 1 GiB test heap) |
| Udef | unsorted | -1 (method not called) | checks the derived default of 128 MiB (:679) |
| U0 | unsorted | 0 | checks that a non-positive value is replaced by 128 MiB, not "unlimited" |
| Uinf | unsorted | 1024 | ceiling above the total data: shows what the heap does with no effective cap |
| S16, S64 | sorted | 16, 64 | control: same knob, writer that does not buffer |
| Ubig | unsorted, `-Dprobe.value=3145728 -Dprobe.rpp=1 -Dprobe.rows=5` | 1 | one-row overshoot |
| Udel | delete, `-Dprobe.rows=500000` | 1 | bypass: partition DELETEs never checked |

**B2c. Workload.** Table `probe_ks.t (k bigint, c int, v blob, PRIMARY KEY (k, c))`, compression
off (so `Data.db` approximates the serialized count). Default run: 147456 rows of a fresh random
1024-byte blob, 16 rows per partition (9216 partitions). A serialized row is about 1024 + 10 to
20 bytes, so total serialized data is about 147456 x ~1040 = ~153 MB = ~146 MiB. That passes the
limit about 146 times at 1 MiB, ~36 at 4 MiB, ~9 at 16 MiB, twice at 64 MiB, once at 128 MiB
(default), never at 1024 MiB. Ubig: five 3 MiB rows in distinct partitions, each alone over a
1 MiB limit. Udel: 500000 distinct partition deletes; each empty partition update serializes to
at least 26 bytes (16-byte table id + 8-byte key + length), so `currentSize` reaches at least
~13 MB, more than 12 x the 1 MiB limit, with no row ever added.

**B2d. Observables and instruments.**

- `limitBytes` (the line-74 field, by reflection): the knob in bytes.
- `currentSize` (the check's operand), sampled by reflection after every `addRow`; a drop means a
  hand-off happened in that call; `preSyncSample` is the last sample before it; `maxIncrement` is
  the largest per-call increase (one row plus at most one partition header).
- Retained heap per buffer: used heap after three `System.gc()` calls minus a baseline taken after
  `build()`, at the first moment `currentSize > 0.95 x limit` in each of the first three buffers
  (`java.lang.management.MemoryMXBean`).
- `Data.db` count and sizes after `close()` (`java.io.File.length()`).
- Not directly observable: which objects make up the heap (use `jcmd <pid> GC.class_histogram`
  during a run if needed); `System.gc()` timing relative to the disk thread (heap samples 2-3 may
  include the previous buffer still being written).

**B2e. Procedure.**

```bash
cd $SRC
ant -q build-test                                   # once
run() {  # $1=name, $2=extra -D args
  rm -rf $RUN/u/$1; mkdir -p $RUN/u/$1/probe_ks/t
  ant testsome -Dno-build-test=true \
      -Dtest.name=org.apache.cassandra.io.sstable.MaxSSTableSizeProbeTest \
      -Dtest.jvm.args="-Dprobe.out=$RUN/u/$1/probe_ks/t $2" > $RUN/u/$1.ant.log 2>&1
  grep -h 'PROBE' build/test/output/TEST-org.apache.cassandra.io.sstable.MaxSSTableSizeProbeTest.* $RUN/u/$1.ant.log | sort -u > $RUN/u/$1.probe.txt
  du -sb $RUN/u/$1; rm -rf $RUN/u/$1                # keep the probe text, drop the SSTables
}
run U1   "-Dprobe.mib=1"
run U4   "-Dprobe.mib=4"
run U16  "-Dprobe.mib=16"
run U64  "-Dprobe.mib=64"
run Udef ""
run U0   "-Dprobe.mib=0"
run Uinf "-Dprobe.mib=1024"
run S16  "-Dprobe.mib=16 -Dprobe.mode=sorted"
run S64  "-Dprobe.mib=64 -Dprobe.mode=sorted"
run Ubig "-Dprobe.mib=1 -Dprobe.value=3145728 -Dprobe.rpp=1 -Dprobe.rows=5"
run Udel "-Dprobe.mib=1 -Dprobe.mode=delete -Dprobe.rows=500000"
pgrep -f MaxSSTableSizeProbeTest || echo "no probe JVM left"
```

(If the output file name differs, take the `PROBE` lines from `build/test/output/` or the ant log;
both are captured.) For each run record: `limitBytes`, number of `sync=` lines, all
`preSyncSample` values, `maxIncrement`, `maxCurrentSize`, the `retained` samples, `dataFiles` and
each `Data.db` size.

**B2f. Predictions.** (L = knob x 1048576 bytes; inc = `maxIncrement`, about 1030 to 1100 bytes.)

| Run | limitBytes | hand-offs (`sync=` lines) | Data.db files | Data.db sizes (all but last) | retained heap (sample 1) |
|---|---|---|---|---|---|
| U1 | 1048576 | ~145 (140-150) | syncs + 1 | 0.90 L to 1.05 L | not judged |
| U4 | 4194304 | ~36 (34-38) | syncs + 1 | 0.90 L to 1.05 L | r x L, r in [1.1, 2.0] |
| U16 | 16777216 | 9 (8-10) | syncs + 1 | 0.90 L to 1.05 L | r x L, same r (+-20%) |
| U64 | 67108864 | 2 | 3 | 0.90 L to 1.05 L | r x L, same r (+-20%) |
| Udef | 134217728 | 1 | 2 | 0.90 L to 1.05 L | r x L |
| U0 | 134217728 | 1 | 2 | as Udef | as Udef |
| Uinf | 1073741824 | 0 | 1 | (one file = all data, ~146 MiB) | no 0.95 L sample; heap grows with rows to ~r x 146 MiB |
| S16 / S64 | n/a (sorted writer) | n/a | ~ceil(146/knob) (switch on on-disk bytes) | ~knob | sortedHeap flat: < 16 MiB at 25/50/75%, same for both knobs |
| Ubig | 1048576 | 5 | 5 | each ~3 MiB (> L) | not judged |
| Udel | 1048576 | 0 | 1 | — | `maxCurrentSize` >= 12 x L (>= ~13 MB) |

Relations stated for every unsorted run with at least one hand-off:

- every `preSyncSample <= L` and `preSyncSample + maxIncrement > L` (the check fires on the first
  row that crosses L, never later);
- `maxCurrentSize <= L` (the samples are taken after the reset; a value above L means a row was
  counted without a check);
- retained heap at samples 2-3 `<= 2 x r x L + 8 MiB` (at most two buffers live);
- retained heap / L roughly constant across U4, U16, U64 (linear in the knob).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Hand-off counts, `preSyncSample` bounds and Data.db sizes as predicted; retained heap linear in L with r in [1.1, 2.0] | claim confirmed: the line-74 value bounds buffered data and its heap |
| Udef/U0 show `limitBytes=134217728` | default derivation (:679) confirmed |
| Number of hand-offs does not change with the knob, or `preSyncSample > L` | claim wrong: the check does not use this value as traced |
| `maxCurrentSize > L` in an INSERT run | a row was counted without a check: a bypass not traced in A3 |
| Retained heap at U64 not larger than at U4 (within noise) | buffer heap does not follow the knob: claim wrong for heap (cap would be on SSTable size only) |
| Retained heap / L > 2 x (r at U4) at U64, or sample 2/3 > 2 x r x L + 8 MiB | more than two buffers live, or another consumer grows with the knob: claim partly wrong |
| Uinf retained heap grows with rows past 64 MiB-equivalent while U64 stays bounded | confirms that the knob, not the workload, is what bounds U64 |
| S16 and S64 heap flat and similar while U16/U64 differ | control: heap growth belongs to the unsorted buffer |
| Ubig five ~3 MiB files | one-row overshoot confirmed (bounded by row size, as traced) |
| Udel one file, `maxCurrentSize >= 12 x L` | DELETE bypass confirmed: for that workload usage does not follow the knob |
| Udel shows hand-offs | the bypass is not real; A3 wrong on this point |

**B2h. Controls.**

- Sorted runs (S16/S64) use the same knob, schema and data but no buffer: rules out the knob
  affecting heap through anything other than the unsorted buffer.
- Uinf (knob above data size) shows the uncapped behaviour of the same workload (positive control
  that the workload can move heap past the capped level).
- Compression off and random blob content: `Data.db` size tracks the serialized count, not a
  compression ratio.
- Fresh blob per row: the heap really holds each row's bytes (a shared buffer would hide growth).
- Each run in a fresh forked JVM with the same 1 GiB heap; three `System.gc()` before each heap
  sample; baseline taken after `build()` so schema loading is excluded.

### B3. Cluster tier

n/a as a node setting: no running Cassandra node reads this value (A1: only the client-side
`CQLSSTableWriter` constructs the writer), so pushing a node's configuration to the boundary
cannot exercise it. Instead, this tier runs the constraint where it acts in practice, a real
bulk-load client process with a fixed `-Xmx`, measuring its actual heap (GC log, OOM boundary)
and the actual SSTable files on disk, and then loads one output into a real single node with
`sstableloader` to show the files are the normal input of the node path.

**B3a. Environment and build.**

- One Linux node, JDK 11, the build of B2a (`$SRC/build/apache-cassandra-5.0.9-SNAPSHOT.jar`
  and `$SRC/build/lib/jars/*`; if the jar is named without `-SNAPSHOT`, use that name).
- Program `$RUN/p/BulkProbe.java` (outside the source tree):

```java
import java.nio.ByteBuffer;
import java.util.Random;
import org.apache.cassandra.io.sstable.CQLSSTableWriter;

public class BulkProbe
{
    public static void main(String[] a) throws Exception
    {
        int mib = Integer.parseInt(a[0]);      // -1: do not call withMaxSSTableSizeInMiB
        int rows = Integer.parseInt(a[1]);
        String out = a[2];                     // existing empty dir .../probe_ks/t
        String schema = "CREATE TABLE probe_ks.t (k bigint, c int, v blob, PRIMARY KEY (k, c)) WITH compression = {'enabled': 'false'}";
        CQLSSTableWriter.Builder b = CQLSSTableWriter.builder().inDirectory(out).forTable(schema)
                                                     .using("INSERT INTO probe_ks.t (k, c, v) VALUES (?, ?, ?)");
        if (mib != -1) b.withMaxSSTableSizeInMiB(mib);
        CQLSSTableWriter w = b.build();
        Random r = new Random(42);
        long t0 = System.nanoTime();
        for (int i = 0; i < rows; i++)
        {
            byte[] v = new byte[1024]; r.nextBytes(v);
            w.addRow((long) (i / 16), i % 16, ByteBuffer.wrap(v));
        }
        w.close();
        System.out.println("BULK done rows=" + rows + " secs=" + (System.nanoTime() - t0) / 1e9);
        System.exit(0);
    }
}
```

```bash
CP="$SRC/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$SRC/build/lib/jars/*"
JOPTS="$(grep -v '^#' $SRC/conf/jvm11-clients.options | grep -v '^$' | xargs)"
mkdir -p $RUN/p && cd $RUN/p && javac -cp "$CP" BulkProbe.java
```

- Node for the load step: `CASSANDRA_CONF=$RUN/conf` (copy of `$SRC/conf`), in
  `$RUN/conf/cassandra.yaml` set `data_file_directories: [$RUN/node/data]`,
  `commitlog_directory: $RUN/node/commitlog`, `hints_directory: $RUN/node/hints`,
  `saved_caches_directory: $RUN/node/saved_caches`, `cdc_raw_directory: $RUN/node/cdc_raw`
  (literal paths), listen/rpc on `127.0.0.1`. Heap `MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M`,
  `CASSANDRA_LOG_DIR=$RUN/node/logs`. Check ports 7000, 9042, 7199 are free first
  (`ss -ltn | grep -E ':(7000|9042|7199) '` empty).

**B3b. Knobs.** The `mib` argument: 16, 64, -1 (default 128), 256, each at `-Xmx2g`; and the OOM
boundary pair 16 and 256 at `-Xmx256m`. 16/64/128/256 span a 16x range so heap differences are far
above GC noise; 256 MiB of serialized payload cannot fit in a 256 MiB heap while 16 MiB can.

**B3c. Workload.** 524288 rows of 1 KiB random blob, 16 per partition (32768 partitions):
~524288 x 1040 = ~545 MB = ~520 MiB serialized, so every knob value (up to 256 MiB) is reached at
least twice. Duration: a few minutes per run (dominated by writing ~520 MiB). Disk per run
~520 MiB, deleted after each run except the one kept for loading.

**B3d. Observables and instruments.**

- JVM heap: unified GC log `-Xlog:gc:file=$RUN/p/gc-<name>.log`; per log, the maximum of the
  post-GC heap figure (`A->B(C)`, take B) over all pauses = peak heap after collection; plus exit
  status and `java.lang.OutOfMemoryError` in stdout/stderr.
- Process RSS: `ps -o rss= -p <pid>` every 1 s (secondary).
- Disk: `ls -l *-Data.db` (count, sizes) and `du -sb` of the output directory.
- Node: `nodetool tablestats probe_ks.t` (SSTable count, space used live), `cqlsh` row check.
- Not observable directly: how much of the post-GC heap is the buffer (young-GC pauses leave
  garbage in old regions; the OOM pair gives the decisive reading).

**B3e. Procedure.**

```bash
cd $RUN/p
bulk() {  # $1=name $2=mib $3=Xmx
  rm -rf $RUN/p/out-$1; mkdir -p $RUN/p/out-$1/probe_ks/t
  ( java $JOPTS -Xmx$3 -Xlog:gc:file=$RUN/p/gc-$1.log -cp "$CP:." BulkProbe $2 524288 $RUN/p/out-$1/probe_ks/t \
      > $RUN/p/$1.out 2>&1; echo "exit=$?" >> $RUN/p/$1.out ) &
  P=$!; while kill -0 $P 2>/dev/null; do ps -o rss= --ppid $P >> $RUN/p/rss-$1.txt; sleep 1; done
  ls -l $RUN/p/out-$1/probe_ks/t/*-Data.db > $RUN/p/data-$1.txt 2>/dev/null; du -sb $RUN/p/out-$1 >> $RUN/p/data-$1.txt
  grep -oE '[0-9]+M->[0-9]+M' $RUN/p/gc-$1.log | sed 's/.*->//; s/M//' | sort -n | tail -1 > $RUN/p/peak-$1.txt
}
bulk m16  16  2g; rm -rf $RUN/p/out-m16
bulk m64  64  2g; rm -rf $RUN/p/out-m64
bulk mdef -1  2g; rm -rf $RUN/p/out-mdef
bulk m256 256 2g; rm -rf $RUN/p/out-m256
bulk x16  16  256m; rm -rf $RUN/p/out-x16
bulk x256 256 256m; rm -rf $RUN/p/out-x256
bulk m16  16  2g                                   # rerun, output kept for the load step
pgrep -f BulkProbe || echo "no BulkProbe left"

# load step (single node)
cd $SRC && CASSANDRA_CONF=$RUN/conf CASSANDRA_LOG_DIR=$RUN/node/logs MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M bin/cassandra -p $RUN/node.pid
until bin/nodetool status 2>/dev/null | grep -q '^UN'; do sleep 5; done   # (use the Monitor/poll of your runner)
bin/cqlsh 127.0.0.1 -e "CREATE KEYSPACE probe_ks WITH replication = {'class':'SimpleStrategy','replication_factor':1};
  CREATE TABLE probe_ks.t (k bigint, c int, v blob, PRIMARY KEY (k, c)) WITH compression = {'enabled': 'false'};"
bin/sstableloader -d 127.0.0.1 --no-progress $RUN/p/out-m16/probe_ks/t
bin/nodetool flush probe_ks t; bin/nodetool tablestats probe_ks.t > $RUN/p/node-tablestats.txt
bin/cqlsh 127.0.0.1 -e "SELECT count(*) FROM probe_ks.t WHERE k = 0; SELECT count(*) FROM probe_ks.t WHERE k = 32767;" > $RUN/p/node-cqlsh.txt
```

**B3f. Predictions.**

| Run | Data.db files | Data.db sizes (all but last) | total `du -sb` | peak post-GC heap | exit |
|---|---|---|---|---|---|
| m16 (2g) | ~33 (31-35) | 15-17 MiB each | ~520-560 MiB | lowest of the four; < 150 MiB | 0 |
| m64 (2g) | ~9 (8-10) | 58-67 MiB | same as m16 (+-2%) | > m16 | 0 |
| mdef (2g) | 5 | 115-135 MiB | same | > m64 | 0 |
| m256 (2g) | 3 | 230-270 MiB | same | > mdef; >= 256 MiB (one buffer >= 256 MiB of payload) | 0 |
| x16 (256m) | ~33 | as m16 | same | < 256 MiB | 0, `BULK done` |
| x256 (256m) | — | — | — | — | non-zero, `OutOfMemoryError` (before or at the first hand-off) |

Relations: peak post-GC heap strictly increases m16 < m64 < mdef < m256; total output bytes do
not depend on the knob; per-file size tracks the knob. Node: `tablestats` live space and row
checks consistent with the loaded data (each `count(*)` = 16).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Per-file sizes track the knob; peak heap increases with the knob; x16 completes and x256 OOMs at the same `-Xmx` | claim confirmed on the real process: the knob decides how much heap the bulk writer needs |
| x256 completes at 256m | buffer heap does not reach the knob's size (r < 1 or the buffer is not retained): heap side of the claim wrong |
| x16 OOMs at 256m | something other than the buffer dominates heap (A4 consumer): claim wrong as a heap cap |
| Peak heap flat across 16..256 | heap does not follow the knob: claim wrong for heap |
| Total `du -sb` changes strongly with the knob | the knob affects total disk, contrary to A2 (needs explanation) |
| Any Data.db larger than the knob plus one row (~1.1 KiB) | check bypassed for INSERTs: claim wrong |
| Node load fails or counts differ | output files are not valid node input; the load step, not the claim, failed |

**B3h. Controls.**

- Same program, rows, seed and `-Xmx` across knob runs; only the `mib` argument changes.
- The OOM pair holds `-Xmx` fixed at 256m and varies only the knob: whether the process completes
  depends on the knob alone (positive control: the 256 MiB run shows the workload can push heap
  past the bound that the 16 MiB run stays under).
- Compression off: per-file sizes reflect the serialized count.
- Node step uses a fresh data directory on `$RUN`, so `tablestats` reflects only the loaded files.

**B4. Risks and cleanup.**

- Disk: unit tier at most ~150 MiB per run, deleted after each run (`run()` removes it); process
  tier ~520-560 MiB per run, deleted after each run; node load ~520 MiB in `$RUN/node`. Keep
  everything under `$RUN` on local disk with >= 4 GiB free; nothing under the shared tree.
- Memory: unit JVM 1 GiB; process runs 2 GiB max; node 1 GiB heap plus off-heap. Do not run tiers
  concurrently on a small node.
- Processes: after the node step:
  `cd $SRC && bin/nodetool stopdaemon || kill $(cat $RUN/node.pid)`;
  then check `pgrep -f CassandraDaemon`, `pgrep -f BulkProbe`, `pgrep -f MaxSSTableSizeProbeTest`
  and `pgrep -f 'org.apache.tools.ant'` all return nothing (kill any leftover started by the run).
- Cleanup: `rm -rf $RUN/u $RUN/p/out-* $RUN/node` after recording results; keep `*.probe.txt`,
  `gc-*.log`, `data-*.txt`, `peak-*.txt`, `node-*.txt`. Remove the added test file only from the
  local copy (`$SRC`), never from the shared tree.

## C. Sources read

src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java
src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java
src/java/org/apache/cassandra/io/sstable/AbstractSSTableSimpleWriter.java
src/java/org/apache/cassandra/io/sstable/SSTableSimpleWriter.java
src/java/org/apache/cassandra/io/sstable/SSTableTxnWriter.java (finish, :103-108)
src/java/org/apache/cassandra/utils/concurrent/BlockingQueues.java
src/java/org/apache/cassandra/cql3/statements/DeleteStatement.java (:59-124)
src/java/org/apache/cassandra/db/partitions/PartitionUpdate.java (Builder fields, :836-900)
src/java/org/apache/cassandra/config/DatabaseDescriptor.java (clientInitialization, :319-362)
tools/stress/src/org/apache/cassandra/io/sstable/StressCQLSSTableWriter.java (grep only)
tools/stress/src/org/apache/cassandra/stress/operations/userdefined/SchemaInsert.java (grep only)
test/unit/org/apache/cassandra/io/sstable/CQLSSTableWriterTest.java
test/unit/org/apache/cassandra/io/sstable/CQLSSTableWriterClientTest.java
doc/modules/cassandra/pages/managing/operating/bulk_loading.adoc
build.xml (testsome, testmacro, test.jvm.args, maxmemory)
.build/build-resolver.xml (build/lib/jars)
conf/jvm11-clients.options, conf/cassandra.yaml, conf/cassandra-env.sh, bin/cassandra (grep)
CHANGES.txt, NEWS.txt (grep)
https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/SynchronousQueue.html

## D. Stage-4 feedback

none yet
