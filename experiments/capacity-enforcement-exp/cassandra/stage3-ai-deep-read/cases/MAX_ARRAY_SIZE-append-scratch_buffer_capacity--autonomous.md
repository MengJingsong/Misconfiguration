# MAX_ARRAY_SIZE (DataOutputBuffer) — verification solution  <!-- file: cases/MAX_ARRAY_SIZE-append-scratch_buffer_capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (`catch (BufferOverflowException boe)` in `append`), **linked**: [`SortedTableWriter.java:155`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java#L155) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-opus-5-5, Claude Code 2.1.330, 2026-11-24 |
| Estimate | `positive`. The given line catches the `BufferOverflowException` that `DataOutputBuffer.validateReallocation` throws when the per-thread row serialization scratch buffer would have to grow past `MAX_ARRAY_SIZE` (`Integer.MAX_VALUE - 8` = 2,147,483,639 bytes). The buffer (direct memory by default) never grows past that size. The write fails instead and the buffer is freed. The cap is per buffer and fixed: it does not limit the heap that holds the row, and while the last resize copies data, old and new buffers exist together (about 3.42 GiB). |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `DataOutputBuffer.MAX_ARRAY_SIZE`. It is a **constant** (`static final int`), first declared at
[`DataOutputBuffer.java:118`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L118):
`static final int MAX_ARRAY_SIZE = Integer.MAX_VALUE - 8;`. The unit is bytes (buffer capacity). The value is 2,147,483,639. The comment at
`DataOutputBuffer.java:115-116` explains it: the JVM array-length limit, with HotSpot's observed −2 and `ByteArrayOutputStream`'s −8 margin.
It cannot be changed: there is no yaml key, `-D` property or JMX attribute. Changing it means a code change and a rebuild.
Related properties shape how the buffer grows to the cap but do not move the cap:
- `cassandra.DOB_DOUBLING_THRESHOLD_MB` (default 64) sets where growth switches from ×2 to ×1.5 (`CassandraRelevantProperties.java:203`, `DataOutputBuffer.java:48,166-169`).
- `cassandra.dob_max_recycle_bytes` (default 1 MiB) sets the largest scratch buffer kept after `close()` (`CassandraRelevantProperties.java:204`, `DataOutputBuffer.java:53,71-80`).
- `cassandra.dob.allocate_type` (`DIRECT` default / `ONHEAP`) chooses direct or heap memory for the scratch buffer (`CassandraRelevantProperties.java:183`, `DataOutputBuffer.java:55,84-89`).
All three are read once in static initialisers, so a change needs a restart.

**A2. What it caps.** It caps the capacity of one growable `DataOutputBuffer`. On the path through the given line, that buffer is the
thread-local **scratch buffer** (`DataOutputBuffer.scratchBuffer`, `DataOutputBuffer.java:63-92`). The SSTable writer serializes each
row body into this buffer before writing it to the data file. With the default `DIRECT` allocation type, the memory is **off-heap
(direct)**. The quantity compared against the limit is the requested new capacity (`saturatedArraySizeCast(newSize)`) against the current
`capacity()` (`DataOutputBuffer.java:151-152`). In effect, a single row body cannot be larger than 2,147,483,639 bytes, and the scratch
buffer never holds more than that.

**A3. Mechanism.**
1. Flush (`Flushing.java:171`), compaction (`CompactionAwareWriter.java:158` → `SSTableRewriter.java:136`) and offline/simple writers
   (`SimpleSSTableMultiWriter.java:49`) call `SortedTableWriter.append(partition)` (`SortedTableWriter.java:132`).
   The concrete writers are `BigTableWriter`/`BtiTableWriter`, and the default format is `big` (`conf/cassandra.yaml:1172`).
2. `append` → `addStaticRow`/`addRow` (`SortedTableWriter.java:146,149,189-217`) → `partitionWriter.addStaticRow` / `addUnfiltered`
   (`SortedTablePartitionWriter.java:117-128`) → `UnfilteredSerializer.serialize(Row …)` (`UnfilteredSerializer.java:151`).
