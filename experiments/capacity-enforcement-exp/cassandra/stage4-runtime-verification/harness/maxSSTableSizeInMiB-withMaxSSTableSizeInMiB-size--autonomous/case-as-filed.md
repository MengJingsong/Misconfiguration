# maxSSTableSizeInMiB — verification solution  <!-- file: cases/maxSSTableSizeInMiB-withMaxSSTableSizeInMiB-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (capacity-set: the builder field is assigned), **linked**: [`CQLSSTableWriter.java:545`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java#L545), the statement `this.maxSSTableSizeInMiB = size;` in `CQLSSTableWriter.Builder.withMaxSSTableSizeInMiB(int size)` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `positive`, with a narrow scope. **Memory:** in the default unsorted mode, the value caps the writer's in-heap row buffer. The cap is checked against an approximate serialized size, so heap is a multiple of the value, up to about two buffers. **Disk:** in both modes, the value caps the size of each output `Data.db` file. **Not capped:** total disk. **Where it applies:** only in the offline/client `CQLSSTableWriter` library, not on a running Cassandra node. **Bypass:** partition-level deletes are not counted. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `maxSSTableSizeInMiB`, a field of the public `CQLSSTableWriter.Builder`. Three methods set it:
  - `withMaxSSTableSizeInMiB(int size)`;
  - the deprecated alias `withBufferSizeInMiB(int)` (`CQLSSTableWriter.java:563-567`);
  - the deprecated alias `withBufferSizeInMB(int)` (`CQLSSTableWriter.java:583-587`).
