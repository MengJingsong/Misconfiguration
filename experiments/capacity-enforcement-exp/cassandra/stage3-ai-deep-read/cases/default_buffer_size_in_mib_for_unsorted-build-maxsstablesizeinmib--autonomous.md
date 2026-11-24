# DEFAULT_BUFFER_SIZE_IN_MIB_FOR_UNSORTED — verification solution  <!-- file: cases/default_buffer_size_in_mib_for_unsorted-build-maxsstablesizeinmib--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (capacity-set: the field `maxSSTableSizeInMiB` is set to its default), **linked**: [`CQLSSTableWriter.java:679`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java#L679) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-opus-5-5 (Claude Code CLI, autonomous stage-3 agent), 2026-11-24 |
| Estimate | `positive`. When the caller sets no positive size, line 679 sets the unsorted writer's buffer cap to 128 MiB. `SSTableSimpleUnsortedWriter` compares its running serialized-size total against that cap after every row and hands the full buffer to the disk thread through a zero-capacity queue, so the heap held for buffered rows is bounded by about 2 × 128 MiB (times the row shape's in-memory/serialized ratio), and each output SSTable holds about 128 MiB. On the sorted branch the same line sets -1 (no cap), but the sorted writer buffers only one partition. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `DEFAULT_BUFFER_SIZE_IN_MIB_FOR_UNSORTED`. Kind: **constant** (a hard-coded default), copied into the builder field `maxSSTableSizeInMiB` at the given line. The field itself is a per-writer **API option**.
- **Declaration:** [`CQLSSTableWriter.java:395`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java#L395) `private static final long DEFAULT_BUFFER_SIZE_IN_MIB_FOR_UNSORTED = 128L;`. The field is declared at `CQLSSTableWriter.java:407` (`private long maxSSTableSizeInMiB = -1L;`).
- **Unit:** MiB. Both writers convert it to bytes with `* 1024L * 1024L` (`SSTableSimpleUnsortedWriter.java:74`, `SSTableSimpleWriter.java:70`).
- **Default and how it is derived:** In `Builder.build()`, `isMaxSSTableSizeUnset()` (`CQLSSTableWriter.java:761-764`, `maxSSTableSizeInMiB <= 0`) is checked at `:677`. When it is true, line 679 sets `maxSSTableSizeInMiB = sorted ? -1L : DEFAULT_BUFFER_SIZE_IN_MIB_FOR_UNSORTED`. The effective defaults are therefore:
  - unsorted writer: **128 MiB = 134,217,728 bytes**;
  - sorted writer: **-1**, which means no limit (`SSTableSimpleWriter.java:105` only switches files when `maxSSTableSizeInBytes > 0`).
- **How it can be set:** Only through the Java builder API: `withMaxSSTableSizeInMiB(int)` (`:537-547`), `withBufferSizeInMiB(int)` (deprecated, `:563-567`) or `withBufferSizeInMB(int)` (deprecated, `:583-587`). There is no yaml key, `-D` property or JMX for it. It is fixed when the writer is built, so a change means building a new writer (a new client program run), not restarting a node.
- **Notable quirk:** `withMaxSSTableSizeInMiB` logs a warning for a non-positive value saying it "disables the size limiting effectively" (`:539-544`). For the **unsorted** writer that is not what happens: line 679 replaces any non-positive value with 128 MiB. Only the sorted writer is actually unlimited.

**A2. What it caps.**
- **Unsorted writer:** It caps **client JVM heap**, and through that the per-SSTable **disk** size. `SSTableSimpleUnsortedWriter` keeps every added row in an in-memory `TreeMap<DecoratedKey, PartitionUpdate.Builder>` (`Buffer`, `:204`) until the cap is crossed.
  - **Compared quantity:** `currentSize` (bytes), the running sum of the **serialized** sizes. It counts a header for each new partition (`:89`) and each row as it is added (`:103`).
  - **Comparison:** `currentSize > maxSStableSizeInBytes` (`:110`).
  - **What the cap means:** it is a *serialized-size* budget, not a measured heap size. The source says so itself (`:98-102`): "the bufferSize is first and foremost used to avoid OOM when using this writer".
- **Sorted writer:** With line 679's -1, nothing is capped. With a positive explicit value, the operand is `writer.getOnDiskBytesWritten()`, which caps per-SSTable disk size (`SSTableSimpleWriter.java:105`).

**A3. Mechanism.**
1. `build()` copies the effective value into the writer's constructor ([`CQLSSTableWriter.java:677-680`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java#L677-L680), then `:738-740`). The unsorted writer stores `maxSStableSizeInBytes = maxSSTableSizeInMiB * 1024 * 1024` (`SSTableSimpleUnsortedWriter.java:74`).
2. `CQLSSTableWriter.rawAddRow` calls `writer.getUpdateFor(key)` (`CQLSSTableWriter.java:265-300`).
   - For a key not yet in the buffer, `getUpdateFor` adds the serialized size of an empty `PartitionUpdate` to `currentSize`, then stores a new builder in `buffer` (`SSTableSimpleUnsortedWriter.java:81-94`).
3. Each `Row` added to that builder runs the overridden `add` (`:126-131`): `super.add(row)`, then `countRow(row)` (adds `UnfilteredSerializer.serializedSize`, `:103`), then `maybeSync()`.
4. **The check:** [`SSTableSimpleUnsortedWriter.java:110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java#L110) `if (currentSize > maxSStableSizeInBytes) sync();`.
   - **Limit crossed:** `sync()` (`:153-161`) calls `put(buffer)` and then starts a fresh `Buffer` with `currentSize = 0`. `put` offers the buffer to `writeQueue`, which is `newBlockingQueue(0)` (`:68`), i.e. a `SynchronousQueue` (`BlockingQueues.java:43-47`). The caller therefore **blocks** until the `DiskWriter` thread takes the buffer (`:163-178`). The `DiskWriter` writes the whole buffer as **one SSTable** (`:210-226`).
   - **Limit not crossed:** nothing happens and the row stays buffered.
   - **Live buffers:** at most two full buffers are live at a time: the one the `DiskWriter` is writing, and the one the caller is filling (the caller cannot hand over a second one until the first is taken).
5. **Overshoot and bypass paths:**
   - The check runs after the row is already in the buffer, so a buffer can exceed the cap by one row. A single row larger than the cap is always fully buffered.
   - The accounting is serialized size. The in-memory size of `PartitionUpdate.Builder` + `BTree` + `Row`/`Cell` objects is larger, and much larger for many small cells (`:98-102`). The user's `ByteBuffer` values are kept by reference, not copied (`TypeCodec.java:1161-1164`, `BlobCodec.serialize` returns `value.duplicate()`).
   - A non-positive explicit value becomes 128 MiB, not "unlimited" (A1).
   - `sorted()` takes the other branch (-1). No buffer is kept, and only the current partition is in memory (`SSTableSimpleWriter.java:74-91`).
   - `close()` performs a final `sync()` of whatever is left (`:136-151`).

**A4. Other consumers.** These are outside this constraint's control:
- the client program's own data and objects (rows it generates or reads before `addRow`);
- client-mode schema/initialization state (`CQLSSTableWriter.java:131-137` static init);
- the `SSTableTxnWriter` the `DiskWriter` uses: write buffers, the bloom filter, and the partition index and summary. Some of these are off-heap and scale with the number of partitions per SSTable, which is only indirectly bounded by this cap;
- SAI index building when `buildIndexes` and index statements are used (`:745-750`);
- opened `SSTableReader`s handed to the listener when `openSSTableOnProduced()` is set (the consumer must release them, `:624-637`, `:651-661`);
- total disk output, which this cap does not bound (it bounds per-file size only).

On a node, none of this is used: `CQLSSTableWriter` is an offline/client tool.

**A5. Evidence beyond the source.**
- Javadoc of `withBufferSizeInMB` (`CQLSSTableWriter.java:569-582`): "The default is 128MiB, which should be reasonable for a 1GiB heap. If you experience OOM while using the writer, you should lower this value."
- Javadoc of `withMaxSSTableSizeInMiB` (`:529-536`): "By default ... there is no maximum size limit" (true only for sorted).
- CHANGES.txt: "Support max SSTable size in sorted CQLSSTableWriter (CASSANDRA-18941)", which introduced the sorted/unsorted split of the default (https://issues.apache.org/jira/browse/CASSANDRA-18941), and CASSANDRA-17675 (renames/deprecations, NEWS.txt:570-573).
- Tests: `test/unit/org/apache/cassandra/io/sstable/CQLSSTableWriterTest.java` `testSyncWithinPartition` (≥2 SSTables with a 1 MiB buffer, CASSANDRA-7360) and `testWriteWithSortedAndMaxSize` (sorted, 1 MiB → 2 files). No test exercises the 128 MiB default itself.

## B. Verification solution

**B1. Claim under test.** For an unsorted `CQLSSTableWriter` built without a positive size (no call, or `withMaxSSTableSizeInMiB(0)`), the effective buffer cap is 128 MiB. The buffered serialized size never exceeds 134,217,728 bytes plus one row. The writer's peak live heap above baseline grows with the cap, not with the total data written (about 1×–2.3× the cap for large-value rows). Each produced SSTable's `Data.db` is about 128 MiB. The claim is wrong if the buffer grows past the cap, if peak heap follows the total data written instead of the cap, or if a non-positive value leaves the writer unlimited.

### B2. Unit tier

**B2a. Environment and build.**
- **Machine:** Linux, JDK 11 (`java -version` shows 11), Apache Ant ≥ 1.10, network access to Maven Central for the dependency fetch.
- **Paths:** `S4=/local/disk/dir/o115` is a local disk directory with **≥ 8 GiB free** (check with `df -h $S4`). Never use NFS or shared storage.
- **Build:**
  ```
  mkdir -p $S4 && rsync -a ~/cassandra-5.0.9/ $S4/src/ && cd $S4/src && ant jar
  ```
  This puts `build/classes/main` and the dependency jars in `build/lib/jars`.
- **Harness:** Save the harness below as `$S4/harness/org/apache/cassandra/io/sstable/BufferCapProbe.java`, outside the source tree. It is in the same package so it can name the package-private `SSTableSimpleUnsortedWriter`. It reads the private fields by reflection.

```java
package org.apache.cassandra.io.sstable;

import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.concurrent.ThreadLocalRandom;

import org.apache.cassandra.io.util.File;

// usage: BufferCapProbe <outDir> <mode> <rows> <valueBytes> <sampleCurrentSize> <gcEveryRows>
//   mode: default | explicit:<MiB> (calls withMaxSSTableSizeInMiB) | sorted
//   gcEveryRows: 0 = off; N = System.gc() then read heap used every N rows (live-heap sample)
public class BufferCapProbe
{
    public static void main(String[] args)
    {
        try { run(args); System.exit(0); }
        catch (Throwable t) { t.printStackTrace(); System.exit(1); }
    }

    static void run(String[] args) throws Exception
    {
        File dir = new File(args[0]);
        String mode = args[1];
        int rows = Integer.parseInt(args[2]);
        int valueBytes = Integer.parseInt(args[3]);
        boolean sample = Boolean.parseBoolean(args[4]);
        int gcEvery = Integer.parseInt(args[5]);
        if (!dir.exists() && !dir.tryCreateDirectories())
            throw new IllegalStateException("cannot create " + dir);

        CQLSSTableWriter.Builder b = CQLSSTableWriter.builder()
            .inDirectory(dir)
            .forTable("CREATE TABLE probe.t (k bigint PRIMARY KEY, v blob) WITH compression = {'enabled': 'false'}")
            .using("INSERT INTO probe.t (k, v) VALUES (?, ?)");
        if (mode.startsWith("explicit:"))
            b.withMaxSSTableSizeInMiB(Integer.parseInt(mode.substring("explicit:".length())));
        if (mode.equals("sorted"))
            b.sorted();
        CQLSSTableWriter w = b.build();

        Field wf = CQLSSTableWriter.class.getDeclaredField("writer");
        wf.setAccessible(true);
        Object sw = wf.get(w);
        boolean unsorted = sw instanceof SSTableSimpleUnsortedWriter;
        Field limitF = sw.getClass().getDeclaredField(unsorted ? "maxSStableSizeInBytes" : "maxSSTableSizeInBytes");
        limitF.setAccessible(true);
        long limit = limitF.getLong(sw);
        System.out.println("WRITER " + sw.getClass().getSimpleName() + " LIMIT_BYTES " + limit);
        Field curF = null;
        if (unsorted)
        {
            curF = SSTableSimpleUnsortedWriter.class.getDeclaredField("currentSize");
            curF.setAccessible(true);
        }

        System.gc();
        long h0 = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
        System.out.println("H0_BYTES " + h0);
        long peakLive = h0, prev = 0, maxObs = 0;
        int resets = 0;
        for (int i = 0; i < rows; i++)
        {
            byte[] v = new byte[valueBytes];                  // fresh array per row: values are kept by reference
            ThreadLocalRandom.current().nextBytes(v);         // incompressible
            w.addRow((long) i, ByteBuffer.wrap(v));
            if (sample && curF != null)
            {
                long cur = curF.getLong(sw);
                if (cur < prev)
                {
                    resets++;
                    System.out.println("RESET " + resets + " row " + i + " lastObserved " + prev);
                }
                maxObs = Math.max(maxObs, cur);
                prev = cur;
            }
            if (gcEvery > 0 && (i + 1) % gcEvery == 0)
            {
                System.gc();
                long live = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
                peakLive = Math.max(peakLive, live);
                System.out.println("LIVE row " + (i + 1) + " bytes " + live);
            }
        }
        w.close();
        System.out.println("SUMMARY limit=" + limit + " resets=" + resets + " maxObservedCurrentSize=" + maxObs
                           + " peakLive=" + peakLive + " h0=" + h0 + " rows=" + rows);
    }
}
```

- **Compile:**
  ```
  cd $S4/harness && javac -cp "$S4/src/build/classes/main:$S4/src/build/lib/jars/*:$S4/src/lib/*" -d classes org/apache/cassandra/io/sstable/BufferCapProbe.java
  ```
- **Run prefix (`RUN`):**
  ```
  java -Xmx1g -XX:+ExitOnOutOfMemoryError -Dlogback.configurationFile=$S4/src/conf/logback-tools.xml -cp "$S4/harness/classes:$S4/src/build/classes/main:$S4/src/build/lib/jars/*:$S4/src/lib/*" org.apache.cassandra.io.sstable.BufferCapProbe
  ```
  `CQLSSTableWriter`'s static block performs client initialization and selects Murmur3 (`CQLSSTableWriter.java:131-137`), so no yaml is needed.

**B2b. Knobs.** The builder call, with the same workload for each value:

| Run | Mode arg | Why |
|---|---|---|
| U1 | `default` (no size call) | Line 679's default branch. Expected limit 128 MiB. |
| U2 | `explicit:0` | Non-positive value. Line 679 overrides it to 128 MiB despite the warning. |
| U3 | `explicit:32` | Explicit cap, 4× smaller. Shows the operand follows the knob (positive control). |
| U4 | `explicit:2047` | Cap larger than the whole data set, so it never binds. "No-cap" reference. |
| U5 | `sorted` (rows = 0) | Line 679's other branch. Expected limit -1 MiB. Rows are not added because keys must arrive in token order. |

**B2c. Workload.**
- **Data:** 18,000 single-row partitions `(k bigint, v blob)`, each `v` a fresh 60,000-byte random array. That is 1.08 × 10⁹ bytes ≈ 1,030 MiB in total.
- **Per-row accounting:** about 60,000 + δ bytes, where δ (partition header + row/cell framing) is between 0 and 100 bytes.
- **Rows per sync with a 128 MiB cap:** `n = floor(134,217,728 / (60,000+δ)) + 1 ∈ [2,234, 2,237]`. So 18,000 rows give **8 syncs during writing** (8n ≤ 17,896 < 18,000 < 9n), plus a close-time sync of the remaining 104–128 rows. That is **9 SSTables**.
- **With a 32 MiB cap:** `n ∈ [559, 560]`, giving **32 syncs** (32 × 560 = 17,920 ≤ 18,000 < 33 × 559) plus the remaining 80–112 rows. That is **33 SSTables**.
- **With 2047 MiB:** no sync during writing and **1 SSTable** at close.

**B2d. Observables and instruments.**
- `LIMIT_BYTES`: the writer's private cap read by reflection right after `build()`. This is the direct result of line 679.
- `currentSize`: read after every `addRow` (18,000 samples). It is used for:
  - `maxObservedCurrentSize`;
  - each `RESET` line (the row index where `currentSize` dropped, and the last value observed before it);
  - the number of resets.
- `Data.db` count and sizes: `ls -l $OUT/*-Data.db`, with byte sizes from `stat -c %s`.
- The U2 warning line in stdout/stderr: `A non-positive value for maximum SSTable size is specified`.
- **Not directly observable:** the value of `currentSize` at the exact moment of the comparison on the triggering row, because `sync()` zeroes it inside the same call. It is bounded as "last observed + one row".

**B2e. Procedure.**
1. Build and compile as in B2a.
2. For each run `R` in U1–U4:
   ```
   OUT=$S4/out/unit-$R/probe/t; mkdir -p $OUT
   $RUN $OUT <mode> 18000 60000 true 0 | tee $S4/out/unit-$R.log
   ```
   Then:
   ```
   ls -l $OUT/*-Data.db | tee -a $S4/out/unit-$R.log
   stat -c '%s %n' $OUT/*-Data.db >> $S4/out/unit-$R.log
   ```
3. Run U5: `$RUN $S4/out/unit-U5/probe/t sorted 0 60000 true 0 | tee $S4/out/unit-U5.log`.
4. After recording each run, delete its data: `rm -rf $S4/out/unit-$R`. Keep the logs.
5. Check that nothing is left running: `pgrep -f BufferCapProbe` must print nothing.

**B2f. Predictions.**

| Run | `LIMIT_BYTES` | resets | `maxObservedCurrentSize` | `lastObserved` at each reset | `Data.db` files | Sizes |
|---|---|---|---|---|---|---|
| U1 default | 134,217,728 | 8 | ≤ 134,217,728 | ∈ [134,157,628, 134,217,728] (cap − one row … cap) | 9 | 8 files ≈ 128 MiB each (within ±2% of 134,217,728 B); 1 file ≈ 6–8 MB |
| U2 `explicit:0` | 134,217,728 (not ≤ 0) | 8 | as U1 | as U1 | 9 | as U1; plus the warning line |
| U3 `explicit:32` | 33,554,432 | 32 | ≤ 33,554,432 | ∈ [33,494,332, 33,554,432] | 33 | 32 files ≈ 32 MiB each (±2%); 1 file ≈ 5–7 MB |
| U4 `explicit:2047` | 2,146,435,072 | 0 | ≈ 1.08 × 10⁹ (the whole data set) | — | 1 | ≈ 1.08 × 10⁹ B |
| U5 sorted | −1,048,576 (−1 MiB) | — | — | — | 0 | — |

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| U1 `LIMIT_BYTES` = 134,217,728, 8 resets, `maxObservedCurrentSize` ≤ cap, 9 files of the predicted sizes | Claim supported at the operand level: line 679's default is applied and enforced. |
| U1 `LIMIT_BYTES` ≠ 134,217,728, or ≤ 0 | Claim wrong: the default at line 679 is not what reaches the writer. |
| U1 `maxObservedCurrentSize` > cap, or resets ≠ 8, or a single file much larger than 128 MiB | Claim wrong: the comparison does not bound the buffer as traced. |
| U2 `LIMIT_BYTES` ≤ 0 and 0 resets | Claim wrong for the non-positive case: the warning is accurate and the writer is unlimited. |
| U3 moves to 32 resets / 33 files while U1 stays at 8 / 9 | Positive control: the same workload moves the operand where a smaller cap binds. |
| U3 unchanged from U1 | Not confirmed: the knob is not reaching the writer, so the harness is suspect. |
| U4 shows 0 resets and a ~1 GiB operand | Reference: shows what the operand does with no binding cap, so U1's flat sawtooth is attributable to the cap. |
| U5 `LIMIT_BYTES` = −1,048,576 | The sorted branch of line 679 behaves as traced (no cap). |

**B2h. Controls.**
- **Same workload in every run.** The same row count, value size and schema are used throughout, with compression disabled in the schema, so `Data.db` size ≈ serialized size and is not shrunk by LZ4.
- **Fresh random arrays.** Each row gets a new array, which rules out shared-buffer effects.
- **Distinguishing U1 from U4.** U4 rules out "files are split for some other reason" (for example a format-level size limit).
- **Distinguishing the default from a typo.** U2 and U3 tell the default branch apart from a misnamed field. The reflection field names are checked by the `getDeclaredField` call, which throws if they are wrong.

**B2i. Audit amendments (stage 4, 2026-11-24, before the freeze; none changes B1).**
1. **Paths and build (B2a).** `S4=/mydata/jingsong-cass-s4/o115` on node `ms0604` (local `/mydata`). `$S4/src` is `cp -a /mydata/s4/cassandra-base`, a `copy-source.sh` copy of `cassandra-5.0.9` already built with `ant build-test` (it holds `build/classes/main` and `build/lib/jars`), so `ant jar` is not re-run. The harness is copied to `$S4/harness/` from `~/writeup-ext/out/o115/harness/` (outside the repo).
2. **Capture stderr and the exit code (B2e).** Each `$RUN … | tee` becomes `$RUN … 2>&1 | tee`: `conf/logback-tools.xml` sends WARN to `System.err`, so without it the U2 warning (B2d) would not reach the log. The exit code is read from `${PIPESTATUS[0]}`, not `$?`.
3. **U4 heap (B2a, B2e).** U4 runs with `-Xmx3g` instead of `-Xmx1g`. With a 2047 MiB cap the whole data set (1.08 × 10⁹ B, kept by reference, A3 step 5) is buffered, which does not fit a 1 GiB heap; at `-Xmx1g` U4 would end in `ExitOnOutOfMemoryError`, an outcome B2g has no row for. U1–U3 and U5 keep `-Xmx1g`.
4. **Small-file bands (B2f).** B2c gives 80–112 leftover rows for U3; at 60,000–60,100 B per row that is 4.80–6.73 MB, so U3's "≈ 5–7 MB" is read as **4.7–7.0 × 10⁶ B** (arithmetic slip: 80 rows give 4.8 MB). U1's "≈ 6–8 MB" is 6.0–8.0 × 10⁶ B (104–128 rows give 6.24–7.69 MB).
5. **Exact tolerances.** "≈ 1.08 × 10⁹" (U4 operand and file) is [1.07, 1.10] × 10⁹ B. "±2%" is of the cap in bytes (U1/U2: 131.53–136.90 × 10⁶ B; U3: 32.88–34.23 × 10⁶ B).
6. **Unit verdict rule.** The tier is **Confirmed (caps)** when U1 matches B2g row 1, U2 matches U1 (`LIMIT_BYTES` 134,217,728, 8 resets, 9 files) and logs the warning, U3 matches the positive-control row, and U4 matches the reference row, with no "Claim wrong" row firing. U5 is a side check of the sorted branch, which B1 does not rest on; a mismatch there is a flag only. A "Claim wrong" row for U1 → **Refuted (does not cap)**; B2g row 4 alone (U2 unlimited) → **Refuted for the non-positive path (caps only on some paths)**. U3 unchanged from U1 → **Not confirmed**. A reading that matches no row → **Not confirmed (no matching row)**.
7. **JDK 11 module options (B2a run prefix; runbook defect 1, 2026-11-24, found by the instrument check before run 1).** `$RUN` and every writer JVM of B3a also get the active lines of `$S4/src/conf/jvm11-clients.options` (`-Djdk.attach.allowAttachSelf=true` and its `--add-exports`/`--add-opens` lines), as Cassandra's own client scripts pass them. Without them the first `sync()` hands a buffer to the `DiskWriter`, whose `SSTableTxnWriter` fails in `FileUtils`' static init (`IllegalAccessException: … jdk.internal.ref.Cleaner.clean`), so no `Data.db` is written and the probe exits 1. The options change no code path of A3 and no prediction.

### B3. Cluster tier

No Cassandra node uses this constraint: `CQLSSTableWriter` runs in a client/bulk-load JVM. The "actual resource" is therefore measured in that **real writer process**, which is the production deployment shape (for example, a bulk-load job). A single local node is then used to ingest the output through the normal bulk-load client path (`sstableloader`), to show that the capped output is complete and to measure the node-side disk it produces.

**B3a. Environment and build.**
- **Build:** the same `$S4/src` build and harness as B2a.
- **Writer JVM:**
  ```
  java -Xmx<X> -XX:+UseG1GC -XX:+ExitOnOutOfMemoryError -Xlog:gc:file=$S4/out/gc-<run>.log -Dlogback.configurationFile=$S4/src/conf/logback-tools.xml -cp "<same classpath as B2a>" org.apache.cassandra.io.sstable.BufferCapProbe
  ```
  Do not set `-XX:+DisableExplicitGC`, because the harness's `System.gc()` must run as a full GC.
- **Node:** one node from `$S4/src`, run with its default directories. Those are under `$S4/src/data` (data, commitlog, hints, saved_caches), so everything is on local disk. Start it with `MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M`.
- **Ports:** before starting, `ss -ltn | grep -E ':(7000|7199|9042)\b'` must print nothing. If it prints something, another instance is using the ports: stop and pick another machine.

**B3b. Knobs.**
- **Writer cap B (MiB):**

  | Run | Mode arg | Role |
  |---|---|---|
  | C128 | `default` | Line 679's value |
  | C64 | `explicit:64` | Smaller explicit cap |
  | C32 | `explicit:32` | Smaller explicit cap |
  | C16 | `explicit:16` | Smaller explicit cap |
  | CX | `explicit:2047` | No binding cap |

- **Writer heap `-Xmx`:**
  - `2g` for all five live-heap runs (CX needs about 1.1 GiB live);
  - for the OOM sweep: C128 at `256m`, `384m`, `512m` and `768m`; C16 at `256m`; CX at `768m`.

**B3c. Workload.**
- **W1:** the same as B2c (18,000 rows × 60,000 B = 1,030 MiB), with live-heap sampling every 250 rows (`gcEveryRows=250`, about 15 MB of data between samples, 72 samples). With large values, the in-memory size of a buffered row ≈ its serialized size, so the cap translates almost 1:1 into heap per buffer. The total data (1,030 MiB) is about 8× the default cap, so an uncapped writer would need about 1 GiB of live heap and a capped one about 2 × 128 MiB.
- **W2 (optional, shows the cap is a serialized budget):** 2,500,000 rows × 100-byte values at B = 16 and B = 64, with `gcEveryRows=50000` and `-Xmx4g`.
  - That is about 2.5 × 10⁸ serialized bytes ≈ 240 MiB, so caps of 16 and 64 MiB are crossed repeatedly.
  - Here per-row object overhead (row, cell, BTree node, `DecoratedKey`, `ByteBuffer`) dominates, so heap per buffer is a multiple of B.
- **Duration:** a few minutes per W1 run (generating and writing 1 GB, plus 72 full GCs).

**B3d. Observables and instruments.**
- **Writer heap:**
  - `H0_BYTES` (live after `build()`);
  - the `LIVE` samples (heap used immediately after `System.gc()`, i.e. the live set including both buffers in flight);
  - `peakLive` from `SUMMARY`;
  - the G1 log `$S4/out/gc-<run>.log` (heap after each pause, as a cross-check).
- **OOM sweep:** the exit code (0 = completed; 3 = `ExitOnOutOfMemoryError`) and an `OutOfMemoryError` line in the output.
- **Writer disk:** the count and byte sizes of `Data.db`, and `du -sb $OUT` (the total of all components).
- **Node:**
  - `bin/nodetool tablestats probe.t` ("Space used (live)", "Number of partitions (estimate)");
  - `du -sb $S4/src/data/data/probe`;
  - `bin/cqlsh -e "SELECT count(*) FROM probe.t" --request-timeout=600`.
- **Not observable:**
  - the instantaneous heap between samples. Samples are every ~15 MB, so a peak can be missed by up to about 15 MB per buffer;
  - off-heap allocations of the `DiskWriter`'s SSTable writer. These are small here (18k partitions) and could be checked with `-XX:NativeMemoryTracking=summary` and `jcmd <pid> VM.native_memory summary` if needed.

**B3e. Procedure.**
1. Check `df -h $S4` (≥ 8 GiB free) and the port check from B3a.
2. **Live-heap runs.** For R in C16, C32, C64, C128, CX:
   ```
   OUT=$S4/out/$R/probe/t; mkdir -p $OUT
   java -Xmx2g ...(B3a)... $OUT <mode> 18000 60000 false 250 | tee $S4/out/$R.log
   stat -c '%s %n' $OUT/*-Data.db >> $S4/out/$R.log
   du -sb $OUT >> $S4/out/$R.log
   ```
   Keep `$S4/out/C128` for step 4. Delete each of the others after recording (`rm -rf $S4/out/$R`).
3. **OOM sweep (W1, `gcEveryRows=0`, `sampleCurrentSize=false`):**
   - C128 at `-Xmx256m`, `384m`, `512m` and `768m`;
   - C16 at `-Xmx256m`;
   - CX at `-Xmx768m`.

   Record each exit code (`echo $?`) and delete each output directory right after the run.
4. **Ingest into a node.**
   1. Start the node:
      ```
      cd $S4/src && MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M bin/cassandra -p $S4/node.pid > $S4/out/node-start.log 2>&1
      ```
   2. Wait until `bin/nodetool status` shows `UN` (poll every 5 s, for up to 3 min).
   3. Create the schema:
      ```
      bin/cqlsh -e "CREATE KEYSPACE probe WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE probe.t (k bigint PRIMARY KEY, v blob) WITH compression = {'enabled':'false'};"
      ```
   4. Load the C128 output and record the node-side counts:
      ```
      bin/sstableloader -d 127.0.0.1 $S4/out/C128/probe/t | tee $S4/out/load.log
      bin/nodetool tablestats probe.t | tee -a $S4/out/load.log
      du -sb $S4/src/data/data/probe >> $S4/out/load.log
      bin/cqlsh --request-timeout=600 -e "SELECT count(*) FROM probe.t" >> $S4/out/load.log
      ```
5. **Stop and clean up.**
   - `kill $(cat $S4/node.pid)`. Wait until `pgrep -f CassandraDaemon` prints nothing (after 60 s, use `kill -9`).
   - `pgrep -f BufferCapProbe` must print nothing.
   - `rm -rf $S4/out/C128 $S4/src/data`. Keep the `*.log` files.

**B3f. Predictions.** Let H0 be the printed `H0_BYTES`. The live-heap numbers below are in MiB.
- **Live-heap runs (W1, `-Xmx2g`):** `peakLive − H0` ≈ k·B with k ∈ [0.9, 2.3]. About 2 is expected, from two buffers in flight (A3 step 4).

  | Run | Predicted `peakLive − H0` |
  |---|---|
  | C16 | 14–37 MiB |
  | C32 | 29–74 MiB |
  | C64 | 58–147 MiB |
  | C128 | 115–295 MiB |
  | CX | 950–1,250 MiB, rising roughly linearly through the `LIVE` samples up to `close()` |

  For C16–C128 the `LIVE` samples form a sawtooth that does **not** trend upward with rows written. `peakLive(C128) − peakLive(C16)` lies in 100–260 MiB.
- **OOM sweep:**
  - C128 fails at `256m` (needs about H0 + 2 × 128 MiB) and completes at `512m` and `768m`. `384m` may go either way, depending on H0.
  - C16 completes at `256m`.
  - CX fails at `768m`.
- **Writer disk:**
  - C128: 9 `Data.db` (8 at ≈ 128 MiB ±2%, 1 small);
  - C64: 17 (16 at ≈ 64 MiB, 1 small);
  - C32: 33;
  - C16: 65 (n = 280 for any δ ∈ [0, 100], since ⌊16,777,216/(60,000+δ)⌋+1 = 280; 64 syncs cover 17,920 rows, and the remaining 80 rows give one more file);
  - CX: 1 file ≈ 1.08 × 10⁹ B.

  Total `du -sb` ≈ 1.08–1.12 × 10⁹ B for every run, so the cap bounds per-file size, not total disk.
- **Node:**
  - `count(*)` = 18,000;
  - the partition estimate is about 18,000;
  - "Space used (live)" ≈ 1.08–1.12 × 10⁹ B after loading, and ≤ about 2.3 × 10⁹ B transiently if STCS compacts the 9 inputs.
- **W2 (optional):** `(peakLive − H0)/B` is at least 2× the W1 ratio, but still flat in rows written. Heap follows B with a row-shape-dependent slope.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| C16–C128 peaks scale with B within the predicted bands, are flat in rows written, and CX rises to ≈ 1 GiB | Claim supported: the 128 MiB default (and the knob) governs writer heap. |
| C128 `peakLive − H0` ≥ 600 MiB, or its `LIVE` samples trend upward with rows like CX | Claim wrong: heap follows the total data written, not the cap. |
| All of C16–C128 within about 30 MiB of each other while CX rises | Claim wrong: the cap does not set heap usage (something else dominates). |
| CX does not rise, or C16 also needs > 256 MiB | Not confirmed: the workload is not holding data in heap as assumed (check fresh arrays, `System.gc` effective). |
| C128 OOM at 256m and success at 512m, while C16 succeeds at 256m and CX fails at 768m | Positive control plus claim supported: the same workload's heap need moves with the cap and is unbounded without it. |
| C128 succeeds at 256m | Claim weakened: the heap per buffer is smaller than traced, or only one buffer is live. Compare with the `LIVE` samples. |
| Any of the first 8 C128 `Data.db` files > 1.1 × 128 MiB | Claim wrong for the per-SSTable disk aspect. |
| Node `count(*)` ≠ 18,000 | The output is incomplete. Investigate before using any other reading. |

**B3h. Controls.**
- **Same workload.** All runs use identical data and differ only in B, so differences come from the cap alone. H0 is subtracted to remove client-initialization heap.
- **No-cap reference.** CX shows the heap the same workload uses when no cap binds. C16 shows that the measurement can detect a small footprint.
- **True live set.** Full-GC sampling measures the live set, not garbage awaiting collection. The G1 log is a cross-check.
- **Compression disabled.** This removes compression ratio as an explanation for file sizes.
- **Completeness check.** Node ingestion with `count(*)` rules out data being dropped to satisfy the cap.

**B3i. Audit amendments (stage 4, 2026-11-24, before the freeze; none changes B1).**
1. **Paths (B3a).** As B2i.1. The node runs from `$S4/src` with its default directories (`$S4/src/data`, `$S4/src/logs`); `ulimit -n 100000` before starting it (the node's soft limit is 1024).
2. **Capture (B3e).** As B2i.2: `2>&1 | tee`, and the OOM sweep's exit code is `${PIPESTATUS[0]}` (after `| tee`, `echo $?` gives tee's status).
3. **Exact tolerances (B3f, B3g).**
   - "Flat in rows written" (C16–C128): the mean of `LIVE − H0` over the last third of the samples minus the mean over the first third is ≤ max(0.5·B, 16 MiB). Above that bound is "trends upward" (B3g row 2).
   - CX "rising roughly linearly": the same difference is ≥ 400 MiB.
   - B3g row 3 "within about 30 MiB of each other": max − min of `peakLive − H0` over C16–C128 ≤ 30 MiB.
   - File-size "±2%" as B2i.5 (C64: 65.77–68.45 × 10⁶ B); partition estimate "about 18,000" = within ±10%.
4. **Cluster verdict rule.** The tier is **Confirmed (caps)** when B3g row 1 holds (each of C16–C128 in its B3f band and flat, `peakLive(C128) − peakLive(C16)` in 100–260 MiB, CX in 950–1,250 MiB and rising), row 5 holds (the OOM sweep; `384m` either way), the B3f file counts hold, node `count(*)` = 18,000, and no "Claim wrong" row (2, 3, 7) fires. A "Claim wrong" row → **Refuted (does not cap)**. Row 4 → **Not confirmed**. Row 1 holding but row 5 not (for example row 6) → **Not confirmed (partial)**, both recorded. Any other unmatched reading → **Not confirmed (no matching row)**. W2 is optional and supporting only; it does not enter the verdict.

**B4. Risks and cleanup.**
- **Disk:**
  - each W1 output is about 1.1 GB, and only one is kept at a time (C128, for loading);
  - the node takes about 1.1 GB, up to about 2.3 GB during compaction;
  - the build takes about 1.5 GB.

  All of this is under `$S4` on local disk (≥ 8 GiB free checked first). Nothing goes to shared storage or the shared source tree.
- **Memory:** writer runs use at most `-Xmx2g` (W2: `-Xmx4g`). Check `free -g` first, and do not run on a node with less than 8 GiB available.
- **Processes:** after each step:
  - `pgrep -f BufferCapProbe` and `pgrep -f CassandraDaemon` must both print nothing;
  - stop the node with `kill $(cat $S4/node.pid)` (`kill -9` after 60 s).
- **Cleanup at the end:** `rm -rf $S4/out/*/probe $S4/src/data $S4/src/logs`, and optionally `rm -rf $S4` once the logs are copied off.

## C. Sources read

- `src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java`: lines 80-140, 260-300, 395-425, 500-800
- `src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java`: whole file
- `src/java/org/apache/cassandra/io/sstable/SSTableSimpleWriter.java`: lines 40-160
- `src/java/org/apache/cassandra/io/sstable/AbstractSSTableSimpleWriter.java`: member declarations (grep)
- `src/java/org/apache/cassandra/utils/concurrent/BlockingQueues.java`: lines 37-47
- `src/java/org/apache/cassandra/cql3/functions/types/TypeCodec.java`: `BlobCodec` (lines 1135-1170)
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java`: `clientInitialization` (lines 250-330)
- `src/java/org/apache/cassandra/schema/CompressionParams.java`: defaults (grep)
- `test/unit/org/apache/cassandra/io/sstable/CQLSSTableWriterTest.java`: setup, `testSyncWithinPartition`, `testWriteWithSortedAndMaxSize`, `testNotifySSTableFinished`
- `test/unit/org/apache/cassandra/io/sstable/CQLSSTableWriterClientTest.java`
- `test/unit/org/apache/cassandra/io/sstable/CQLSSTableWriterDaemonTest.java`
- `build.xml`: the `testsome` target, memory properties, lib dirs (grep)
- `conf/cassandra.yaml`: directory keys and `default_compaction` (grep)
- `CHANGES.txt`, `NEWS.txt`: CQLSSTableWriter entries (grep)
- `tools/stress/src/org/apache/cassandra/io/sstable/StressCQLSSTableWriter.java`: grep only
- https://issues.apache.org/jira/browse/CASSANDRA-18941 (cited from CHANGES.txt, not fetched)
- https://issues.apache.org/jira/browse/CASSANDRA-17675 (cited from CHANGES.txt, not fetched)

## D. Stage-4 feedback

`none yet`