3. For an SSTable header (`header.isForSSTable()`), the row body is first serialized into `DataOutputBuffer.scratchBuffer.get()`
   (`UnfilteredSerializer.java:193-204`). The writer needs the body's size first, to write it as a vint ahead of the body (`:199`).
   Every cell, including every element of a multi-cell collection, goes into that buffer (`:236-280`).
4. When the buffer is full, `BufferedDataOutputStreamPlus.write(...)` calls `doFlush(count)` (`BufferedDataOutputStreamPlus.java:104-112,130-136,145-146`).
   For `DataOutputBuffer` this is `expandToFit(count)` (`DataOutputBuffer.java:136-139,174-182`).
5. `calculateNewSize` (`DataOutputBuffer.java:158-172`) computes `max(cap*2, cap+count)` while the capacity is ≤ 64 MiB, then
   `max(cap*1.5, cap+count)`, and passes the result to `validateReallocation` (`:149-155`). That method saturates the size to
   `MAX_ARRAY_SIZE` (`:121-125`).
   **The check:** [`DataOutputBuffer.java:152`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L152)
   `if (saturatedSize <= capacity()) throw new BufferOverflowException();`.
   - **Below the limit:** it returns the new size. `allocate(...)` creates the new buffer, the old one is copied in, and `setBuffer`
     frees the old one with `FileUtils.clean` (`:178-187`, `FileUtils.java:362`).
   - **At the limit:** once the capacity is already 2,147,483,639 and more bytes must be written, the saturated size equals the
     capacity, so it throws `BufferOverflowException`.
6. The exception travels up through the serializer. While it does, the `try`-with-resources at `UnfilteredSerializer.java:195` closes the
   scratch buffer. Because its capacity is > 1 MiB, `close()` replaces it with a 128-byte buffer and frees the large one
   (`DataOutputBuffer.java:71-80,186`).