- **Kind:** a programmatic configuration value of a client library (a Java builder option). It is not a yaml key, a `-D` property or a JMX attribute, and it is not runtime-queried.
- **Declaration:** [`CQLSSTableWriter.java:407`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java#L407), `private long maxSSTableSizeInMiB = -1L;`. The default it falls back to is [`CQLSSTableWriter.java:395`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java#L395), `DEFAULT_BUFFER_SIZE_IN_MIB_FOR_UNSORTED = 128L`.
- **Unit:** MiB. The parameter is an `int`, widened to `long`. The writers convert it to bytes with `× 1024 × 1024` (`SSTableSimpleUnsortedWriter.java:74`, `SSTableSimpleWriter.java:70`).
- **Default and how it is derived:**
  - The field starts at `-1` (`:407`).
  - `withMaxSSTableSizeInMiB` stores any value. When `size <= 0` it only logs a warning (`:539-545`).
  - In `build()`, `isMaxSSTableSizeUnset()` (`:761-764`, `maxSSTableSizeInMiB <= 0`) replaces any non-positive value (`:676-680`):
    - sorted writer: `-1`, meaning no limit;
    - unsorted writer: **128 MiB**.
  - So for the unsorted writer a non-positive value does **not** "disable the size limiting", although the warning at `:541-543` says it does. The unsorted writer always has a limit of at least 1 MiB, and 128 MiB when the value is unset.
- **How it is set:**
  - It is set on the builder before `build()`, by the program that embeds `CQLSSTableWriter` (a bulk-load job or a test).
  - The value is copied into a `final` field of the writer at construction (`:738-740`). A new value therefore needs a new writer instance; no node restart is involved.

**A2. What it caps.**
- **Unsorted writer** (the default, when `sorted()` is not called):
  - **Resource:** the **heap** held by the in-memory row buffer `Buffer`, a `TreeMap<DecoratedKey, PartitionUpdate.Builder>` (`SSTableSimpleUnsortedWriter.java:60,204`). Through that buffer it also caps the **disk** size of each SSTable, because each flushed buffer becomes one SSTable.
  - **Compared quantity:** `currentSize`, the serialized size of each partition header (`:89`) plus each row (`:103`) added since the last flush. It is not the in-heap object footprint.
  - **Stated intent:**
    - The code comment at `:98-102` says the buffer size is "first and foremost used to avoid OOM".
    - The builder javadoc at `CQLSSTableWriter.java:549-558` says: "The default is 128MiB, which should be reasonable for a 1GiB heap. If you experience OOM while using the writer, you should lower this value."
- **Sorted writer** (`sorted()`):
  - **Resource:** the **disk** size of each output SSTable's data file. Heap does not depend on this value in this mode.
  - **Compared quantity:** `writer.getOnDiskBytesWritten()` of the current `SSTableTxnWriter` (`SSTableSimpleWriter.java:105`). The call chain is `SimpleSSTableMultiWriter.getOnDiskBytesWritten()` → `SSTableWriter.getEstimatedOnDiskBytesWritten()` → the data-file writer's position (`SimpleSSTableMultiWriter.java:78-81`, `SortedTableWriter.java:339-342`, `SequentialWriter.java:309-317`). For compressed tables the position is `chunkOffset` (`CompressedSequentialWriter.java:128-131`).
  - **Not counted:** only the Data component is counted. Index, Partitions/Rows, Filter, Statistics and SAI files are not.

**A3. Mechanism.**
1. **Set.** The caller sets the value at the given line, [`CQLSSTableWriter.java:545`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java#L545). A non-positive value is only logged (`:539-544`).
2. **Normalise and pass on.** `build()` normalises the value (`:677-680`) and passes it to the writer constructor (`:738-740`):
   - sorted: `new SSTableSimpleWriter(..., maxSSTableSizeInMiB)`;
   - unsorted: `new SSTableSimpleUnsortedWriter(..., maxSSTableSizeInMiB)`.
3. **Unsorted path.**
   - **How a row arrives.** `CQLSSTableWriter.rawAddRow` (`:265-317`) calls `writer.getUpdateFor(key)`, then `modificationStatement.addUpdateForKey(...)`. That reaches `UpdateStatement.java:94/103` or `DeleteStatement.java:79/101/109`, which call `updateBuilder.add(Row)`.
   - **Accounting for a new key.** `getUpdateFor` adds the serialized size of an empty `PartitionUpdate` (table id plus partition header) to `currentSize` (`SSTableSimpleUnsortedWriter.java:84-92`). It does not check the limit here.
   - **Accounting for a row.** The overridden `PartitionUpdate.Builder.add(Row)` (`:123-131`) adds the row, calls `countRow` (`:103`), then calls `maybeSync()`.
   - **The check:** [`SSTableSimpleUnsortedWriter.java:110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java#L110), `if (currentSize > maxSStableSizeInBytes) sync();`.
   - **When the limit is exceeded:**
     - `sync()` (`:153-161`) hands the full buffer to the `DiskWriter` thread through `writeQueue`, then starts a new empty buffer with `currentSize = 0`.
     - `writeQueue` is `newBlockingQueue(0)`, which is a `SynchronousQueue` (`BlockingQueues.java:43-47`). `put` (`:163-178`) therefore **blocks the producer** until the `DiskWriter` takes the buffer.
     - The `DiskWriter` (`:206-237`) writes each buffer, in sorted order, as one new SSTable.
   - **When it is not exceeded:** the row stays in the buffer.
   - **Peak heap:** at most one buffer being written, plus one full buffer the producer is offering, plus one row of overshoot. That is about 2 × L serialized bytes, times the in-memory overhead factor.
   - **Overshoot:** the check runs only after a whole row is added, so the buffer can exceed L by one row of any size. A single 500 MiB cell overshoots by 500 MiB.
   - **Bypass:**
     - Partition deletions (`DeleteStatement.java:72`, `addPartitionDeletion`) and range tombstones (`DeleteStatement.java:84,123`, `add(RangeTombstone)`) do not go through the overridden `add(Row)`. They never call `maybeSync()`, and their content is not counted.
     - Each new partition key still adds its header size to `currentSize` (`:89`). But nothing flushes the buffer until a row arrives or `close()` runs.
     - A delete-only workload therefore grows the buffer without limit.
4. **Sorted path.**
   - **How a partition is written.** `getUpdateFor` (`SSTableSimpleWriter.java:74-91`) keeps one partition in memory. On a new key it calls `writePartition(previous)`, which calls `getOrCreateWriter()` (`:112-121`).
   - **The check:** [`SSTableSimpleWriter.java:105`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableSimpleWriter.java#L105), `return writer == null || (maxSSTableSizeInBytes > 0 && writer.getOnDiskBytesWritten() > maxSSTableSizeInBytes);`.
   - **When the limit is exceeded:** the current SSTable is finished (`maybeCloseWriter`, `:138-154`) and a new one is opened before the partition is appended. Each finished data file is therefore larger than L by at most one partition. With compression on, add up to one compression chunk.
   - **When it is not exceeded:** the partition is appended to the current SSTable.
   - **Bypass:**
     - When L ≤ 0 the check is off (`maxSSTableSizeInBytes > 0`).
     - One very large partition overshoots by its full size.

**A4. Other consumers.**
- **Heap, unsorted mode.** These are not counted against L:
  - the in-memory footprint of buffered rows is larger than their serialized size. The extra comes from object headers, `BTreeRow`, `BufferCell`, `ByteBuffer`, `TreeMap` entries, `DecoratedKey` and the `PartitionUpdate.Builder` per partition. None of it is counted.
  - the throw-away `PartitionUpdate` built for each new key only to measure its size (`:87-89`).
  - the `PartitionUpdate` built for each partition while a buffer is written (`:223`).
  - the caller's own row objects.
  - client-mode schema and static state.
- **Heap, sorted mode.** One partition at a time, whatever L is.
- **Off-heap / native:**
  - `SequentialWriter` and compression buffers.
  - the SAI index build, when `withIndexes` is used (`CQLSSTableWriter.java:745-750`).
- **Disk.** These are not capped by L:
  - the total output size. It equals the data volume, whatever L is; L only splits it into more files.
  - the non-Data components and SAI files.
  - whatever the target cluster does after `sstableloader` or `nodetool import` (compaction, streaming).
- **Separate copy:** `tools/stress` has its own `StressCQLSSTableWriter.withBufferSizeInMiB` (`tools/stress/src/org/apache/cassandra/io/sstable/StressCQLSSTableWriter.java:522`). It is a separate field and is not covered here.

**A5. Evidence beyond the source.**
- **Change history:**
  - `CHANGES.txt:386`, "Support max SSTable size in sorted CQLSSTableWriter (CASSANDRA-18941)": https://issues.apache.org/jira/browse/CASSANDRA-18941
  - `CHANGES.txt:842`, CASSANDRA-17675 (the deprecated buffer-size aliases): https://issues.apache.org/jira/browse/CASSANDRA-17675
  - `CHANGES.txt:210`, CASSANDRA-19800 (the produced-SSTable listener): https://issues.apache.org/jira/browse/CASSANDRA-19800
- **Tests:**
  - `test/unit/org/apache/cassandra/io/sstable/CQLSSTableWriterTest.java:1273-1318`, `testWriteWithSortedAndMaxSize`: 1 MiB limit and 30,000 rows; it expects 2 data files, the larger within 50 KiB of 1 MiB.
  - `:1336-1380`, `testNotifySSTableFinished`: 1 MiB, sorted and unsorted.
  - No existing test checks heap.
- **Docs:** `doc/modules/cassandra/pages/managing/operating/bulk_loading.adoc:640-720` (CQLSSTableWriter usage, with a `withBufferSizeInMB(256)` example).
- **JDK** (https://docs.oracle.com/en/java/javase/11/docs/api/):
  - `java.util.concurrent.SynchronousQueue`: zero capacity; `offer(e, timeout)` succeeds only when a taker is waiting.
  - `java.lang.management.MemoryMXBean.getHeapMemoryUsage()`.

## B. Verification solution

**B1. Claim under test.**
- **Unsorted writer.** The value L set by `withMaxSSTableSizeInMiB(L)` keeps the buffered serialized size at or below L MiB before each flush. As a result:
  - the writer process's live heap rises with L, up to roughly one or two buffers of L times an overhead factor;
  - each output `Data.db` file is about L MiB;
  - total output does not depend on L.
- **Sorted writer.** Each finished `Data.db` is larger than L and at most L plus one partition. Heap does not depend on L.
- **The claim is wrong if:**
  - the operand exceeds L without a flush on an insert workload;
  - live heap does not rise with L;
  - file sizes do not track L.

### B2. Unit tier

Drive `CQLSSTableWriter` directly from a small JVM program. Read the check's own operand by reflection and count the flushes.

**B2a. Environment and build.**
- **Host:** one Linux host with JDK 11 (`java -version` shows 11) and Apache Ant 1.10 or later.
- **Work directory:** `WORK=/mydata/$USER-s4/cqlsstw`, or any directory on local disk with at least 6 GiB free (check with `df -h $WORK`). It must not be on shared or NFS storage.
- **Build.** Copy the tree first; never build in the shared tree:
  ```
  mkdir -p $WORK/probe $WORK/logs $WORK/out
  rsync -a ~/cassandra-5.0.9/ $WORK/src/
  cd $WORK/src && ant -q jar          # produces build/classes/main and fetches deps into build/lib/jars
  ```
- **Probe program.** Save the following as `$WORK/probe/MaxSizeProbe.java`. It is outside the tree, and both tiers use it:
  ```java
  import java.io.File;
  import java.lang.management.ManagementFactory;
  import java.lang.management.MemoryMXBean;
  import java.lang.reflect.Field;
  import java.lang.reflect.Method;
  import java.nio.ByteBuffer;
  import java.util.Random;

  import org.apache.cassandra.dht.ByteOrderedPartitioner;
  import org.apache.cassandra.dht.Murmur3Partitioner;
  import org.apache.cassandra.io.sstable.CQLSSTableWriter;

  // args: mode(unsorted|sorted) limit(unset|<int MiB>) rows valueBytes outDir sampleEvery(0=off) stmt(insert|delete) [partitioner bop|m3, default bop]
  public class MaxSizeProbe
  {
      public static void main(String[] a) throws Exception
      {
          String mode = a[0], limit = a[1];
          long rows = Long.parseLong(a[2]);
          int valueBytes = Integer.parseInt(a[3]);
          File out = new File(a[4], "probe/t");
          int every = Integer.parseInt(a[5]);
          boolean delete = a.length > 6 && a[6].equals("delete");
          boolean m3 = a.length > 7 && a[7].equals("m3");
          boolean sorted = mode.equals("sorted");
          if (!out.mkdirs() && !out.isDirectory()) throw new IllegalStateException("cannot create " + out);

          CQLSSTableWriter.Builder b = CQLSSTableWriter.builder()
              .inDirectory(out.getAbsolutePath())
              .forTable("CREATE TABLE probe.t (k bigint PRIMARY KEY, v blob) WITH compression = {'enabled':'false'}")
              .using(delete ? "DELETE FROM probe.t WHERE k = ?" : "INSERT INTO probe.t (k, v) VALUES (?, ?)")
              // ByteOrdered: bigint keys 0..N-1 are then already in partitioner order (needed by sorted())
              .withPartitioner(m3 ? Murmur3Partitioner.instance : ByteOrderedPartitioner.instance);
          if (sorted) b.sorted();
          if (!limit.equals("unset")) b.withMaxSSTableSizeInMiB(Integer.parseInt(limit));
          CQLSSTableWriter w = b.build();

          Field wf = CQLSSTableWriter.class.getDeclaredField("writer"); wf.setAccessible(true);
          Object inner = wf.get(w);
          Field limF = inner.getClass().getDeclaredField(sorted ? "maxSSTableSizeInBytes" : "maxSStableSizeInBytes");
          limF.setAccessible(true);
          Field curF = sorted ? null : inner.getClass().getDeclaredField("currentSize");
          Field txnF = sorted ? inner.getClass().getDeclaredField("writer") : null;
          if (curF != null) curF.setAccessible(true);
          if (txnF != null) txnF.setAccessible(true);
          System.out.println("WRITER " + inner.getClass().getSimpleName() + " EFFECTIVE_LIMIT_BYTES " + limF.getLong(inner));

          MemoryMXBean mem = ManagementFactory.getMemoryMXBean();
          Random rnd = new Random(42);
          long maxOp = 0, prev = 0, firstDelta = -1, syncs = 0, maxHeap = 0, minHeap = Long.MAX_VALUE;
          Object lastTxn = null; Method onDisk = null;
          long lastTxnBytes = 0, switches = 0, maxAtSwitch = 0, minAtSwitch = Long.MAX_VALUE;
          long t0 = System.nanoTime();
          for (long i = 0; i < rows; i++)
          {
              if (delete) w.addRow(i);
              else { byte[] v = new byte[valueBytes]; rnd.nextBytes(v); w.addRow(i, ByteBuffer.wrap(v)); }
              if (!sorted)
              {
                  long cur = curF.getLong(inner);          // the check's operand (bytes)
                  if (firstDelta < 0) firstDelta = cur;     // = s, serialized bytes of one 1-row partition
                  if (cur < prev) syncs++;                  // sync() resets currentSize to 0
                  maxOp = Math.max(maxOp, cur); prev = cur;
              }
              else
              {
                  Object txn = txnF.get(inner);
                  if (txn != null)
                  {
                      if (onDisk == null) onDisk = txn.getClass().getMethod("getOnDiskBytesWritten");
                      if (lastTxn != null && txn != lastTxn)
                      { switches++; maxAtSwitch = Math.max(maxAtSwitch, lastTxnBytes); minAtSwitch = Math.min(minAtSwitch, lastTxnBytes); }
                      lastTxn = txn; lastTxnBytes = (Long) onDisk.invoke(txn);
                      maxOp = Math.max(maxOp, lastTxnBytes);
                  }
              }
              if (every > 0 && (i + 1) % every == 0)
              {
                  System.gc();
                  long used = mem.getHeapMemoryUsage().getUsed();
                  maxHeap = Math.max(maxHeap, used); minHeap = Math.min(minHeap, used);
                  System.out.println("HEAP_SAMPLE row=" + (i + 1) + " live_bytes=" + used);
              }
          }
          w.close();
          System.out.println("SUMMARY mode=" + mode + " limit=" + limit + " rows=" + rows + " stmt=" + (delete ? "delete" : "insert")
                             + " first_row_delta=" + firstDelta + " max_operand=" + maxOp + " syncs=" + syncs
                             + " switches=" + switches + " min_at_switch=" + (switches > 0 ? minAtSwitch : -1)
                             + " max_at_switch=" + maxAtSwitch + " min_live_heap=" + (every > 0 ? minHeap : -1)
                             + " max_live_heap=" + (every > 0 ? maxHeap : -1)
                             + " elapsed_s=" + (System.nanoTime() - t0) / 1_000_000_000L);
          System.exit(0);   // client mode may leave non-daemon threads
      }
  }
  ```
- **Runner script.** Save as `$WORK/probe/run.sh` and make it executable with `chmod +x $WORK/probe/run.sh`.
  - Usage: `HEAPOPTS=... run.sh <tag> <probe args...>`.
  - It runs one probe, prints the summary, the data-file count, the sorted data-file sizes and the `du`, then deletes the output unless `KEEP=1` is set.
  ```bash
  #!/usr/bin/env bash
  set -u
  WORK=${WORK:?}; tag=$1; shift
  CP="$WORK/src/build/classes/main:$WORK/src/build/lib/jars/*:$WORK/src/conf"
  JOPTS="$(grep -v '^#' $WORK/src/conf/jvm11-clients.options | grep -v '^$' | tr '\n' ' ') -Dlogback.configurationFile=$WORK/src/conf/logback-tools.xml"
  OUT=$WORK/out/$tag; rm -rf "$OUT"; mkdir -p "$OUT"
  # probe args: mode limit rows valueBytes ; outDir is inserted here ; then sampleEvery stmt [partitioner]
  timeout 1800 java $JOPTS ${HEAPOPTS:-} -cp "$WORK/probe/classes:$CP" MaxSizeProbe "$1" "$2" "$3" "$4" "$OUT" "${@:5}" \
      > "$WORK/logs/$tag.log" 2>&1
  echo "exit=$?" | tee -a "$WORK/logs/$tag.log"
  grep -E '^(WRITER|SUMMARY)' "$WORK/logs/$tag.log"
  grep -m1 -E 'OutOfMemoryError' "$WORK/logs/$tag.log"
  echo "data_files=$(ls $OUT/probe/t/*-Data.db 2>/dev/null | wc -l)"
  echo "data_sizes=$(stat -c '%s' $OUT/probe/t/*-Data.db 2>/dev/null | sort -n | tr '\n' ' ')"
  echo "du_bytes=$(du -sb $OUT/probe/t 2>/dev/null | cut -f1)"
  [ "${KEEP:-0}" = 1 ] || rm -rf "$OUT"
  ```
- **Compile:**
  ```
  export WORK
  javac -cp "$WORK/src/build/classes/main:$WORK/src/build/lib/jars/*" -d $WORK/probe/classes $WORK/probe/MaxSizeProbe.java
  ```
- **Unit-tier JVM options:** `HEAPOPTS="-Xmx2g"`. Heap sampling is off (`sampleEvery=0`).

**B2b. Knobs.** The knob is the value passed to `withMaxSSTableSizeInMiB`, given as the probe's second argument.
- **Unsorted, insert:** L ∈ {1, 4, 16}. All three are well below the workload, so they give many, some and few flushes.
- **Default handling:** L ∈ {`unset`, `0`, `-1`} for both modes, with a workload above 128 MiB. This tests `:677-680` and the misleading warning.
- **Sorted, insert:** L ∈ {1, 4, 16}.
- **Bypass probe:** unsorted, delete-only, L = 1.

**B2c. Workload.**
- **Table and rows:**
  - The table is `probe.t (k bigint PRIMARY KEY, v blob)` with compression off, so the data-file position is exact (`SequentialWriter.java:309-317`).
  - Each row is a new partition with a 1,024-byte random blob (seed 42).
- **Row size s.** The probe prints it as `first_row_delta`. From the source, s should be about 1.05–1.15 KiB. It is made of:
  - a 16-byte table id (`PartitionUpdate.java:774`);
  - the partition header and the 8-byte key;
  - the row header;
  - a 2-byte length and 1,024 value bytes.
- **Main runs:** N = 65,536 rows, so the total T = N·s ≈ 67–74 MiB. That is 67–74 × L at L = 1, 17–18 × L at L = 4 and 4–5 × L at L = 16, so the limit is reached many times.
- **Default runs:** N = 196,608 rows, so T ≈ 202–221 MiB. That is more than 128 MiB, so a 128 MiB cap gives 2 files and no cap gives 1.
- **Bypass run:** N = 262,144 partition deletes. Each adds at least 16 bytes (the table id) to the operand, so the total is at least 4 MiB, which is more than L = 1 MiB.

**B2d. Observables and instruments.**
- **`EFFECTIVE_LIMIT_BYTES`:** the writer's `final` limit field, read by reflection.
- **`max_operand`:** the largest value of the operand seen after any `addRow`. The operand is `currentSize` for the unsorted writer and `getOnDiskBytesWritten()` for the sorted writer.
- **`syncs`:** the number of times `currentSize` reset to 0 (unsorted).
- **`switches` and `min_at_switch` / `max_at_switch`** (sorted): the old writer's data-file bytes at the moment it was replaced. This is exactly the operand the check compared.
- **`data_files` and `data_sizes`:** the count and sizes of the output data files (`*-Data.db`).
- **Not directly observable:**
  - In the unsorted writer, the operand at the instant of the `>` comparison. That value is `prev + rowSize`; the probe sees `prev` and the reset that follows.
  - Heap. B3 measures it.

**B2e. Procedure.**
```
export WORK HEAPOPTS="-Xmx2g"; R=$WORK/probe/run.sh
# 1. unsorted, insert
for L in 1 4 16; do $R u-ins-$L unsorted $L 65536 1024 0 insert; done
# 2. default handling (above 128 MiB of data)
for L in unset 0 -1; do $R u-def-$L unsorted $L 196608 1024 0 insert; done
for L in unset 0 -1; do $R s-def-$L sorted   $L 196608 1024 0 insert; done
# 3. sorted, insert
for L in 1 4 16; do $R s-ins-$L sorted $L 65536 1024 0 insert; done
# 4. bypass probe: delete-only (valueBytes ignored)
$R u-del-1 unsorted 1 262144 0 0 delete
# 5. nothing left running
pgrep -f MaxSizeProbe || echo "no probe left"
```
Record each run's `WRITER` and `SUMMARY` lines, `data_files` and `data_sizes`.

**B2f. Predictions.**
- **Notation:**
  - s = `first_row_delta`;
  - n(L) = ⌈N·s / (L·2^20)⌉;
  - s_disk = the on-disk size of one partition, close to s.
- **Main relation:** the data-file count scales as 1/L, and `max_operand` ≤ L in every insert run on the unsorted writer.

| Run | EFFECTIVE_LIMIT_BYTES | max_operand | syncs or switches | data_files | data_sizes |
|---|---|---|---|---|---|
| u-ins-1 | 1,048,576 | in (1,048,576 − s, 1,048,576] | syncs = n(1) − 1 ± 1 (≈ 66–73) | n(1) ± 1 | all but the last in [0.85, 1.15] MiB |
| u-ins-4 | 4,194,304 | in (4,194,304 − s, 4,194,304] | syncs = n(4) − 1 ± 1 (≈ 16–18) | n(4) ± 1 | all but the last in [3.4, 4.6] MiB |
| u-ins-16 | 16,777,216 | in (16,777,216 − s, 16,777,216] | syncs = n(16) − 1 ± 1 (≈ 4) | n(16) ± 1 (≈ 5) | all but the last in [13.6, 18.4] MiB |
| u-def-unset, u-def-0, u-def-−1 | **134,217,728** in all three | > 134,217,728 − s and ≤ 134,217,728 | syncs = 1 | **2** | the first in [109, 147] MiB |
| s-def-unset, s-def-0, s-def-−1 | −1,048,576 (no limit) | about the whole data file | switches = 0 | **1** | one file, about N·s_disk |
| s-ins-L (L = 1, 4, 16) | L·2^20 | ≤ L·2^20 + one partition | switches = data_files − 1 | ⌈N·s_disk / (L·2^20)⌉ ± 1 | all but the last in (L·2^20, L·2^20 + 2,048] bytes; `min_at_switch` > L·2^20 |
| u-del-1 | 1,048,576 | **≥ 4,194,304, above L** | **syncs = 0** | **1** | one file |

**B2g. Readings.**

| Observation | What it means |
|---|---|
| Insert runs: `max_operand` ≤ limit, syncs and file count scale as 1/L, file sizes ≈ L | The mechanism works as traced; the claim holds at the operand level |
| Insert runs: `max_operand` > limit plus one row, or syncs = 0 while T > L | The check does not bound the operand: **the claim is wrong** |
| The file count does not change with L, or the file sizes do not track L | The value does not govern the output: **the claim is wrong** |
| u-def runs: 1 file, or `EFFECTIVE_LIMIT_BYTES` ≤ 0 | The default handling differs from the trace of `:677-680`. The trace is wrong and the warning is right |
| u-def runs: 2 files and a limit of 134,217,728, including for `0` and `-1` | Confirms that a non-positive value does not disable the cap in the unsorted writer, so the warning at `:541-543` is misleading |
| s-ins runs: a file other than the last is ≤ L, or larger than L + 2 KiB | The sorted check does not switch files at the first partition past L: the trace is wrong |
| u-del-1: syncs = 0 and `max_operand` far above L | The bypass is confirmed: deletes are not counted and do not trigger a flush |
| u-del-1: syncs > 0 | The bypass is refuted: some other path calls `maybeSync` |
| A run with T > L where `max_operand` stays far below L | Not confirmed: check the workload size and `first_row_delta` |

**B2h. Controls.**
- **Only L changes.** The seed, N and the compression-off schema are the same for every knob value.
- **Internal check of the default.** In the default runs, `unset` must give 128 MiB.
- **Independent check of the sorted path.** The sorted runs use the same data and exercise the data-file check without the buffer.
- **The unchecked path is exercised.** The delete probe drives the one path the trace says is not checked.
- **Argument errors are visible.** `EFFECTIVE_LIMIT_BYTES` is printed, so a wrongly passed value shows.
- **No leftover files.** Every run starts with an empty, newly created output directory, because `getNextId` scans the directory (`AbstractSSTableSimpleWriter.java:134-151`).

### B3. Cluster tier

**n/a for a running node.**
- `CQLSSTableWriter` is an offline/client library: its static initializer calls `DatabaseDescriptor.clientInitialization(false)` (`CQLSSTableWriter.java:131-138`).
- The value can only be set on the builder. No Cassandra node reads it, and no node runs this code path.
- So the value cannot bound a node's heap or disk.

**Instead: a client-process tier.** It answers the same question on the real resource:
- The bulk-writing program runs as a real job in its own JVM with a fixed heap.
- It measures the **actual** live heap and the on-disk output.
- An optional step loads the output into one node to show the files are valid.

The subsections below describe this tier.

**B3a. Environment and build.**
- **Host, build, probe and runner:** the same as B2a.
- **JVM options:**
  - measurement runs: `-Xms2g -Xmx2g -XX:+UseG1GC -Xlog:gc*:file=$WORK/logs/<tag>-gc.log`;
  - heap-ceiling runs: `-Xmx320m -XX:+UseG1GC`.
- **Disk:** at least 2 GiB free on local disk, for one run's output (about 600 MiB) plus logs. The runner deletes each run's output.
- **Optional validity step:** one local node started from `$WORK/src`. It needs about 3 GiB of RAM free.

**B3b. Knobs.**
- **Unsorted:** L ∈ {16, 64, `unset` (= 128), 256}. These cover a 16× range and all stay below the workload of about 560 MiB.
- **Positive control:** unsorted with L = 1024, which is above the workload, so the buffer holds everything until `close()`.
- **Sorted contrast:** L ∈ {16, 256}.
- **Heap ceiling:** `-Xmx320m` with L ∈ {16, 256}.

**B3c. Workload.**
- **Size:** N = 524,288 rows of 1 KiB random blobs, one partition per row. T = N·s ≈ 540–590 MiB serialized, and about the same on disk (no compression).
- **Buffers per run:** T/L ≈ 35 at L = 16, 9 at L = 64, 4.5 at L = 128 and 2.2 at L = 256.
- **Heap sampling:** every 8,192 rows (about 8.5 MiB of input), so 64 samples per run.
- **Duration:** about 1–3 minutes per run, plus the time for about 64 forced GCs.

**B3d. Observables and instruments.**
- **Live heap:**
  - the `HEAP_SAMPLE` lines (`System.gc()`, then `MemoryMXBean.getHeapMemoryUsage().getUsed()`), and `max_live_heap` / `min_live_heap`;
  - cross-check: heap after each forced GC from the G1 log, `grep -E 'Pause Full' $WORK/logs/<tag>-gc.log`.
- **Disk:** the size of each data file and the total output size, `du_bytes`.
- **Pass or fail under `-Xmx320m`:** the exit code and any `OutOfMemoryError` in the log.
- **Not observable:**
  - the true instantaneous peak between samples. Samples are taken on the producer thread, and the `DiskWriter` may hold a second buffer at that moment.
  - how heap splits between the two buffers.

**B3e. Procedure.**
1. **Measurement runs:**
   ```
   export WORK; R=$WORK/probe/run.sh
   for L in 16 64 unset 256 1024; do
     HEAPOPTS="-Xms2g -Xmx2g -XX:+UseG1GC -Xlog:gc*:file=$WORK/logs/p-u-$L-gc.log" $R p-u-$L unsorted $L 524288 1024 8192 insert
   done
   for L in 16 256; do
     HEAPOPTS="-Xms2g -Xmx2g -XX:+UseG1GC -Xlog:gc*:file=$WORK/logs/p-s-$L-gc.log" $R p-s-$L sorted $L 524288 1024 8192 insert
   done
   ```
2. **Baseline and heap growth.** H0 is `min_live_heap` from the `p-u-16` run. For each run, P(L) = `max_live_heap` − H0.
3. **Heap-ceiling runs:**
   ```
   for L in 16 256; do HEAPOPTS="-Xmx320m -XX:+UseG1GC" $R p-oom-$L unsorted $L 524288 1024 0 insert; done
   ```
4. **Optional validity check:**
   1. Write the output with the node's default partitioner and keep it:
      ```
      KEEP=1 HEAPOPTS="-Xmx2g" $R p-m3 unsorted 16 524288 1024 0 insert m3
      ```
   2. In a copy of `$WORK/src/conf/cassandra.yaml`, set `data_file_directories`, `commitlog_directory`, `hints_directory` and `saved_caches_directory` under `$WORK/node`. Start the node with `CASSANDRA_CONF=<that conf> $WORK/src/bin/cassandra -p $WORK/node/pid`.
   3. Create the schema:
      ```
      bin/cqlsh -e "CREATE KEYSPACE probe WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE probe.t (k bigint PRIMARY KEY, v blob) WITH compression={'enabled':'false'};"
      ```
   4. Load the files: `bin/sstableloader -d 127.0.0.1 $WORK/out/p-m3/probe/t`.
   5. Count the rows: `bin/cqlsh --request-timeout=600 -e "SELECT count(*) FROM probe.t"`. Expect 524,288.
   6. Stop the node with `bin/nodetool stopdaemon`.
5. **Check and clean up.** `pgrep -f MaxSizeProbe` and `pgrep -f CassandraDaemon` must both print nothing. Then `rm -rf $WORK/out $WORK/node`.

**B3f. Predictions.**
- **Heap rises with L (unsorted):**
  - P(16) < P(64) < P(128) < P(256), with each step positive.
  - For L ≥ 64, P(L)/L (MiB of heap per MiB of L) is in [0.6, 4.0]. The upper end allows two buffers at an overhead factor of about 1.2–2 for 1 KiB values. The lower end allows for samples that miss the peak.
  - P(256) − P(64) ≥ 150 MiB.
  - P(16) ≤ 80 MiB.
- **Positive control (L = 1024, above T):**
  - the live samples rise roughly linearly with the rows written, ending at least 0.8·T ≈ 430 MiB above H0;
  - there is no flush before `close()`, and there is one data file.
- **Sorted contrast:**
  - |P_sorted(256) − P_sorted(16)| ≤ 32 MiB;
  - both are ≤ P(16) + 32 MiB.
- **Disk:**
  - unsorted data-file count ⌈T/L⌉ ± 1: about 35, 9, 5, 3 and 1 for L = 16, 64, 128, 256 and 1024;
  - unsorted data files other than the last are in [0.85, 1.15]·L;
  - sorted data files other than the last are in (L, L + 2 KiB];
  - `du_bytes` is the same for every L within 3%, so total disk is not capped.
- **Heap ceiling (`-Xmx320m`):**
  - L = 16 completes with exit 0.
  - L = 256 fails with an `OutOfMemoryError` or a nonzero exit. One full 256 MiB buffer at an overhead of at least 1.2 is at least 307 MiB; with H0 added, that is more than 320 MiB.

**B3g. Readings.**

| Observation | What it means |
|---|---|
| P rises with L within the stated ratio band, and the L = 1024 control rises with the rows written | Live heap follows the cap: **the claim holds** |
| P is flat across L (within 32 MiB) while the L = 1024 control rises | The buffer is not what drives heap: **the claim is wrong** for heap |
| P is flat and the control is flat too | The instrument cannot see buffer growth: **not confirmed** (check the sampling) |
| P(L)/L far above 4 for L ≥ 64 | Heap follows L, but the bound is loose: more than two buffers, or more overhead than traced. The claim holds in direction only; investigate the queue path |
| Under `-Xmx320m`, L = 16 passes and L = 256 runs out of memory | Lowering the value avoids OOM, as the javadoc says: **the claim holds** |
| Under `-Xmx320m`, both pass | The overhead factor or the buffer count is lower than predicted. The heap claim is weaker; record P(256) |
| Under `-Xmx320m`, both run out of memory | The baseline is too high for this ceiling: not confirmed. Rerun with `-Xmx448m`, where L = 16 must pass |
| The data-file count or sizes do not track L, or `du_bytes` differs by more than 3% across L | The per-file disk claim is wrong, or total disk depends on L (not expected) |
| Sorted heap differs by more than 32 MiB between L = 16 and L = 256 | Sorted mode holds more than one partition in memory: the trace is wrong |

**B3h. Controls.**
- **Only L changes.** The seed, data and JVM flags are the same across L, and `-Xms` = `-Xmx` fixes the heap size.
- **Live set, not garbage.** Each sample follows a forced GC.
- **The instrument can see growth.** The L = 1024 positive control must show buffer growth.
- **The growth comes from the buffer.** The sorted contrast uses the same workload without a buffer, and its heap must stay flat.
- **One variable in the ceiling test.** Both OOM runs use the same ceiling; only L differs.
- **Valid output.** The optional loader step shows the produced files are valid SSTables.
- **Quiet host.** Run nothing else heavy on the host at the same time. Record `nproc`, `free -g` and `df -h $WORK`.

**B4. Risks and cleanup.**
- **Disk:**
  - All output goes under `$WORK` on local disk.
  - The runner deletes each run's output unless `KEEP=1` is set. The largest single output is about 600 MiB.
  - Each GC log is about 1 MB.
  - Never point the output at shared storage or at the source copy.
- **Processes:**
  - Every probe run is wrapped in `timeout 1800` and ends with `System.exit(0)`.
  - Check `pgrep -f MaxSizeProbe` after each tier.
  - Stop the optional node with `nodetool stopdaemon`. Then `pgrep -f CassandraDaemon` must print nothing; otherwise `kill $(cat $WORK/node/pid)`.
- **Memory:**
  - The `-Xmx2g` runs need about 2.5 GiB of RAM free.
  - The OOM runs are capped at 320 MiB and write no heap dump (`-XX:+HeapDumpOnOutOfMemoryError` is not set).
- **Cleanup:** `rm -rf $WORK/out $WORK/node`, and keep `$WORK/logs`. When done, remove `$WORK/src` if the space is needed.

## C. Sources read

src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java
src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java
src/java/org/apache/cassandra/io/sstable/SSTableSimpleWriter.java
src/java/org/apache/cassandra/io/sstable/AbstractSSTableSimpleWriter.java
src/java/org/apache/cassandra/io/sstable/SSTableTxnWriter.java
src/java/org/apache/cassandra/io/sstable/SimpleSSTableMultiWriter.java
src/java/org/apache/cassandra/io/sstable/format/SSTableWriter.java
src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java
src/java/org/apache/cassandra/io/util/SequentialWriter.java
src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java
src/java/org/apache/cassandra/utils/concurrent/BlockingQueues.java
src/java/org/apache/cassandra/db/partitions/PartitionUpdate.java
src/java/org/apache/cassandra/cql3/statements/UpdateStatement.java
src/java/org/apache/cassandra/cql3/statements/DeleteStatement.java
src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/schema/CompressionParams.java
tools/stress/src/org/apache/cassandra/io/sstable/StressCQLSSTableWriter.java
test/unit/org/apache/cassandra/io/sstable/CQLSSTableWriterTest.java
test/unit/org/apache/cassandra/io/sstable/CQLSSTableWriterClientTest.java
doc/modules/cassandra/pages/managing/operating/bulk_loading.adoc
CHANGES.txt
NEWS.txt
build.xml
.build/build-resolver.xml
conf/jvm11-clients.options
https://issues.apache.org/jira/browse/CASSANDRA-18941
https://issues.apache.org/jira/browse/CASSANDRA-17675
https://issues.apache.org/jira/browse/CASSANDRA-19800
https://docs.oracle.com/en/java/javase/11/docs/api/

## D. Stage-4 feedback

none yet
