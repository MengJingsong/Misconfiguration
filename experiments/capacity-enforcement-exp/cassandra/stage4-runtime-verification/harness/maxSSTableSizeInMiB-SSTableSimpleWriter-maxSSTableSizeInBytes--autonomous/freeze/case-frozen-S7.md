# maxSSTableSizeInMiB (CQLSSTableWriter sorted writer) — verification solution  <!-- file: cases/maxSSTableSizeInMiB-SSTableSimpleWriter-maxSSTableSizeInBytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (a capacity-set place: the field that holds the limit is set), **linked**: [`SSTableSimpleWriter.java:70`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableSimpleWriter.java#L70) — `this.maxSSTableSizeInBytes = maxSSTableSizeInMiB * 1024L * 1024L;` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `positive`. The limit set at line 70 is compared against the bytes already written to the current SSTable's `Data.db` before every partition append, and a new SSTable is started once it is exceeded, so each SSTable's `Data.db` produced by the **sorted** `CQLSSTableWriter` is capped at the limit plus at most one partition (plus one compression chunk when compressed). It caps per-SSTable data-file size only: not the total disk the writer uses, not the other SSTable components, and not heap. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `maxSSTableSizeInMiB`, a field of `CQLSSTableWriter.Builder`, set through the public builder method `withMaxSSTableSizeInMiB(int size)` (and the deprecated aliases `withBufferSizeInMiB(int)` / `withBufferSizeInMB(int)`, which delegate to it, `CQLSSTableWriter.java:564-567`, `:584-587`).
- **Kind:** an API-level (programmatic) configuration value of the offline bulk-writer `CQLSSTableWriter`. It is not a `cassandra.yaml` entry, not a `-D` property, not JMX. It is never read by a running Cassandra node; it is used by client programs that generate SSTables for bulk loading (`nodetool import`, `sstableloader`).
- **First declared:** [`CQLSSTableWriter.java:407`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java#L407) `private long maxSSTableSizeInMiB = -1L;`. It is converted to bytes and stored as `SSTableSimpleWriter.maxSSTableSizeInBytes` (declared `SSTableSimpleWriter.java:49`) at the given line, [`SSTableSimpleWriter.java:70`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableSimpleWriter.java#L70).
- **Unit:** MiB in the builder (`int` argument, stored as `long`); bytes in the writer (`× 1024L × 1024L`, no overflow possible for an `int` input: 2^31 × 2^20 = 2^51 < 2^63).
- **Default and derivation:** builder default `-1L` (`CQLSSTableWriter.java:407`). In `build()`, if the value is unset or non-positive (`isMaxSSTableSizeUnset()` = `maxSSTableSizeInMiB <= 0`, `:761-764`), it becomes `-1` for the sorted writer and `DEFAULT_BUFFER_SIZE_IN_MIB_FOR_UNSORTED = 128` (`:395`) for the unsorted writer (`:677-680`). So for the sorted writer (the class at the given line) the default is **no limit** (one SSTable for all data). `withMaxSSTableSizeInMiB(size <= 0)` logs a warning that this disables size limiting (`:537-547`).
- **How set / restart:** only in code, per writer instance: `CQLSSTableWriter.builder()...sorted().withMaxSSTableSizeInMiB(N).build()`. It is fixed for the life of the writer (`final` field, `SSTableSimpleWriter.java:49`); a change needs a new writer (no node restart involved).
- The sorted writer is selected only when `.sorted()` is called (`CQLSSTableWriter.java:606-610`, `:738-740`); without it the same value goes to `SSTableSimpleUnsortedWriter` (a different, buffer-based mechanism, out of scope of this case except as a control).

**A2. What it caps.** Disk: the size of each individual SSTable's data file (`*-Data.db`) written by the sorted `CQLSSTableWriter`. The quantity compared is `writer.getOnDiskBytesWritten()` of the current `SSTableTxnWriter`, which resolves to the data writer's estimated on-disk bytes:
`SSTableTxnWriter.getOnDiskBytesWritten()` (`SSTableTxnWriter.java:74-77`) → `SimpleSSTableMultiWriter.getOnDiskBytesWritten()` → `writer.getEstimatedOnDiskBytesWritten()` (`SimpleSSTableMultiWriter.java:78-81`) → `SortedTableWriter.getEstimatedOnDiskBytesWritten()` → `dataWriter.getEstimatedOnDiskBytesWritten()` (`SortedTableWriter.java:339-342`). For an uncompressed table the data writer is a `SequentialWriter` whose value is `position()` (`SequentialWriter.java:309-317`, `:271-274`), i.e. logical bytes including the unflushed buffer = the final file length so far. For a compressed table (the default, LZ4, 16 KiB chunks: `CompressionParams.java:48`, `:59-65`) it is `chunkOffset` (`CompressedSequentialWriter.java:128-131`), the compressed bytes of chunks already flushed (incremented at `:203`), so the partially filled current chunk (< 16 KiB uncompressed) is not counted.
It does not count the other components (primary index `Index.db`, `Summary.db`, `Filter.db`, `Statistics.db`, `CompressionInfo.db`/`CRC.db`, `Digest`, `TOC`), nor the total across SSTables.

**A3. Mechanism.**
1. `CQLSSTableWriter.Builder.build()` passes `maxSSTableSizeInMiB` to `new SSTableSimpleWriter(..., maxSSTableSizeInMiB)` when `sorted` (`CQLSSTableWriter.java:738-740`).
2. The constructor stores the byte limit at the given line, [`SSTableSimpleWriter.java:70`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableSimpleWriter.java#L70).
3. Each `addRow(...)` / `rawAddRow(...)` (`CQLSSTableWriter.java:194`, `:265`) calls `writer.getUpdateFor(key)` (`:296`, `:306`). In `SSTableSimpleWriter.getUpdateFor` (`SSTableSimpleWriter.java:73-91`), when the key changes, the previously buffered partition is built and written: `writePartition(update.build())` (`:82-83`). Only one partition is held in memory.
4. `writePartition` → `getOrCreateWriter().append(...)` (`:156-159`). `getOrCreateWriter` (`:112-121`) evaluates the check:
   [`SSTableSimpleWriter.java:105`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableSimpleWriter.java#L105) `return writer == null || (maxSSTableSizeInBytes > 0 && writer.getOnDiskBytesWritten() > maxSSTableSizeInBytes);`
   used by the `if` at [`SSTableSimpleWriter.java:114`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableSimpleWriter.java#L114).
5. **Outcome true (limit exceeded):** `maybeCloseWriter(writer)` finishes and commits the current SSTable (`:116`, `:138-154`; it flushes the residual compressed chunk and writes the index/filter/statistics components), notifies an optional listener, then `createWriter(null)` opens a new SSTable with the next generation id (`:117`; `AbstractSSTableSimpleWriter.java:111-130`). The pending partition goes into the new SSTable. **Outcome false:** append to the current SSTable. Nothing fails or blocks; the limit only controls where files are split.
6. `close()` writes the last buffered partition and finishes the last SSTable (`SSTableSimpleWriter.java:93-98`, `:123-136`).

**Overshoot and bypasses.**
- The check runs *before* appending a partition, against the size *after* the previous partition. A finished non-last SSTable therefore has operand-at-switch in `(L, L + P]`, where `L = maxSSTableSizeInBytes` and `P` is the on-disk size of the last partition appended to it. Uncompressed: final `Data.db` = operand at switch, so `Data.db ∈ (L, L + P]`. Compressed: the operand counts only flushed chunks, so the operand first exceeds `L` by at most the compressed bytes flushed during one append (≤ `ceil(P/16 KiB)` chunks), and on finish one more partial chunk (≤ 16 KiB + 4 B checksum) is flushed: `Data.db ∈ (L, L + P_c + 16 KiB + 4 B]` roughly, with `P_c` the compressed bytes of the partition's chunks.
- **Single large partition:** a partition is never split. A partition bigger than `L` produces an SSTable of about that partition's size, unbounded by `L`.
- **Strict `>`:** an SSTable whose `Data.db` is exactly `L` does not switch.
- **Non-positive value:** `maxSSTableSizeInBytes > 0` guard (`:105`) disables the cap; `build()` also rewrites any `<= 0` to `-1` for the sorted writer (`CQLSSTableWriter.java:677-680`).
- **Other components** (index, filter, summary, statistics) grow alongside but are not counted, so an SSTable's total on-disk footprint exceeds `L` by them.
- **Total disk is not capped:** the writer just produces `≈ ceil(total / L)` SSTables.

**A4. Other consumers.**
- Same disk: the other SSTable components; the total output of the writer; the temporary transaction log files of each `LifecycleTransaction` (`SSTableTxnWriter.create`, `SSTableTxnWriter.java:145-159`); after loading into a node, compaction rewrites the files (node-side compaction strategy decides the final SSTable sizes, independent of this value).
- Heap: the sorted writer keeps one `PartitionUpdate.Builder` (`SSTableSimpleWriter.java:86`) plus the writer's buffers (16 KiB chunk buffer, index/filter builders); none of it depends on this limit. The **unsorted** writer uses the same builder value as an in-memory buffer cap (`SSTableSimpleUnsortedWriter.java:71-74`, `:89-110`), a different mechanism.
- Node-side analogues capping SSTable size during compaction (e.g. `MaxSSTableSizeWriter.java:78`) are separate constraints.

**A5. Evidence beyond the source.**
- `CHANGES.txt:386` — "Support max SSTable size in sorted CQLSSTableWriter (CASSANDRA-18941)"; https://issues.apache.org/jira/browse/CASSANDRA-18941
- In-tree test `test/unit/org/apache/cassandra/io/sstable/CQLSSTableWriterTest.java:1272-1311` (`testWriteWithSortedAndMaxSize`): sorted writer, `withMaxSSTableSizeInMiB(1)`, 30,000 rows of ≈41 B → asserts exactly 2 `Data.db` files and the larger within 50 KiB of 1 MiB. Also `:1324-1385` (listener notification, 2 SSTables). Concrete runner: `CQLSSTableWriterClientTest` (`CQLSSTableWriterClientTest.java:30-53`).
- `doc/modules/cassandra/pages/managing/operating/bulk_loading.adoc:382-530`, `:640-760` (CQLSSTableWriter and `nodetool import` usage).
- No git history is available in the copy (not a git checkout).

## B. Verification solution

**B1. Claim under test.** With the sorted `CQLSSTableWriter` and `withMaxSSTableSizeInMiB(M)`, M > 0, every produced SSTable except the last has `Data.db` size in `(M MiB, M MiB + one partition (+ one 16 KiB compression chunk when compressed)]`, and the number of SSTables is `≈ ceil(total Data bytes / M MiB)`; with M unset or ≤ 0 exactly one SSTable is produced. The claim is wrong if any non-last `Data.db` exceeds that bound, if any non-last `Data.db` is ≤ M MiB, or if the SSTable count does not change with M.

> **Amendment S2 (stage-4 audit, 2026-11-24, before any reading).** The compressed bound above is too tight by derivation from the source, not from any reading. With LZ4 the operand is `chunkOffset`, which advances only in whole flushed chunks of `compressedLength + 4` B (`CompressedSequentialWriter.java:156-203`). `min_compress_ratio` defaults to 0 (`CompressionParams.java:49`, `:187-190`), so `maxCompressedLength` = `Integer.MAX_VALUE` and an expanded chunk is stored as compressed; a chunk is at most `4` (LZ4 length header) `+ LZ4.maxCompressedLength(16,384) = 16,384 + 16,384/255 + 16 = 16,464` (`LZ4Compressor.java:113-116`) `+ 4` (CRC) `= Cmax = 16,472 B`. Since P (≈ 1 KB) < one chunk, one append flushes at most one chunk, so the operand at the switch is in `(L, L + Cmax]`, and finishing flushes at most one more partial chunk. **Compressed claim, as amended:** every non-last `Data.db` ∈ `(L, L + 2·Cmax] = (L, L + 32,944 B]`. A3's "(L, L + P_c + 16 KiB + 4 B]" already has this shape (P_c = the chunk flushed during the append); B1's "one partition + one 16 KiB chunk" and B2f's "L + P + 16,388" put P where P_c belongs and omit the LZ4 header and expansion. The uncompressed claim is unchanged.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11 (`java -version` shows 11), Apache Ant ≥ 1.10, ~3 GB free local disk.
- Copy the tree to local disk: `export S4=<local-disk dir, e.g. /mydata/$USER-s4-o117>; mkdir -p $S4; rsync -a <shared source>/ $S4/cassandra-5.0.9/` (never build in the shared tree).
- `cd $S4/cassandra-5.0.9 && ant jar build-test` (`-Duse.jdk11=true` not needed on 5.0 with JDK 11).

> **Amendment S1 (stage-4 audit, 2026-11-24).** Node `ms0640` (CloudLab Utah m400, aarch64). `S4=/mydata/jingsong-cass-s4/o117`. The tree is `cp -a /mydata/s4/cassandra-base $S4/cassandra-5.0.9` (the node's copy of the repository source made with `copy-source.sh` and already built with `ant build-test`), not a fresh rsync and full build. The probe is compiled by `ant build-test` after it is copied in, and both `testsome` calls then use `-Dno-build-test=true`. Harness from `/users/jason92/writeup-ext/out/o117/harness/`, copied to `$S4/harness/`. `testsome` writes `build/test/output/TEST-<class>.xml`; the console of each call is kept in `$S4/logs/`.
>
> **Amendment S6 (stage-4 audit, 2026-11-25, before any reading of this run).** The 2026-11-24 run on `ms0640` was interrupted and its partial outputs are set aside unread. This run is on node **`pc82`** (`node1.jason92-326665`, CloudLab UMass, **x86_64**, 40 cores, 125 GiB, Ubuntu 22.04 / `5.15.0-203-generic`, JDK 11.0.33, Ant 1.10.12), not `ms0640`. Everything else in S1 and S4 stands: `S4=/mydata/jingsong-cass-s4/o117`, `cp -a /mydata/s4/cassandra-base`, harness from `/users/jason92/writeup-ext/out/o117/harness/` copied to `$S4/harness/`. The node changes no claim, prediction or reading rule (the operand and bounds are platform-independent byte counts).
- Test source location: `$S4/cassandra-5.0.9/test/unit/org/apache/cassandra/io/sstable/MaxSSTableSizeProbeTest.java` (same package as the package-private `SSTableSimpleWriter`). JVM options: the defaults of `ant testsome` (test heap from `build.xml`); export `PROBE_DIR=$S4/probe-unit` and `PROBE_OUT=$S4/probe-unit.csv` (environment is inherited by the forked JUnit JVM).

**B2b. Knobs.** `M = withMaxSSTableSizeInMiB(M)`:
- `1`, `4`, `16`: cap binds several times on a ≈ 58 MiB data set (≈ 58, 15, 4 SSTables), spanning a 16× range so the count must scale with M.
- `0` and *not called*: the disabled/default path (`-1`) → negative control (1 SSTable).
- Each with table compression `{'enabled':'false'}` (operand = exact logical position) and default LZ4 (operand = flushed chunk offset), to test both operand definitions.
- Large-partition case: `M = 1`, uncompressed, partition 0 of 5,000 rows.
- Control writer: unsorted (no `.sorted()`), `M = 4`.

**B2c. Workload.** Table `probe_ksN.t (k int, c int, v blob, PRIMARY KEY (k, c))`, `ByteOrderedPartitioner` (as `CQLSSTableWriterClientTest` does) so increasing non-negative `int` keys are in partitioner order. `N = 60,000` partitions, one row each, `v` = 1,000 random bytes (`new Random(42)`, incompressible, so LZ4 stores chunks ≈ raw). Per partition on disk ≈ 1,000 B value + ≈ 15–30 B key/row/cell framing ⇒ `P ≈ 1.02–1.03 KB`; total `Data.db` ≈ 60,000 × 1.025 KB ≈ 61.5 MB ≈ 58.7 MiB, i.e. 58× the M = 1 limit and 3.7× the M = 16 limit. Large-partition case: partition 0 has 5,000 rows × 1,000 B ≈ 5.1 MB ≈ 4.9 MiB (≈ 4.9× M = 1), then partitions 1..2,999 with one row each (≈ 3.0 MB).

**B2d. Observables and instruments.**
- **Operand at each switch:** after every `addRow`, read via reflection `CQLSSTableWriter.writer` (an `SSTableSimpleWriter`) → its private `writer` (`SSTableTxnWriter`) → `getOnDiskBytesWritten()`. When the `SSTableTxnWriter` instance changes, the last value seen for the previous instance is the operand at the check that returned true (nothing is written between the return of `addRow(k)` and the check inside `addRow(k+1)`; see A3 step 3–4).
- **Limit actually set (given line):** reflection read of `SSTableSimpleWriter.maxSSTableSizeInBytes`.
- **Result files:** after `close()`, each SSTable's `Data.db` length and the sum of all its components (grouped by the generation id in the file name), sorted by generation (= production order; the sorted writer is synchronous).
- Output: CSV lines to `$PROBE_OUT`: `run,M,compressed,limitBytes,sstableIdx,dataBytes,allComponentsBytes,operandAtSwitch`.
- Not observable directly: the exact per-partition on-disk size `P`; derive it as `(sum of Data.db) / partitions` for the run.

**B2e. Procedure.**
1. Write the probe test (below) into the copy.
2. `cd $S4/cassandra-5.0.9 && rm -rf $PROBE_DIR $PROBE_OUT && mkdir -p $PROBE_DIR`
3. Positive control first: `ant testsome -Dtest.name=org.apache.cassandra.io.sstable.CQLSSTableWriterClientTest -Dtest.methods=testWriteWithSortedAndMaxSize -Dno-build-test=true` — must pass.
4. `ant testsome -Dtest.name=org.apache.cassandra.io.sstable.MaxSSTableSizeProbeTest -Dno-build-test=true` (after `ant build-test` has compiled the new file; or omit `-Dno-build-test`).
5. `column -s, -t $PROBE_OUT | less`; compute per run: SSTable count, max/min non-last `Data.db`, `P = sum(Data)/partitions`, `(Data.db − L)` per non-last SSTable.
6. `rm -rf $PROBE_DIR` (the test also deletes each run's directory after measuring).

Probe (`MaxSSTableSizeProbeTest.java`):

```java
package org.apache.cassandra.io.sstable;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.*;
import org.junit.BeforeClass;
import org.junit.Test;
import org.apache.cassandra.config.*;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.dht.ByteOrderedPartitioner;
import org.apache.cassandra.io.util.File;

public class MaxSSTableSizeProbeTest
{
    static final int UNSET = Integer.MIN_VALUE;
    static final String BASE = System.getenv().getOrDefault("PROBE_DIR", System.getProperty("java.io.tmpdir") + "/probe-unit");
    static final String OUT  = System.getenv().getOrDefault("PROBE_OUT", BASE + ".csv");
    static int seq = 0;

    @BeforeClass
    public static void setup()
    {
        new File(BASE).tryCreateDirectories();
        DatabaseDescriptor.clientInitialization(true, () -> { Config c = new Config(); c.data_file_directories = new String[]{ BASE }; return c; });
        CassandraRelevantProperties.FORCE_LOAD_LOCAL_KEYSPACES.setBoolean(true);
        DatabaseDescriptor.setPartitionerUnsafe(ByteOrderedPartitioner.instance);
        Keyspace.setInitialized();
    }

    @Test
    public void probe() throws Exception
    {
        for (boolean comp : new boolean[]{ false, true })
            for (int m : new int[]{ 1, 4, 16, 0, UNSET })
                run("sorted", m, true, comp, 60_000, 1);
        run("bigpart", 1, true, false, 3_000, 5_000);
        run("unsorted", 4, false, false, 60_000, 1);
    }

    void run(String label, int m, boolean sorted, boolean comp, int partitions, int rowsInFirst) throws Exception
    {
        String ks = "probe_ks" + (++seq);
        File dir = new File(BASE + "/" + ks + "/t");
        dir.tryCreateDirectories();
        String schema = "CREATE TABLE " + ks + ".t (k int, c int, v blob, PRIMARY KEY (k, c))"
                        + (comp ? "" : " WITH compression = {'enabled': 'false'}");
        CQLSSTableWriter.Builder b = CQLSSTableWriter.builder().inDirectory(dir).forTable(schema)
                .using("INSERT INTO " + ks + ".t (k, c, v) VALUES (?, ?, ?)")
                .withPartitioner(ByteOrderedPartitioner.instance);
        if (sorted) b.sorted();
        if (m != UNSET) b.withMaxSSTableSizeInMiB(m);
        CQLSSTableWriter w = b.build();

        Field fSimple = CQLSSTableWriter.class.getDeclaredField("writer"); fSimple.setAccessible(true);
        Object simple = fSimple.get(w);
        long limit = -2; Field fTxn = null;
        if (simple instanceof SSTableSimpleWriter)
        {
            Field fl = SSTableSimpleWriter.class.getDeclaredField("maxSSTableSizeInBytes"); fl.setAccessible(true);
            limit = fl.getLong(simple);
            fTxn = SSTableSimpleWriter.class.getDeclaredField("writer"); fTxn.setAccessible(true);
        }
        List<Long> operandAtSwitch = new ArrayList<>();
        Object cur = null; long curVal = -1;
        Random rnd = new Random(42);
        for (int k = 0; k < partitions; k++)
            for (int c = 0; c < (k == 0 ? rowsInFirst : 1); c++)
            {
                byte[] v = new byte[1000]; rnd.nextBytes(v);
                w.addRow(k, c, ByteBuffer.wrap(v));
                if (fTxn != null)
                {
                    SSTableTxnWriter t = (SSTableTxnWriter) fTxn.get(simple);
                    if (t != null)
                    {
                        if (t != cur) { if (cur != null) operandAtSwitch.add(curVal); cur = t; }
                        curVal = t.getOnDiskBytesWritten();
                    }
                }
            }
        w.close();

        // group component files by generation id (file name "<ver>-<gen>-<fmt>-<Component>.db")
        TreeMap<Long, long[]> byGen = new TreeMap<>();
        for (File f : dir.tryList())
        {
            String[] p = f.name().split("-");
            if (p.length < 4) continue;
            long gen; try { gen = Long.parseLong(p[1]); } catch (NumberFormatException e) { continue; }
            long[] s = byGen.computeIfAbsent(gen, g -> new long[2]);
            if (f.name().endsWith("-Data.db")) s[0] = f.length();
            s[1] += f.length();
        }
        try (PrintWriter out = new PrintWriter(new FileWriter(OUT, true)))
        {
            int i = 0;
            for (long[] s : byGen.values())
            {
                String op = i < operandAtSwitch.size() ? String.valueOf(operandAtSwitch.get(i)) : "";
                out.println(String.join(",", label, String.valueOf(m), String.valueOf(comp), String.valueOf(limit),
                                        String.valueOf(i), String.valueOf(s[0]), String.valueOf(s[1]), op));
                i++;
            }
        }
        dir.deleteRecursive();
    }
}
```
(`File#tryList`, `#deleteRecursive`, `#name`, `#length` are at `io/util/File.java:514`, `:223`, `:463`, `:267`. `UNSET` is printed as `-2147483648`.)

**B2f. Predictions** (stated before any run; `L = M × 1,048,576`, `P` ≈ 1.02–1.03 KB measured as sum/partitions, `T` = run's total `Data.db`, ≈ 61.5 MB).
- `limitBytes` column: 1,048,576 / 4,194,304 / 16,777,216 for M = 1/4/16; `-1048576` for M = 0 or unset (the builder rewrites ≤ 0 to −1, ×1 MiB).
- **Uncompressed, M = 1, 4, 16:** SSTable count = `floor(T / L') + 1` where `L'` is the mean non-last `Data.db` (≈ 59, 15, 4). Every non-last SSTable: `L < Data.db ≤ L + P` (i.e. ≤ 1,049,600 B for M = 1 with P ≈ 1.03 KB), and `operandAtSwitch == Data.db`. The last SSTable ≤ `L + P`.
- **LZ4, M = 1, 4, 16:** same counts ±1; non-last `L < Data.db ≤ L + P + 16,388 B` (incompressible data: chunks stored at ≈ 16,384 B + 4 B CRC); `operandAtSwitch > L` and `Data.db − operandAtSwitch ≤ 16,388 B`.
- **M = 0 or unset:** exactly 1 SSTable, `Data.db ≈ T` (≈ 61.5 MB), no `operandAtSwitch` value.
- **bigpart, M = 1:** first SSTable `Data.db ≈ 5.1 MB` (> 4.8 × L, overshoot by the whole partition), `operandAtSwitch` ≈ 5.1 MB; following SSTables in `(L, L + P]`; total ≈ 8.1 MB ⇒ ≈ 4 SSTables.
- Components beyond `Data.db` add a few % (BIG `Index.db` ≈ 10–15 B per partition, filter, statistics): `allComponentsBytes` exceeds `L` by roughly 1–3 % for non-last SSTables; not capped.
- Claim wrong if: any non-last `Data.db` > `L + P` (+16,388 B compressed), any non-last `Data.db ≤ L`, or the count for M = 1 is not ≈ 4× the count for M = 4 (within ±2).

> **Amendment S2 (2026-11-24, before any reading), applied to the LZ4 bullet and the "claim wrong if" bullet above:** for LZ4 read `L < Data.db ≤ L + 2·Cmax = L + 32,944 B`, `L < operandAtSwitch ≤ L + Cmax = L + 16,472 B`, and `0 ≤ Data.db − operandAtSwitch ≤ Cmax = 16,472 B` (derivation in the note under B1). The filed bound `L + P + 16,388` is still computed and reported, as a secondary observation for stage 3; it does not decide a row.
>
> **Amendment S3 (2026-11-24, before any reading): reading rules for B2g.** Per run, `T` = sum of `Data.db`, `P` = `T / rows` (60,000; 64,999 for bigpart), `Pb = ceil(P) + 16 B` (row timestamps are delta-encoded as variable-length integers, so partitions differ by a few bytes). (a) "within (L, L+P]" is checked with `Pb`; uncompressed also requires `operandAtSwitch == Data.db` for every non-last SSTable. (b) "Counts ≈ 59 / 15 / 4" holds for a run when `|count − ceil(T/L)| ≤ max(1, 0.1·ceil(T/L))`, and across runs when `|c(M=1) − 4·c(M=4)| ≤ 2` and `|c(M=4) − 4·c(M=16)| ≤ 2`, for both compression settings. (c) Row 1 (Confirmed) needs (a), (b), `limitBytes` = M × 1,048,576 (−1,048,576 for 0/unset), exactly 1 SSTable for M = 0 and unset, the positive control passing, and `T` ≥ 40 MB in every sorted run. (d) The bigpart row holds when the first SSTable's `Data.db` > 4.5 MiB with `operandAtSwitch` equal to it, and the run has 3–5 SSTables. (e) The unsorted control holds when it gives ≥ 2 SSTables. (f) Readings that match no row, or a refuting row together with row 1, give "Not confirmed (no matching row)" unless a refuting row's condition is met, which then decides (Refuted).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Counts ≈ 59 / 15 / 4 for M = 1/4/16, 1 for M = 0/unset; non-last `Data.db` in `(L, L+P]` (uncompressed) / `(L, L+P+16,388]` (LZ4) | Claim confirmed: the limit caps per-SSTable data-file size as traced |
| Non-last `Data.db` exceeds the bound (e.g. 1.2 MiB at M = 1 with 1 KB partitions) | Claim wrong: overshoot larger than one partition/chunk; operand or check differs from the trace |
| Non-last `Data.db ≤ L` | Claim wrong: switch happens before the limit (another trigger) |
| Count does not change with M | Claim wrong: the value does not reach the check (e.g. builder ignores it for sorted) |
| `limitBytes` ≠ M × 1 MiB | Given line not executed as traced |
| M = 0 / unset yield > 1 SSTable | Disabled path differs from the trace |
| bigpart first SSTable ≈ 5.1 MB | Expected bypass confirmed (a partition is never split) |
| Positive control (`testWriteWithSortedAndMaxSize`) fails | Harness/build problem; results of this tier not usable |
| `T` far below 61.5 MB (e.g. < 40 MB) | Data compressed or not written; limit possibly not reached for M = 16; redo with larger N |

**B2h. Controls.**
- Positive control: upstream `testWriteWithSortedAndMaxSize` (cap known to bind at 1 MiB in upstream CI).
- Negative controls: M = 0 and unset (same data, no cap → 1 SSTable).
- Unsorted writer at M = 4: a different, buffer-based enforcement; expected multiple SSTables of roughly 4 MiB (not bounded by the trace above), shows the workload can move SSTable count through a separate known mechanism.
- Fixed RNG seed and incompressible values so `T` is the same for every M; uncompressed vs LZ4 isolates the operand definition.
- Each run in a fresh keyspace and directory, so no files of a previous run are counted.

### B3. Cluster tier

The constraint lives in a client-side offline writer; no node code reads it. The cluster tier therefore uses the documented real path: a standalone client program builds SSTables with `CQLSSTableWriter`, and a real single node ingests them with `nodetool import`. The actual resource measured is disk: per-SSTable file sizes on the generator's output directory and in the node's data directory after import.

**B3a. Environment and build.**
- One Linux node, JDK 11, Ant; built copy from B2a (`$S4/cassandra-5.0.9`, `ant jar` done). ≥ 3 GB free on the local disk under `$S4`.
- Node config (`$S4/cassandra-5.0.9/conf/cassandra.yaml`, edit in the copy): `data_file_directories: [$S4/node/data]`, `commitlog_directory: $S4/node/commitlog`, `saved_caches_directory: $S4/node/saved_caches`, `hints_directory: $S4/node/hints`, `cdc_raw_directory: $S4/node/cdc`; `listen_address`/`rpc_address: 127.0.0.1`; seeds `127.0.0.1:7000`; default `partitioner: org.apache.cassandra.dht.Murmur3Partitioner`. `conf/jvm-server.options`/`jvm11-server.options` unchanged; `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` exported. If ports 7000/9042/7199 are used by another user on the node, change `storage_port`, `native_transport_port` and `JMX_PORT` in `conf/cassandra-env.sh` and pass `-p <JMX_PORT>` to nodetool.
> **Amendment S4 (stage-4 audit, 2026-11-24).** `S4` as in S1, with a second `cp -a` of the base to `$S4/cluster/cassandra-5.0.9`, so the unit tier's test files are not in the node's tree; `$S4/cassandra-5.0.9` below means that copy, and `$S4/node`, `$S4/gen` mean `$S4/cluster/node`, `$S4/cluster/gen`. In a source build the dependency jars are in `build/lib/jars/`; `lib/` holds only the driver zip. The generator's `javac` and `java` classpaths therefore read `build/lib/jars/*` where the text below says `lib/*`. Before `bin/cassandra`: `ulimit -n 100000` (the node's soft limit is 1024). "Up" = `nodetool status` shows `UN 127.0.0.1` **and** `nodetool statusbinary` prints `running`. The yaml is edited by the harness script (`cluster-run.sh`) in that copy. Process checks use `ps -eo cmd | grep '[C]assandraDaemon'` (and `[G]enSorted`), per the stage-4 safety rules.
>
> **Amendment S7 (stage-4 runbook defect D1, 2026-11-25; claim, prediction and reading rules unchanged; the cluster tier restarted from its beginning).** B3e step 6 could not run as written: `nodetool import` printed nothing and returned 0, but every table kept 0 SSTables ("No new SSTables were found", `system.log`). Cause (Byteman trace on the node): `CQLSSTableWriter` runs in client mode, where `DatabaseDescriptor.applyCompatibilityMode()` forces `storage_compatibility_mode` to `NONE` (`DatabaseDescriptor.java:1602-1609`), so it writes the 5.0 BIG version `oa` (`BigFormat.java:343`); the node, started with the shipped `storage_compatibility_mode: CASSANDRA_4` (`conf/cassandra.yaml:2320`), has current version `nb`, so `Descriptor.validateAndExtractInfo` rejects every `oa` file as "incompatible sstable version (oa)" (`BigFormat.java:516-519`, `Descriptor.java:405-407`), and `SSTableLister` drops the rejected files without a log line (`Directories.java:1128-1130`, `SSTable.java:248-257`). **Fix:** in B3a's yaml edit also set `storage_compatibility_mode: NONE` on the fresh node (the documented "start with all the new features and formats enabled" mode); after step 6, stop if any table's `nodetool tablestats` "SSTable count" is 0. The node's mode does not touch the constraint, which lives in the client-side writer; generator-side readings still decide the claim (B3g row 4).

- Generator program `$S4/gen/GenSorted.java` (outside the source tree), compiled with `javac -cp "$S4/cassandra-5.0.9/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$S4/cassandra-5.0.9/lib/*" -d $S4/gen $S4/gen/GenSorted.java`; run with `java $(grep -v '^#' $S4/cassandra-5.0.9/conf/jvm11-clients.options | xargs) -Xmx1G -cp "$S4/gen:$S4/cassandra-5.0.9/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$S4/cassandra-5.0.9/lib/*:$S4/cassandra-5.0.9/conf" GenSorted <outDir> <table> <M|unset> <sorted|unsorted> <partitions>`.

```java
import java.nio.ByteBuffer;
import java.util.*;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.io.sstable.CQLSSTableWriter;
import org.apache.cassandra.utils.ByteBufferUtil;

public class GenSorted
{
    public static void main(String[] a) throws Exception
    {
        String out = a[0], table = a[1]; boolean sorted = a[3].equals("sorted"); int n = Integer.parseInt(a[4]);
        new java.io.File(out).mkdirs();
        CQLSSTableWriter.Builder b = CQLSSTableWriter.builder().inDirectory(out)
            .forTable("CREATE TABLE s4ks." + table + " (k int PRIMARY KEY, v blob) WITH compression = {'enabled': 'false'}")
            .using("INSERT INTO s4ks." + table + " (k, v) VALUES (?, ?)");
        if (sorted) b.sorted();
        if (!a[2].equals("unset")) b.withMaxSSTableSizeInMiB(Integer.parseInt(a[2]));
        CQLSSTableWriter w = b.build();
        Integer[] keys = new Integer[n];
        for (int i = 0; i < n; i++) keys[i] = i;
        // Murmur3 order: token, then key bytes (DecoratedKey order)
        Arrays.sort(keys, Comparator.comparingLong((Integer k) -> (Long) Murmur3Partitioner.instance.getToken(ByteBufferUtil.bytes(k)).getTokenValue())
                                    .thenComparing(k -> ByteBufferUtil.bytes(k)));
        Random rnd = new Random(42);
        for (Integer k : keys) { byte[] v = new byte[1000]; rnd.nextBytes(v); w.addRow(k, ByteBuffer.wrap(v)); }
        w.close();
        System.exit(0);
    }
}
```

**B3b. Knobs.** `M ∈ {1, 4, 16, unset}` with the sorted writer, uncompressed table (so `Data.db` = operand exactly), one table per value: `t_m1`, `t_m4`, `t_m16`, `t_unset`; control `t_ctl` = unsorted writer, M = 4. Set by the program argument (only way to set it).

**B3c. Workload.** 60,000 partitions × 1,000 random bytes ⇒ ≈ 61.5 MB `Data.db` per table (58.7 MiB = 58.7 × the M = 1 limit, 3.7 × the M = 16 limit). Five tables ⇒ ≈ 310 MB generated + ≈ 310 MB copied into the node (`--copy-data`) ⇒ < 1 GB. Generation ≈ 1 min per table; import seconds.

**B3d. Observables and instruments.**
- Generator side: `ls -l --block-size=1 <outDir>/*-Data.db` and all components (`stat -c '%s %n'`), per SSTable; `du -sb <outDir>`.
- Node side after import: `ls -l` of `$S4/node/data/s4ks/<table>-*/` (`*-Data.db` sizes), `nodetool tablestats s4ks.<table>` ("SSTable count", "Space used (live)"). Row count check: `cqlsh -e "SELECT count(*) FROM s4ks.<table>"` (≈ 60,000; use `CONSISTENCY ONE`, timeout raised with `--request-timeout=120`).
- Sampled once after each generation and once after each import (sizes are static, autocompaction disabled).
- Not observable on the node: the operand itself (B2 covers it); node RSS/heap are not affected by this constraint and are not measured.

**B3e. Procedure.**
1. `mkdir -p $S4/node/{data,commitlog,saved_caches,hints,cdc} $S4/gen/out`; edit yaml as in B3a.
2. Start node: `cd $S4/cassandra-5.0.9 && bin/cassandra -p $S4/node/cassandra.pid > $S4/node/stdout.log 2>&1`; wait until `bin/nodetool status` shows `UN 127.0.0.1`.
3. Schema: `bin/cqlsh 127.0.0.1 -e "CREATE KEYSPACE s4ks WITH replication = {'class':'SimpleStrategy','replication_factor':1};"` then for each `T` in `t_m1 t_m4 t_m16 t_unset t_ctl`: `bin/cqlsh 127.0.0.1 -e "CREATE TABLE s4ks.$T (k int PRIMARY KEY, v blob) WITH compression = {'enabled':'false'}; "` and `bin/nodetool disableautocompaction s4ks $T`.
4. Generate (each in its own `ks/table` directory): `GenSorted $S4/gen/out/t_m1/s4ks/t_m1 t_m1 1 sorted 60000`; same for `t_m4 4`, `t_m16 16`, `t_unset unset`; control `GenSorted $S4/gen/out/t_ctl/s4ks/t_ctl t_ctl 4 unsorted 60000`.
5. Record generator-side sizes: `for d in $S4/gen/out/*/s4ks/*; do echo $d; stat -c '%s %n' $d/*-Data.db; du -sb $d; done | tee $S4/gen/sizes-gen.txt`.
6. Import: `bin/nodetool import --copy-data s4ks $T $S4/gen/out/$T/s4ks/$T` for each `T`.
7. Record node-side sizes: `for T in ...; do bin/nodetool tablestats s4ks.$T | egrep 'SSTable count|Space used \(live\)'; stat -c '%s %n' $S4/node/data/s4ks/$T-*/*-Data.db; done | tee $S4/gen/sizes-node.txt`; row counts via cqlsh.
8. Stop: `kill $(cat $S4/node/cassandra.pid)`; wait for exit; `pgrep -u $USER -f CassandraDaemon` must print nothing; `pgrep -u $USER -f GenSorted` nothing.
9. Cleanup per B4.

**B3f. Predictions** (`L = M MiB`, `P` ≈ 1.02 KB, `T` ≈ 61.5 MB per table).
- `t_m1`: ≈ 59 SSTables; each non-last `Data.db` ∈ (1,048,576, 1,049,600] B. `t_m4`: ≈ 15, each ∈ (4,194,304, 4,195,330]. `t_m16`: 4, each ∈ (16,777,216, 16,778,240] (last ≈ 61.5 MB − 3 × 16.78 MB ≈ 11.2 MB). `t_unset`: 1 SSTable, `Data.db` ≈ 61.5 MB.
- Node side after import: identical SSTable count and identical `Data.db` sizes (import copies/renames files, no rewrite; autocompaction disabled); `Space used (live)` ≈ generator `du -sb` (same within the size of TOC/Digest files).
- `t_ctl` (unsorted, M = 4): several SSTables (≈ 13–20) of roughly 3–5 MB each; no (L, L+P] bound predicted.
- Row count 60,000 in every table.
- Claim wrong if a non-last `Data.db` in `t_m1`/`t_m4`/`t_m16` lies outside its interval, if the counts do not scale ≈ 1/M, or if `t_unset` has more than one SSTable.

> **Amendment S5 (2026-11-24, before any reading): reading rules for B3g.** "Within (L, L+P]" and "counts ≈ 59/15/4" are read with S3 (a) and (b) on the generator-side `Data.db` sizes (P = T/60,000 per table; no operand on this tier; "non-last" = all but the largest generation id). "Identical on node after import" = the same sorted list of `Data.db` sizes and the same SSTable count in `nodetool tablestats`. "Row counts" must be exactly 60,000. `t_ctl` "splits" = ≥ 2 SSTables. Readings that match no row give "Not confirmed (no matching row)".

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Counts ≈ 59/15/4/1 and non-last `Data.db` within (L, L+P], same on node after import | Claim confirmed: the constraint caps each SSTable's data file on disk as loaded into a node |
| Any non-last `Data.db` > L + P | Claim wrong (overshoot beyond one partition) |
| Count independent of M | Claim wrong (value not effective) |
| Node-side sizes differ from generator-side | Import rewrote files (or compaction ran): the node, not the constraint, decides final sizes; generator-side readings still decide the claim |
| `t_unset` 1 SSTable ≈ 61.5 MB while `t_m*` split | Negative control as expected; difference attributable to M |
| `t_ctl` splits into several files | Positive control: the workload is large enough to trigger a known split mechanism |
| Row counts ≠ 60,000 | Data loss or import failure; readings not usable |

**B3h. Controls.** `t_unset` (same data, no cap); `t_ctl` (separate known split mechanism, the unsorted writer buffer, documented default 128 MiB); autocompaction disabled before import so the node does not merge files; fixed RNG seed and uncompressed table so `T` is identical across tables; row-count check that every partition landed.

**B4. Risks and cleanup.**
- Disk: unit tier ≤ ≈ 70 MB at a time (each run deleted after measuring) plus build ≈ 1–2 GB; cluster tier < 1 GB under `$S4`. All on local disk under `$S4`, never in the shared source tree or shared storage.
- Processes: the JUnit fork ends with `ant`; the node is stopped with `kill $(cat $S4/node/cassandra.pid)`; verify `pgrep -u $USER -f 'CassandraDaemon|GenSorted|junit'` is empty.
- Ports: single node on 127.0.0.1; change ports if another user's node is running.
- Cleanup: `rm -rf $S4/node $S4/gen $S4/probe-unit $S4/probe-unit.csv` after copying the CSV/size files to the results location; keep or remove `$S4/cassandra-5.0.9` as the stage-4 environment dictates.

## C. Sources read

- src/java/org/apache/cassandra/io/sstable/SSTableSimpleWriter.java
- src/java/org/apache/cassandra/io/sstable/AbstractSSTableSimpleWriter.java
- src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java
- src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java (lines 60-160, via grep)
- src/java/org/apache/cassandra/io/sstable/SSTableTxnWriter.java
- src/java/org/apache/cassandra/io/sstable/SimpleSSTableMultiWriter.java
- src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java
- src/java/org/apache/cassandra/io/sstable/format/SSTableWriter.java
- src/java/org/apache/cassandra/io/sstable/format/DataComponent.java
- src/java/org/apache/cassandra/io/util/SequentialWriter.java
- src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java
- src/java/org/apache/cassandra/schema/CompressionParams.java
- src/java/org/apache/cassandra/config/Config.java (selected_format, uuid_sstable_identifiers_enabled)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (DETERMINISM_SSTABLE_COMPRESSION_DEFAULT)
- src/java/org/apache/cassandra/db/SSTableImporter.java
- src/java/org/apache/cassandra/tools/nodetool/Import.java
- src/java/org/apache/cassandra/db/compaction/writers/MaxSSTableSizeWriter.java (line 78, via grep)
- test/unit/org/apache/cassandra/io/sstable/CQLSSTableWriterTest.java
- test/unit/org/apache/cassandra/io/sstable/CQLSSTableWriterClientTest.java
- doc/modules/cassandra/pages/managing/operating/bulk_loading.adoc
- CHANGES.txt
- build.xml
- bin/cassandra.in.sh
- https://issues.apache.org/jira/browse/CASSANDRA-18941 (cited from CHANGES.txt; not fetched)

## D. Stage-4 feedback

none yet