7. **The given line**: [`SortedTableWriter.java:155`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java#L155)
   catches the `BufferOverflowException` and rethrows `PartitionSerializationException`. Its message is "Failed to serialize partition key
   '%s' on table '%s' in keyspace '%s'." (`PartitionSerializationException.java:25-35`). The flush or compaction that called `append`
   fails, and its transaction aborts.

Growth sequence with the default threshold (bytes): 128 → … → 67,108,864 → 134,217,728 → 201,326,592 → 301,989,888 → 452,984,832 →
679,477,248 → 1,019,215,872 → 1,528,823,808 → **2,147,483,639** (saturated) → `BufferOverflowException` on the next expansion.
**Overshoot:** during the last expansion the old buffer (1,528,823,808) and the new one (2,147,483,639) are both allocated, so the peak
is about 3,676,307,447 B ≈ 3.42 GiB of direct memory per thread.
**Bypass / other failure modes:**
- If `-XX:MaxDirectMemorySize` is smaller than that peak plus the baseline, `ByteBuffer.allocateDirect` throws
  `OutOfMemoryError: Direct buffer memory` before the check is reached. The JVM limit then binds first.
- The overflow can also come from `DataOutputBufferFixed` (`DataOutputBufferFixed.java:49-64`), but no such buffer is on this write path.
- The `BigFormatPartitionWriter` row-index buffer is another growable `DataOutputBuffer` (`BigFormatPartitionWriter.java:193-205`).
  It would hit the same check only with a row index larger than 2 GiB, which is impractical.
- Range-tombstone markers are not buffered: their size is computed instead (`UnfilteredSerializer.java:289-293`).

**A4. Other consumers.** These use the same memory outside this cap:
- the heap that holds the row being written: the memtable for a flush, or the merged row in compaction. It is unbounded by this
  constant and is larger than the cap when the cap binds.
- one scratch buffer per writing thread (each flush writer and compaction thread can reach about 2 GiB, or about 3.42 GiB transiently,
  at the same time).
- the chunk cache / `BufferPool` (`file_cache_size`, `conf/cassandra.yaml:742-757`) and networking buffers.
- the `Mutation` serialization paths, which also use `scratchBuffer` (`Mutation.java:453,491`).
- the data file on disk, which is written only after each row body has been buffered.

**A5. Evidence beyond the source.**
- `CHANGES.txt:1356`, "Throw BufferOverflowException from DataOutputBuffer for better visibility (CASSANDRA-16214)",
  <https://issues.apache.org/jira/browse/CASSANDRA-16214>.
- `test/unit/org/apache/cassandra/io/util/DataOutputTest.java:141-248`. It has a fake-capacity test (`testDataOutputBufferMaxSizeFake`),
  a real test that is skipped below about 4.7 GiB of heap (`testDataOutputBufferMaxSize`), and tests of `saturatedArraySizeCast` and
  `validateReallocation`.
- JDK `ByteBuffer.allocateDirect` takes an `int` capacity, and direct allocations count toward `-XX:MaxDirectMemorySize`:
  <https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html#allocateDirect(int)>.

## B. Verification solution

**B1. Claim under test.** Serializing a row (body) for an SSTable never makes the scratch buffer larger than `MAX_ARRAY_SIZE` = 2,147,483,639 bytes.
- A row body above that size makes `SortedTableWriter.append` fail with `PartitionSerializationException` (cause `BufferOverflowException`).
- Direct memory used by that buffer peaks at no more than about 3.42 GiB above baseline, during the final copy, and returns to baseline after the failure.
- A row body just below the limit is written successfully.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11, Ant, ≥ 16 GiB free RAM, ≥ 6 GiB free local disk.
- Copy the tree to local disk: `rsync -a <source>/ /local/s3u/cassandra-5.0.9/`, then `cd /local/s3u/cassandra-5.0.9 && ant jar`.
- Put the probe sources outside the tree, in `/local/s3u/probe/src/`:
  - `org/apache/cassandra/io/util/ScratchCapProbe.java`. It must be in this package because `capacity()` is package-private.
  - `S3RowWriterProbe.java`
- Compile:
  `javac -cp "build/classes/main:lib/*:build/lib/jars/*" -d /local/s3u/probe/classes $(find /local/s3u/probe/src -name '*.java')`
- Run classpath: `/local/s3u/probe/classes:build/classes/main:lib/*:build/lib/jars/*:conf`
- Base JVM options: `-Xmx6g -XX:MaxDirectMemorySize=6g -Dcassandra.storagedir=/local/s3u/storage`
- In both probes, a daemon sampler thread reads `ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)` (name `direct`,
  `getMemoryUsed()`) every 10 ms and records the maximum.

**B2b. Knobs.** The cap itself cannot be set. What varies is the operand size, plus controls that change the surroundings:
- **U1, bytes written** to the scratch buffer: 1,400 MiB / 2,047 MiB / 2,100 MiB, written as 1 MiB `write(byte[])` calls.
- **U2, number of map entries N** in a single row, each a 1 MiB blob: N = 1,400 / 2,046 / 2,049 / 2,240.
  Per entry, the body is 1,048,576 B of value plus about 10–20 B of cell overhead.
- **Controls**, each changing one JVM option and run at U2 N = 2,240:
  - (c1) `-Dcassandra.DOB_DOUBLING_THRESHOLD_MB=4096`: a different growth path to the same cap.
  - (c2) `-Dcassandra.dob.allocate_type=ONHEAP` with `-Xmx12g`: the same cap applied to heap instead.
  - (c3) `-XX:MaxDirectMemorySize=3g`: the JVM direct limit binds before the constant.

**B2c. Workload.**
- **U1** (`ScratchCapProbe.main(totalMiB)`):
  1. `DataOutputBuffer dob = DataOutputBuffer.scratchBuffer.get();`
  2. Loop `dob.write(chunk)` with a 1,048,576-byte random `chunk`. After each write, if `dob.capacity()` changed, print it.
  3. Catch `BufferOverflowException`, then print `dob.position()` and the class of the exception.
  4. `dob.close()`, then print `dob.capacity()` and the direct `MemoryUsed`.

  Arithmetic: 2,047 MiB = 2,146,435,072 < 2,147,483,639 (fits). 2,100 MiB = 2,202,009,600 > the cap (overflows during the 2,048th chunk).
- **U2** (`S3RowWriterProbe.main(N, outDir)`) uses the public offline writer, which goes through
  `SSTableSimpleWriter` → `SSTableTxnWriter` → `SimpleSSTableMultiWriter` → `SortedTableWriter.append`.
  ```java
  CQLSSTableWriter w = CQLSSTableWriter.builder().inDirectory(outDir)
      .forTable("CREATE TABLE ks.t (pk int PRIMARY KEY, m map<int, blob>) WITH compression = {'enabled':'false'}")
      .using("UPDATE ks.t SET m = m + ? WHERE pk = ?").sorted().build();
  // N/14 calls (last call holds the remainder), each a Map<Integer,ByteBuffer> of 14 distinct keys -> 1 MiB random blob
  w.addRow(map, 1);   // all for pk = 1: merged into one row
  w.close();          // writes the single partition -> append
  ```
  `.sorted()` is required. The unsorted writer flushes by buffer size and would split the row (`SSTableSimpleWriter.java:74-91`).
  Arithmetic, at about 1,048,586 B per entry:
  - N = 1,400 → 1.468e9 B, below the last-but-one capacity of 1,528,823,808.
  - N = 2,046 → 2.1454e9 B, below the cap by about 2 MB.
  - N = 2,049 → 2.1485e9 B, above the cap.
  - N = 2,240 → 2.349e9 B.

**B2d. Observables and instruments.**
- For U1: the capacity sequence and `position()` at the throw, both from the probe's own output.
- For U2: the exception class, message and cause chain (`printStackTrace`); in particular, whether `SortedTableWriter.append` and
  `DataOutputBuffer.validateReallocation` appear in the stack.
- Peak and post-run direct `MemoryUsed`, from the 10 ms sampler.
- The `*-Data.db` size in `outDir` (`ls -l`).
- With c2: peak heap used, from the `MemoryMXBean` sampler.

What cannot be observed directly: the scratch buffer's capacity inside U2, because the stack hides it. It is inferred from the direct pool's peak and plateau.

**B2e. Procedure.**
1. Build and compile (B2a).
2. U1: `java <opts> -cp <cp> org.apache.cassandra.io.util.ScratchCapProbe <MiB>` for 1400, 2047, 2100. Each run is a fresh JVM.
3. U2: `rm -rf /local/s3u/out && mkdir -p /local/s3u/out/ks/t`, then `java <opts> -cp <cp> S3RowWriterProbe <N> /local/s3u/out/ks/t`
   for N in 1400, 2046, 2049, 2240. Clean `out` between runs.
4. Run controls c1–c3 with U2 at N = 2,240, then c1 with U1 at 2,100 MiB.
5. Record everything in the B2g table.

**B2f. Predictions.**

U1:
- **1,400 MiB:** capacities follow the A3 sequence up to 1,528,823,808. No exception is thrown.
- **2,047 MiB:** the last capacity is 2,147,483,639. No exception is thrown, and the peak direct memory is about 3.68e9 B above baseline.
- **2,100 MiB:** `BufferOverflowException` with `position()` = 2,147,483,639 exactly. The capacity never exceeds 2,147,483,639. After
  `close()` the capacity is 128 and direct `MemoryUsed` returns to within 1 MiB of baseline.
- **c1 (U1 at 2,100 MiB):** the sequence doubles up to 1,073,741,824 and then goes to 2,147,483,639. The throw happens at the same
  position, and the peak is about 3.22e9 B.

U2:
- **N = 1,400:** succeeds. The peak direct is about 2.55e9 B above baseline (1,019,215,872 + 1,528,823,808), and Data.db is about 1.468 GB.
- **N = 2,046:** succeeds. The peak direct is about 3.68e9 B above baseline, and Data.db is about 2.145 GB.
- **N = 2,049 and N = 2,240:** `PartitionSerializationException: Failed to serialize partition key '1' on table 't' in keyspace 'ks'.`
  - The cause is `BufferOverflowException`, raised at `DataOutputBuffer.validateReallocation` and passing through
    `UnfilteredSerializer.serialize` and `SortedTableWriter.append`.
  - The peak direct is ≤ about 3.68e9 B above baseline, and after the failure it returns to baseline.
  - No Data.db is left (the transaction aborted).
- **c2 (`ONHEAP`):** same exception. The heap peak rises by about 3.4 GiB instead, and direct memory stays flat.
- **c3 (3 GiB direct limit):** `OutOfMemoryError: Direct buffer memory` during the 1,528,823,808 → 2,147,483,639 expansion. There is no `PartitionSerializationException`.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| U1 2,100 MiB throws at position 2,147,483,639; capacity never > that; U2 N≥2,049 fails with PSE ← BOE through `SortedTableWriter.append` | Claim confirmed: the constant caps the buffer and stops the write |
| U2 N=2,046 succeeds, N=2,049 fails | The boundary sits at the cap (within the per-cell overhead): confirms the cap and not some other limit |
| U2 N=2,240 succeeds, or a Data.db > 2.15 GB is written | Claim wrong: the row body is not bounded by this buffer |
| Peak direct > baseline + 3.7e9 B, or no return to baseline after the failure | Claim wrong about the memory bound (leak, or a second unbounded buffer) |
| Exception comes from somewhere other than `validateReallocation` (e.g. OOM, `MutationExceededMaxSize`) at default options | Not confirmed: another limit bound first. Check the options against B2a |
| c1 changes the growth sequence but not the throw position | Confirms the cap is independent of the growth knob |
| c3 gives OOM Direct instead of BOE | Shows the JVM direct limit can bind before the constant. This is not a refutation, but record it as a precondition |

**B2h. Controls.**
- N = 1,400 is a positive control: the same workload, below the cap, moves direct usage (about 2.5e9 B) and succeeds.
- N = 2,046 versus N = 2,049 brackets the boundary.
- c1 separates the cap from the growth policy, c2 separates it from the allocation type, and c3 separates it from the JVM direct limit.
- A fresh JVM per run means the thread-local buffer starts at 128 bytes.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node with ≥ 32 GiB RAM and ≥ 15 GiB free local disk.
- Copy the tree to `/local/s3c/cassandra-5.0.9` and run `ant jar`.
- In `conf/cassandra.yaml`, put every path on local disk:
  - `data_file_directories: [/local/s3c/data]`
  - `commitlog_directory: /local/s3c/commitlog`
  - `saved_caches_directory: /local/s3c/saved_caches`
  - `hints_directory: /local/s3c/hints`
  - `cdc_raw_directory: /local/s3c/cdc`
- Also in `conf/cassandra.yaml`: `listen_address`/`rpc_address: 127.0.0.1`, `concurrent_compactors: 1`, `compaction_throughput: 64MiB/s`
  (the default, which keeps the growth slow enough to sample), and `file_cache_enabled: false` to keep the chunk cache out of the direct readings.
- Keep the defaults `commitlog_segment_size: 32MiB`, which makes `max_mutation_size` = 16 MiB (`DatabaseDescriptor.java:898-899`).
- Start with `MAX_HEAP_SIZE=12G MAX_DIRECT_MEMORY_SIZE=8G bin/cassandra -p /local/s3c/pid` (G1 default; `conf/cassandra-env.sh:115-140`).
- Client: Python 3 with the bundled driver, `PYTHONPATH=lib/cassandra-driver-internal-only-3.29.0.zip`, or `pip install --user cassandra-driver==3.29.0`.

**B3b. Knobs.** The constant cannot be set. What varies is the size of one row produced by a **major compaction** (row-entry count E):
- R1, E = 560 (control)
- R2, E = 1,904 (below the cap)
- R3, E = 2,240 (above the cap)

The scratch-buffer properties stay at their defaults.

**B3c. Workload.**
1. Create the keyspace and table:
   `CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':1};`
   `CREATE TABLE ks.t (pk int PRIMARY KEY, m map<int, blob>) WITH compression={'enabled':'false'} AND compaction={'class':'SizeTieredCompactionStrategy','enabled':'false'};`
2. Run `nodetool disableautocompaction ks t`.
3. Use a separate `pk` per run: R1 uses pk = 1, R2 pk = 2, R3 pk = 3.
4. Each statement is `UPDATE ks.t SET m = m + %s WHERE pk = %s`, with a dict of 14 distinct int keys, each mapped to `os.urandom(1048576)`.
   That is about 14.0 MiB, under the 16 MiB maximum mutation size.
5. Run `nodetool flush ks t` after every F updates, so the row is spread over 8 SSTables. No single flush comes near the cap: the largest
   flush row is about 280 MiB.
   - R1: 40 updates, F = 5 (E = 560)
   - R2: 136 updates, F = 17 (E = 1,904)
   - R3: 160 updates, F = 20 (E = 2,240)
6. Run `nodetool compact ks t`. The major compaction merges each row into one row, and `append` serializes it.

Each run is done on a fresh data directory (wipe and restart between runs) so that only one large row exists.
Arithmetic, at about 1,048,586 B per entry:
- R2 → 1.9965e9 B. This is above 1,528,823,808, so the buffer reaches 2,147,483,639, but the body fits.
- R3 → 2.3488e9 B, above the cap.
- R1 → 0.587e9 B, so the capacity stops at 679,477,248.

Duration: writes take a few minutes. Compaction at 64 MiB/s takes about 10 s (R1), 31 s (R2) and about 32 s up to the failure (R3).

**B3d. Observables and instruments.**
- Direct buffer pool, sampled every 1 s during compaction:
  `while kill -0 $(cat /local/s3c/pid); do date +%s.%N; bin/nodetool sjk mx -b 'java.nio:type=BufferPool,name=direct' -mg -f MemoryUsed; sleep 1; done > direct.log`.
  The plateau at the cap lasts several seconds (R3: 1,458 → 2,048 MiB at 64 MiB/s ≈ 9 s), so 1 s sampling sees it.
- Process RSS: `ps -o rss= -p $(cat /local/s3c/pid)` in the same loop.
- `logs/system.log`: `grep -n "PartitionSerializationException\|BufferOverflowException\|Direct buffer memory"`.
- `bin/nodetool tablestats ks.t` (live SSTable count, space used) and `ls -l /local/s3c/data/ks/t-*/`.
- `bin/nodetool compactionstats` and `compactionhistory`.

What cannot be observed directly: the scratch buffer's capacity. It is inferred from the plateau in direct `MemoryUsed` above the baseline taken just before `nodetool compact`.

**B3e. Procedure.**
1. Configure, then start the node with `MAX_HEAP_SIZE=12G MAX_DIRECT_MEMORY_SIZE=8G bin/cassandra -p /local/s3c/pid`. Wait for `nodetool status` UN.
2. Create the schema (B3c), then `nodetool disableautocompaction ks t`.
3. Run the writer script for the run (updates, F), with `nodetool flush ks t` every F updates. Check 8 live SSTables.
4. Take baseline direct readings for 10 s, start the sampler, run `nodetool compact ks t`, and wait until `compactionstats` shows no pending compactions.
5. Collect `direct.log`, `system.log`, `tablestats` and `ls`.
6. `bin/nodetool stopdaemon`, then confirm with `pgrep -f CassandraDaemon` (nothing found). `rm -rf /local/s3c/{data,commitlog,saved_caches,hints,cdc}/*`.
   Repeat for the next run in the order R1, R2, R3.

**B3f. Predictions.** Direct values are given above the pre-compaction baseline.
- **R1:** compaction succeeds and leaves 1 SSTable of about 0.587 GB. The direct peak is ≤ about 1.14e9 B (452,984,832 + 679,477,248), and it returns to baseline afterwards.
- **R2:** compaction succeeds and leaves 1 SSTable of about 2.0 GB.
  - Direct memory plateaus at about 2.15e9 B, with a transient up to about 3.68e9 B, and returns to baseline.
  - There is no `PartitionSerializationException` in the log.
- **R3:** compaction fails.
  - `system.log` has `PartitionSerializationException: Failed to serialize partition key '3' on table 't' in keyspace 'ks'`, caused by
    `java.nio.BufferOverflowException` at `DataOutputBuffer.validateReallocation`.
  - 8 live SSTables remain, and no new SSTable of 2.3 GB appears.
  - Direct memory plateaus at about 2.15e9 B and never goes above about 3.68e9 B. Within one sample after the failure it is back at baseline.
  - The node stays up (no OOM).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| R3 fails with PSE ← BOE; direct plateau ≈ 2.15e9 B, max ≤ ≈ 3.7e9 B; back to baseline | Claim confirmed: the constant caps the scratch buffer on the real node |
| R2 succeeds with the same plateau ≈ 2.15e9 B | Positive control: the same workload drives the buffer up to the cap without failing |
| R3 compaction succeeds and writes a 2.35 GB row | Claim wrong: row bodies are not bounded by this buffer on this path |
| Direct above baseline + 3.7e9 B, or not released after the failure | Claim wrong about the memory bound |
| OOM `Direct buffer memory` or node death instead of PSE | Not confirmed: the JVM direct limit bound first. Check `MAX_DIRECT_MEMORY_SIZE` |
| `MutationExceededMaxSizeException` during writes, or the row split by unexpected flushes (fewer entries than E) | Not confirmed: the workload did not reach the operand. Reduce the entries per update |
| Direct does not move in R1/R2 | Instrument or allocation type wrong (check `cassandra.dob.allocate_type`). Not confirmed |

**B3h. Controls.**
- R1 and R2 use the same table, client path and compaction, below the cap. They show direct usage moving with row size, and success.
- R3 differs from R2 only in entry count.
- Turning off the chunk cache and allowing one compactor removes the other big direct consumers.
- Disabling autocompaction and wiping the data directory per run make sure only the intended merge happens.
- Checking `max_mutation_size` and the SSTable counts shows each row was built as designed.

**B4. Risks and cleanup.**
- **Memory.** Both tiers allocate 2–3.5 GiB of direct memory. Use a machine with ≥ 16 GiB (unit) or ≥ 32 GiB (cluster) of free RAM,
  and run nothing else memory-heavy.
- **Disk.** Unit U2 writes up to about 2.2 GB in `/local/s3u/out`. Cluster runs write about 2.4 GB of SSTables plus up to about 2.4 GB
  of commit log, and R2 writes about 2 GB more for the compaction output. All of it goes on local disk: check `df` ≥ 15 GiB first.
  Never use shared storage.
- **Leftover processes.** Stop every process the run starts:
  - after each unit run, `pgrep -f 'ScratchCapProbe|S3RowWriterProbe'` must find nothing.
  - on the cluster, run `nodetool stopdaemon` and then confirm `pgrep -f CassandraDaemon` finds nothing. Kill the sampler loop with
    `pkill -f "sjk mx"`.
- **Cleanup.** `rm -rf /local/s3u /local/s3c` after the readings are copied off. Do not build in, or add files to, the shared source tree.

## C. Sources read

src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java
src/java/org/apache/cassandra/io/util/DataOutputBuffer.java
src/java/org/apache/cassandra/io/util/DataOutputBufferFixed.java
src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java
src/java/org/apache/cassandra/io/util/FileUtils.java
src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java
src/java/org/apache/cassandra/db/rows/UnfilteredRowIteratorSerializer.java
src/java/org/apache/cassandra/db/rows/PartitionSerializationException.java
src/java/org/apache/cassandra/io/sstable/format/SortedTablePartitionWriter.java
src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java
src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java
src/java/org/apache/cassandra/io/sstable/SSTableSimpleWriter.java
src/java/org/apache/cassandra/io/sstable/AbstractSSTableSimpleWriter.java
src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 895-901, 2827)
src/java/org/apache/cassandra/db/Mutation.java (grep)
src/java/org/apache/cassandra/db/memtable/Flushing.java, db/compaction/writers/CompactionAwareWriter.java, io/sstable/SSTableRewriter.java, io/sstable/SimpleSSTableMultiWriter.java (call sites, grep)
test/unit/org/apache/cassandra/io/util/DataOutputTest.java
conf/cassandra.yaml, conf/cassandra-env.sh, conf/jvm-server.options, conf/jvm11-server.options
CHANGES.txt
https://issues.apache.org/jira/browse/CASSANDRA-16214
https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html#allocateDirect(int)

## D. Stage-4 feedback

none yet
