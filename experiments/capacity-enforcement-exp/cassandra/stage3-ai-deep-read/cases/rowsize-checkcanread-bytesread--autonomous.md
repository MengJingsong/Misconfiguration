# rowSize (per-row read limit of `TrackedDataInputPlus`) — verification solution  <!-- file: cases/rowsize-checkcanread-bytesread--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (capacity-set: the field `limit` is set), **linked**: [`TrackedDataInputPlus.java:52`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TrackedDataInputPlus.java#L52) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `negative`: the limit is not a configured cap. It is the row's own serialized size, read from the sstable or stream, and it bounds how many **bytes are consumed from the input** for one row body. It does not bound heap: a cell's value array is allocated at its encoded length *before* the limit is checked. |
| Ground | (1) Nobody can set it. Its value is `rowSize`, read per row from the data at `UnfilteredSerializer.java:585`, so for well-formed data it equals the data size and cannot be raised or lowered independently of it. (2) Where it actually fires (encoded lengths that do not match the row size, i.e. corruption), `ByteArrayAccessor.read` runs `new byte[length]` (`ByteArrayAccessor.java:102`) before `readFully` reaches `checkCanRead` (`TrackedDataInputPlus.java:184`). The allocation is therefore bounded only by `max_value_size` (`AbstractType.java:594`), not by this limit. It is a corruption/framing guard, not a memory or disk cap. |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). Use a permalink at the pinned tag,
> `[`File.java:123`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/path/File.java#L123)`
> (a range is `#L123-L130`; the path is the file's full path under the repository root).
> Check that the line number is the line you mean. Other citations may stay plain `file:line`.

## A. Constraint trace

**A1. The constraint.**
- **Name:** `TrackedDataInputPlus.limit`, the per-row byte limit. Its value is the row's serialized body size, `rowSize`.
- **Kind:** runtime-derived. It is not a configuration entry, JVM property or constant: it comes from a field of the data being read.
- **Declaration:** the field is declared at [`TrackedDataInputPlus.java:34`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TrackedDataInputPlus.java#L34) (`private final long limit;`). It is assigned at the target line, `TrackedDataInputPlus.java:52`, in the constructor `TrackedDataInputPlus(DataInput source, long limit)` (`:49`). The one-argument constructor passes `-1`, meaning no limit (`:40-43`).
- **Where the value comes from:** the only production caller that passes a limit is [`UnfilteredSerializer.java:585-587`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L585-L587). It runs `long rowSize = in.readUnsignedVInt(); in.readUnsignedVInt(); in = new TrackedDataInputPlus(in, rowSize);`, and only when `header.isForSSTable()` (`:583`). Every other construction site uses the unlimited form: `CassandraStreamReader.java:134`, `CassandraCompressedStreamReader.java:76`, `HintMessage.java:157`, `RowIndexEntry.java:557`.
- **Writer side:** `rowSize` is written at `UnfilteredSerializer.java:199` as `dob.position() + TypeSizes.sizeofUnsignedVInt(previousUnfilteredSize)`, i.e. the serialized row body plus the size of the "previous unfiltered size" vint.
- **Unit:** bytes.
- **Default:** none. The value is per row and equals that row's serialized body size (plus 1–9 bytes, see A3).
- **How it can be set:** not settable by yaml, `-D` or JMX. It changes only when the data changes: a different row size, or a corrupted size or length field. A restart is not relevant.

**A2. What it caps.**
- **Quantity compared:** `bytesRead + size > limit` (`TrackedDataInputPlus.java:184`). `bytesRead` counts the bytes consumed through this wrapper since it was created at the start of the row body. `size` is the number of bytes the next primitive read or `readFully` needs.
- **Resource:** bytes consumed from the underlying `FileDataInput` (the sstable `Data.db` reader) or the stream input, for one row body. That is a read position/framing bound, not heap, off-heap or disk.
- **Heap:** it does not cap heap. Allocation of the cell value happens before the check (A3, step 5). For well-formed data the number of bytes read equals `rowSize` anyway, so the limit never binds.

**A3. Mechanism.**
1. A row is read from an sstable (`deserializeOne`, `UnfilteredSerializer.java:458` onwards; `deserializeRowBody` is called at `:482`, static rows at `:546`). `deserializeRowBody` (`:564`) reads `rowSize` and `previousUnfilteredSize`. It then wraps the input at `:587`, which reaches the target line [`TrackedDataInputPlus.java:52`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TrackedDataInputPlus.java#L52) and stores `limit = rowSize`.
2. Every primitive read and every `readFully` on the wrapper calls `checkCanRead(size)` before delegating (`:66-160`). Variable-length ints go through `DataInputPlus.readUnsignedVInt` → `VIntCoding.readUnsignedVInt(this)` → `readByte`, so they are tracked as well.
3. **The check:** [`TrackedDataInputPlus.java:184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TrackedDataInputPlus.java#L184), `if (limit >= 0 && bytesRead + size > limit)`.
   - **True:** `skipBytes((int)(limit - bytesRead))` advances the source to the end of the row (`:186`, which itself clamps at `:176`). It then throws `EOFException("EOF after " + (limit - bytesRead) + " bytes out of " + size)` (`:187`). `bytesRead` has already been advanced by the skip, so when the source can skip the whole remainder the message reads `EOF after 0 bytes out of <size>`.
   - **False:** the read proceeds and `bytesRead += size`.
4. `skipBytes` (`:174-178`) clamps the skip to `limit - bytesRead`. `skipBytesFully` (`DataInputPlus.java:94-99`) therefore throws `EOFException` when asked to skip past the row end.
5. **Cell values (the memory-relevant path):**
   - `readSimpleColumn` / `readComplexColumn` call `Cell.serializer.deserialize(in, …, ByteArrayAccessor.instance)` (`UnfilteredSerializer.java:652`, `:685`), which calls `header.getType(column).read(accessor, in, DatabaseDescriptor.getMaxValueSize())` (`Cell.java:339`).
   - `AbstractType.read` (`AbstractType.java:582-600`) reads the length vint `l`. It rejects `l > maxValueSize` with `IOException` (`:594`), then calls `accessor.read(in, l)`.
   - `ByteArrayAccessor.read` (`ByteArrayAccessor.java:100-104`) does `byte[] b = new byte[length]; in.readFully(b);`. The array of `l` bytes is allocated **before** `readFully` → `checkCanRead(l)` runs.
   - So when an encoded length exceeds the row size, the heap cost is `l` (up to `max_value_size`, default 256 MiB, `Config.java:310`), and only afterwards does the limit throw.
6. **Error propagation:**
   - The `EOFException` is wrapped in `WrappedException` inside `columns.apply` and unwrapped back to `IOException` (`UnfilteredSerializer.java:622-628`).
   - The sstable iterator turns it into `CorruptSSTableException` (`AbstractSSTableIterator.java:286-297`, `BigTableReader.java:189`/`:355`).
   - That exception is handled per `disk_failure_policy` (default `stop`, `conf/cassandra.yaml:471`).
7. **Bypasses and overshoots:**
   - (a) Allocation-before-check, as in step 5.
   - (b) Slack: `limit = rowSize`, and `rowSize` includes `sizeofUnsignedVInt(previousUnfilteredSize)` (`UnfilteredSerializer.java:199`, `:338-339`). That vint is read *before* wrapping (`:586`), so the limit exceeds the remaining body by 1–9 bytes and a few bytes of overread are tolerated.
   - (c) A corrupted, very large `rowSize` makes the check ineffective.
   - (d) Rows read with a non-sstable header (messaging, `isForSSTable() == false`) are never wrapped.
   - (e) Range tombstone markers (`deserializeMarkerBody`, `:549-561`) are not wrapped.
   - (f) `skipRowBody` (`:698-702`) uses `rowSize` directly via `skipBytesFully`, not this wrapper.

**A4. Other consumers.** Heap used while reading a row that is outside this limit's control:
- Cell value arrays, bounded only by `max_value_size` (`Config.java:310`, `DatabaseDescriptor.java:944-948`, `:1928-1931`).
- Clustering values (`ClusteringPrefix.java:517`, `:674`, also `max_value_size`).
- Partition keys (`SinglePartitionReadCommand.java:1352`).
- The row builder's BTree, reader buffers (`RandomAccessReader` / chunk cache), the key cache and the row index.
- Network frames (`native_transport_max_frame_size`).

Disk is not touched by this read path. Streaming (`CassandraStreamReader.StreamDeserializer`, `:208-225`) also deserializes rows with the sstable header, so the same wrapper and the same allocation order apply there.

**A5. Evidence beyond the source.**
- `test/unit/org/apache/cassandra/utils/BytesReadTrackerTest.java` tests byte counting only, always with the unlimited constructor (`:106`, `:179`, `:207`, `:239`). No existing test exercises `limit`.
- `conf/cassandra.yaml:2143-2145` states that `max_value_size` "is checked when deserializing any value to detect sstable corruption", which supports reading the row-size wrapper as a corruption guard too.
- No git history was available in the source copy (no `.git`), and `CHANGES.txt` has no entry naming `TrackedDataInputPlus`.

## B. Verification solution

**B1. Claim under test.** The per-row limit set at `TrackedDataInputPlus.java:52` (= `rowSize`) does **not** bound the heap allocated while deserializing a row. When an encoded cell length `V` exceeds the row's size `L`, the node still allocates a `byte[V]` (≈ `V` bytes of heap, up to `max_value_size`) before the limit raises `EOFException`. The allocation follows `V` and not `L`. By contrast `max_value_size < V` prevents the allocation (positive control).

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11, Ant.
- Copy the tree to local disk:

  ```
  RUN=/mydata/<operator>-s4/o122
  mkdir -p $RUN && rsync -a <pristine cassandra-5.0.9 copy>/ $RUN/src/
  ```

  Never build in the shared tree.
- Build: `cd $RUN/src && ant jar build-test`.
- Test source: `$RUN/src/test/unit/org/apache/cassandra/io/util/TrackedDataInputPlusLimitTest.java` (new file, below).
- The JVM is the `ant testsome` JUnit JVM: `-Xmx4G` from `build.xml:1245-1255`, HotSpot with thread-allocation accounting enabled (the default).

**B2b. Knobs.**
- `L` (the limit, i.e. what `rowSize` would be) ∈ {64 B, 1 MiB, 16 MiB}. These span tiny to large but stay below `V`, so the check fires.
- `V` (the encoded value length) ∈ {16 MiB, 64 MiB}. These are large enough to dominate allocation noise and below the 4 GiB heap.
- `maxValueSize` passed to `AbstractType.read` ∈ {256 MiB (the default), 8 MiB (positive control, `< V`)}.
- A well-formed case `L = V + 4` with the source holding `V` bytes (`V = 16 MiB`) shows allocation ≈ `V` when the limit does not fire.
- All knobs are set as constants in the test. `L` is the second constructor argument, as at `UnfilteredSerializer.java:587`.

**B2c. Workload.**
- For each `(L, V, maxValueSize)`:
  - Build a byte array `src` = unsigned vint of `V` (`DataOutputBuffer.writeUnsignedVInt(long)`, 4 bytes for 2 MiB ≤ V < 256 MiB), followed by `R = 1024` zero bytes. The source holds far fewer than `V` bytes, so a read could never succeed. That does not matter, because the check (or the length check) fires first.
  - Wrap: `in = new TrackedDataInputPlus(new DataInputBuffer(src), L)`.
  - Call exactly what `Cell.java:339` calls: `BytesType.instance.read(ByteArrayAccessor.instance, in, maxValueSize)`.
- Arithmetic: after the 4-byte vint, `bytesRead = 4`. `checkCanRead(V)` tests `4 + V > L`, which is true for every `L < V + 4`, so the limit is reached.
- Well-formed case: `src` = vint(V) + `V` bytes, `L = V + 4`. Then `4 + V > V + 4` is false and the read succeeds.

**B2d. Observables and instruments.**
- (1) Bytes allocated by the test thread across the single `read` call: `((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId())`, taken before and after. The delta is `A`.
- (2) The exception class and message: `EOFException` "… out of V", or `IOException` "Corrupt value length … max_value_size".
- (3) `in.getBytesRead()` after the call.
- Not observable here: whether the array survives (it is garbage immediately). We measure allocation, which is the transient heap demand.
- Each cell runs 3 repetitions. The test reports the median `A` in MiB. Do one warm-up call with V = 1 MiB first, so that class loading does not land in the measurement.

**B2e. Procedure.**
1. Create `test/unit/org/apache/cassandra/io/util/TrackedDataInputPlusLimitTest.java` in `$RUN/src`:
   - `@BeforeClass`: `DatabaseDescriptor.daemonInitialization();`
   - Helper `long alloc(Runnable r)` that returns the delta from B2d(1).
   - Helper `byte[] src(long V, int R)` as in B2c.
   - One `@Test` per row of B2f. Each catches the expected exception, then prints `RESULT L=<L> V=<V> max=<m> allocMiB=<A/2^20> exc=<class>:<message> bytesRead=<n>` and asserts the predictions in B2f.
   - Mechanism test `testLimitFires`:
     - `L = 100` over 200 bytes. Read 100 single bytes and expect `getBytesRead() == 100`. The 101st `readByte()` throws `EOFException`.
     - New wrapper with `L = 100`: `readFully(new byte[150])` throws, after which `getBytesRead() == 100`.
     - New wrapper with `L = -1`: reads 200 bytes with no exception.
2. Run:

   ```
   cd $RUN/src && ant testsome -Dtest.name=org.apache.cassandra.io.util.TrackedDataInputPlusLimitTest 2>&1 | tee $RUN/unit.log
   ```

3. `grep RESULT $RUN/unit.log` and the JUnit report under `$RUN/src/build/test/output/`.
4. Check that no JVM from the run is left: `pgrep -f TrackedDataInputPlusLimitTest` returns nothing.

**B2f. Predictions** (stated before any run):

| L | V | maxValueSize | Exception | allocMiB (A) | bytesRead after |
|---|---|---|---|---|---|
| 64 B | 16 MiB | 256 MiB | `EOFException`, message ends `out of 16777216` | 16 ≤ A < 17 | 4 + min(R, L−4) = 64 |
| 1 MiB | 16 MiB | 256 MiB | `EOFException … out of 16777216` | 16 ≤ A < 17 | 4 + 1024 = 1028 (source exhausted) |
| 16 MiB | 64 MiB | 256 MiB | `EOFException … out of 67108864` | 64 ≤ A < 65 | 1028 |
| 64 B | 64 MiB | 256 MiB | `EOFException … out of 67108864` | 64 ≤ A < 65 | 64 |
| 1 MiB | 64 MiB | **8 MiB** (control) | `IOException` "Corrupt value length 67108864 … max_value_size" | A < 1 | 4 |
| V+4 | 16 MiB | 256 MiB (well-formed) | none | 16 ≤ A < 17 | V + 4 |

`testLimitFires` passes as described.

The relation: for fixed `V`, `A` is the same (≈ V) across all `L`. For fixed `L`, `A` scales with `V`. `A` drops to near zero only when `maxValueSize < V`.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `A ≈ V` for every `L < V`, `EOFException` thrown, and the control (`max = 8 MiB`) shows `A < 1 MiB` | Claim **confirmed**: the limit does not bound allocation, and `max_value_size` does on the same workload. |
| `A` grows with `L` or stays ≤ `L` (e.g. `A < 1 MiB` when `L = 64 B`) | Claim **refuted**: usage follows the limit, so the check runs before allocation (the source trace would be wrong). |
| `A ≈ 0` in every row, including the well-formed row | Instrument broken (allocation accounting off or JIT-eliminated). **Not confirmed.** Rerun with `-XX:-DoEscapeAnalysis` via `-Dtest.jvm.args`, or measure with JFR. |
| No `EOFException` when `L < V` | The limit never fired, so the limit was not reached. **Not confirmed.** Check the wrapper construction. |
| Control row shows `A ≈ V` | The positive control did not move. **Not confirmed.** Check that `maxValueSize` was passed. |

**B2h. Controls.**
- The `maxValueSize = 8 MiB` row is the positive control: same input, a cap known to bind before allocation (`AbstractType.java:594`).
- The well-formed row shows the allocation is that of the value array itself.
- Varying `L` with fixed `V` isolates the limit.
- The warm-up call and 3 repetitions remove class-loading noise.
- `testLimitFires` shows the limit itself is active, so a flat `A` is not because the check is dead.

**B2i. Stage-4 audit amendments (2026-11-24, before any harness or reading; B1, B2f's numbers and B2g's rows 1–5 unchanged).**
1. *Paths.* `RUN=/mydata/jingsong-cass-s4/o122` on `ms0640` (aarch64). The pristine copy is `/mydata/s4/cassandra-base` (a `copy-source.sh` copy of `cassandra-5.0.9`, already built with `ant build-test`), copied with `cp -a` to `$RUN/src`; `ant testsome` compiles the new test on top of it, so B2a's `ant jar build-test` is not repeated.
2. *Repetitions.* Each B2f row runs 3 times after the warm-up; the test prints one `RESULT` line per repetition (with `rep=<i>`) and one with `rep=median`; the B2f assertions are made on the median `A`, and on the exception and `bytesRead` of every repetition.
3. *Catch-all row added to B2g:* any other mismatch with B2f (an `A` outside its band while the exception is as predicted, a different exception class or message, `testLimitFires` failing) → **Not confirmed** for the unit tier, recorded with the reading. A `bytesRead` that differs from B2f while `A`, the exception and the control match row 1 is recorded as a miss in a mechanism detail and does not change the matched row (it does not bear on B1).

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node with JDK 11 and ≥ 4 GiB free RAM, and a local disk with ≥ 5 GiB free under `$RUN`.
- Build: `cd $RUN/src && ant jar`. Run from `$RUN/src`, with `bin/cassandra` using `conf/` in the copy.
- Configuration edits in `$RUN/src/conf/cassandra.yaml`:
  - `data_file_directories: [$RUN/data]`
  - `commitlog_directory: $RUN/commitlog`
  - `hints_directory: $RUN/hints`
  - `saved_caches_directory: $RUN/saved_caches`
  - `cdc_raw_directory: $RUN/cdc_raw`
  - `disk_failure_policy: ignore`, so a corrupt read does not stop the node and reads can be repeated
  - `storage_port: 17100`
  - `native_transport_port: 19142`
  - `max_value_size: 256MiB` (the default, written explicitly)
  - `listen_address` / `rpc_address: 127.0.0.1`
  - `seeds: "127.0.0.1:17100"`
- In `conf/cassandra-env.sh` set `JMX_PORT="17299"`.
- Environment: `MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M` (G1 per `conf/jvm11-server.options:63`).
- Extra JVM options via `JVM_EXTRA_OPTS`:
  - `-Xlog:gc*:file=$RUN/gc.log:time,uptime`
  - `-XX:StartFlightRecording=name=s4,settings=profile,filename=$RUN/rec.jfr,dumponexit=true`
- Logs go to `CASSANDRA_LOG_DIR=$RUN/logs`.

**B3b. Knobs.**
- Row size `S` (the inserted blob, which determines `L ≈ S + ~10 B`) ∈ {3 MiB, 6 MiB}. Both use a 4-byte length vint (2 MiB ≤ S < 256 MiB), so it can be patched in place without changing the file layout. Both stay under the 16 MiB frame and mutation limits.
- Patched encoded length `V` ∈ {100 MiB, 200 MiB}. Both are 4-byte vints, `< max_value_size` (256 MiB) and `< heap` (1 GiB).
- Positive control: `max_value_size: 64MiB` (yaml, restart) with `S = 3 MiB`, `V = 200 MiB`.
- `L` cannot be set directly. It is varied through `S`, which is the only way it can change.

**B3c. Workload.**
- Write and read path:
  - Table `CREATE KEYSPACE s4 WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE s4.t (k int PRIMARY KEY, v blob) WITH compression = {'enabled': false};`
  - Compression is off, so `Data.db` holds the raw row and no chunk CRC is checked on read.
  - One row `k = 1`, whose `v` is `S` bytes: the 16-byte ASCII marker `S4MARKER-TDIPLIM` followed by zeros.
  - Insert via a generated CQL file (hex literal of `2·S` chars, ≤ 12 MiB of text), flush, drain, stop.
- Corruption:
  - Patch the 4 bytes immediately before the marker in `Data.db` from vint(S) to vint(V).
  - vint(3 MiB) = `e0300000`, vint(6 MiB) = `e0600000`, vint(100 MiB) = `e6400000`, vint(200 MiB) = `ec800000`.
  - The patch keeps the 4-byte width, so the file length and every offset are unchanged.
- Read: restart and run `SELECT v FROM s4.t WHERE k = 1` 3 times, 10 s apart.
- Arithmetic:
  - On read, `bytesRead` before the value is a few bytes (liveness vint, cell flags, length vint).
  - `checkCanRead(V)` tests `~10 + V > S + ~10`, which is true since `V ≥ 100 MiB > 6 MiB`. The limit is reached on every read.
  - `V ≤ 256 MiB` passes `max_value_size`, so `new byte[V]` runs first.
- Duration: about 5 minutes per configuration.

**B3d. Observables and instruments.**
- (1) **Primary:** JFR `jdk.ObjectAllocationOutsideTLAB` events (enabled in `profile.jfc`) with `objectClass = byte[]` and `allocationSize ≥ 50 MiB`, from `$RUN/rec.jfr`. Read with `$JAVA_HOME/bin/jfr print --events jdk.ObjectAllocationOutsideTLAB $RUN/rec.jfr`. If the JDK 11 build has no `jfr` tool, any JDK ≥ 17 `jfr` reads the file.
  - Count the events and their `allocationSize` per read.
  - Stack trace: expect `ByteArrayAccessor.read` ← `AbstractType.read` ← `Cell$Serializer.deserialize`.
- (2) `$RUN/logs/system.log`: a `CorruptSSTableException` caused by `java.io.EOFException: EOF after 0 bytes out of <V>`. Per A3 step 3, the message shows `size = V`, the length of the array already allocated.
- (3) `$RUN/gc.log`: G1 humongous allocations (`G1 Humongous Allocation` GC cause, humongous regions count). This is secondary: a transient object may be freed between GCs.
- (4) The cqlsh error (ReadFailure / server error).
- Not observable directly: resident heap after the read (the array is garbage at once). We measure allocation.

**B3e. Procedure** (per `(S, V, max_value_size)`):
1. Clean start:

   ```
   rm -rf $RUN/{data,commitlog,hints,saved_caches,cdc_raw,logs,gc.log,rec.jfr}
   ```

   Then set `max_value_size` in yaml and start:

   ```
   cd $RUN/src && MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M CASSANDRA_LOG_DIR=$RUN/logs JVM_EXTRA_OPTS="..." bin/cassandra -p $RUN/pid
   ```

   Wait until `bin/nodetool -p 17299 status` shows `UN`.
2. Write the schema with `bin/cqlsh 127.0.0.1 19142 -e "<B3c DDL>"`, then `bin/nodetool -p 17299 disableautocompaction s4`.
3. Generate the insert:

   ```
   python3 -c "import sys;S=int(sys.argv[1]);v=b'S4MARKER-TDIPLIM'+b'\0'*(S-16);open('$RUN/ins.cql','w').write('INSERT INTO s4.t (k,v) VALUES (1,0x%s);\n'%v.hex())" $((S_MiB*1048576))
   ```

   Then `bin/cqlsh 127.0.0.1 19142 --request-timeout=60 -f $RUN/ins.cql`.
4. Sanity read (uncorrupted): `bin/cqlsh 127.0.0.1 19142 -e "SELECT k FROM s4.t WHERE k=1;"` returns 1 row. Then run `bin/nodetool -p 17299 flush s4 t` and `SELECT v FROM s4.t WHERE k=1` (output to `/dev/null`) also succeeds. JFR later shows ≈ S `byte[]` allocations for it, which is the instrument check.
5. `bin/nodetool -p 17299 flush s4 t && bin/nodetool -p 17299 drain`. Then `kill $(cat $RUN/pid)` and wait for the process to exit.
6. Patch the sstable:

   ```
   python3 - <<EOF
   import glob; f=glob.glob('$RUN/data/s4/t-*/*-Data.db'); assert len(f)==1
   b=bytearray(open(f[0],'rb').read()); m=b.find(b'S4MARKER-TDIPLIM'); assert m>=4 and b.count(b'S4MARKER-TDIPLIM')==1
   assert b[m-4:m].hex()=='<vint(S)>', b[m-4:m].hex()
   b[m-4:m]=bytes.fromhex('<vint(V)>'); open(f[0],'wb').write(b); print('patched at', m-4)
   EOF
   ```

7. Start the node again as in step 1, but without the `rm` and with a fresh `rec.jfr` filename.
8. Run `bin/cqlsh 127.0.0.1 19142 -e "SELECT v FROM s4.t WHERE k=1;"` 3 times, 10 s apart. Record each error.
9. `jcmd $(cat $RUN/pid) JFR.dump name=s4 filename=$RUN/rec-<cfg>.jfr`, then `jfr print --events jdk.ObjectAllocationOutsideTLAB $RUN/rec-<cfg>.jfr > $RUN/alloc-<cfg>.txt`. Copy the `system.log` lines with `grep -A5 "EOF after\|Corrupt value length" $RUN/logs/system.log`.
10. Stop the node (`kill $(cat $RUN/pid)`), then confirm with `pgrep -f "$RUN/src"` that it is gone. Archive the results into `$RUN/results-<cfg>/`.

Configurations, in order:
- C1: S=3 MiB, V=100 MiB
- C2: S=3 MiB, V=200 MiB
- C3: S=6 MiB, V=200 MiB
- C4 (positive control): S=3 MiB, V=200 MiB, `max_value_size: 64MiB`

**B3f. Predictions** (per read, stated before any run):

| Config | L (≈ S) | V | Exception in system.log | `byte[]` allocations ≥ 50 MiB per read (JFR) |
|---|---|---|---|---|
| C1 | ≈ 3 MiB | 100 MiB | `EOFException: EOF after 0 bytes out of 104857600` | 1 event, size ≈ 104857616 B (100 MiB + array header) |
| C2 | ≈ 3 MiB | 200 MiB | `… out of 209715200` | 1 event ≈ 200 MiB |
| C3 | ≈ 6 MiB | 200 MiB | `… out of 209715200` | 1 event ≈ 200 MiB (same as C2: doubling L does not change it) |
| C4 (control) | ≈ 3 MiB | 200 MiB | `IOException: Corrupt value length 209715200 encountered, as it exceeds the maximum of 67108864` | 0 events ≥ 50 MiB |

Over 3 reads: C1–C3 give 3 events each, C4 gives 0. The node stays up throughout (`disk_failure_policy: ignore`). Relation: allocation per read = `V` and does not depend on `L`. A `max_value_size` below `V` removes the allocation.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| C1–C3 each show one ≈ `V` `byte[]` per read with the `ByteArrayAccessor.read` stack, the `EOFException … out of V` is logged, and C4 shows none | Claim **confirmed**: usage is flat in `L` and follows `V`, while the positive control (`max_value_size`) moves it. |
| C1–C3 show no large allocation but the `EOFException` is logged | Claim **refuted**: the limit stopped the read before allocation. Re-examine A3 step 5. |
| C3's allocation differs from C2's in proportion to L | Claim **refuted**: usage follows the limit. |
| No `EOFException` and no `Corrupt value length` (read succeeded or failed elsewhere) | The patch missed or the limit was never reached. **Not confirmed.** Check step 6's assertion and that `SELECT v` reads the value rather than skipping it. |
| C4 still shows a ≈ 200 MiB allocation | The positive control did not move. **Not confirmed.** Check that `max_value_size` was applied (`nodetool getconfig`/system.log config dump). |
| JFR file has no `ObjectAllocationOutsideTLAB` events at all, including the sanity read | Instrument broken (settings not `profile`). **Not confirmed.** Use `gc.log` humongous allocations as the fallback. |

**B3h. Controls.**
- C4 is the positive control: same data, same read, and a cap known to bind before allocation.
- The uncorrupted sanity read in step 4 shows the instrument sees a value allocation of ≈ S.
- C2 vs C3 varies only `L`.
- C1 vs C2 varies only `V`.
- Compression is off and `autocompaction` is disabled, so no other reader touches the row.
- There is one sstable and one row, so no other large allocation is expected near the read timestamps. Correlate the JFR event start times with the cqlsh call times.
- Optional extra row: `SELECT k FROM s4.t WHERE k=1`. The value may then be skipped (`helper.canSkipValue`, `Cell.java:331-334` → `skipBytesFully`, clamped by `TrackedDataInputPlus.skipBytes:176`). The expectation is an `EOFException` with **no** large allocation. That would show the limit does guard a skip but not a read. Record it as supporting evidence only.

**B3i. Stage-4 audit amendments (2026-11-24, before any harness or reading; B1, B3f's numbers and B3g's rows 1–6 unchanged).**
1. *Paths and node.* `RUN=/mydata/jingsong-cass-s4/o122/cluster` on `ms0640` (aarch64); the node runs from `$RUN/node-tree`, a `cp -a` of the built `/mydata/jingsong-cass-s4/o122/src` in which `ant` is never run (B3a's `ant jar` is already done there). `ulimit -n 100000` before each start (the node's soft limit is 1024).
2. *JFR file names.* Step 1 records to `$RUN/rec-<cfg>-write.jfr`; step 7 records to `$RUN/rec-<cfg>-read.jfr`; step 9 dumps the read session to `$RUN/rec-<cfg>.jfr`. The sanity read of step 4 is read from `rec-<cfg>-write.jfr` (dumped on exit).
3. *Insert client.* Step 3 sends `$RUN/ins.cql` with `bin/cqlsh -f`. If cqlsh cannot send it (client-side lexer time over 10 min, or a client error), the same statement text is sent with the Python driver bundled in `lib/` (same server path); recorded as a deviation.
4. *Tolerance and count.* "≈ V" means a `jdk.ObjectAllocationOutsideTLAB` event with `objectClass = byte[]` and `allocationSize` in `[V, V + 64]` bytes. Row 1 of B3g requires, for each of C1–C3, one such event per read that logs `EOF after … out of V` (expected 3 per config), each with `ByteArrayAccessor.read` in its stack; and for C4 no `byte[]` event ≥ 50 MiB and the `Corrupt value length` error.
5. *Catch-all row added to B3g:* any other mismatch with B3f (event count different from the number of logged EOF reads, an event size outside the band, a different message) → **Not confirmed** for the cluster tier, recorded with the reading.
6. *Process check.* Step 10's `pgrep -f "$RUN/src"` is replaced by `ps -eo cmd | grep '[C]assandraDaemon'` (the stage-4 safety rule; `pgrep -f` inside an inline `ssh` string matches its own shell).

**B4. Risks and cleanup.**
- Disk: everything goes under `$RUN` on local disk. The data is < 20 MiB, plus logs, JFR (< 200 MiB) and the build (~1 GiB). Nothing goes on shared storage, and the shared source tree is never built in or written to.
- Memory: C2/C3 allocate 200 MiB in a 1 GiB heap, which is safe. Do not raise `V` near the heap size, since an `OutOfMemoryError` kills the node through `JVMStabilityInspector`.
- Ports: 17100/19142/17299 avoid the default ports. Check that they are free with `ss -ltn`.
- Processes: after each config and at the end, `kill $(cat $RUN/pid)`. `pgrep -af "$RUN/src"` and `pgrep -af TrackedDataInputPlusLimitTest` must print nothing. Kill any leftover Ant/JUnit JVM.
- Cleanup: `rm -rf $RUN/{data,commitlog,hints,saved_caches,cdc_raw}` once the results are archived. The corrupted sstable must not be copied anywhere else.

## C. Sources read

- `src/java/org/apache/cassandra/io/util/TrackedDataInputPlus.java`
- `src/java/org/apache/cassandra/io/util/DataInputPlus.java`
- `src/java/org/apache/cassandra/io/util/DataInputBuffer.java` (constructors)
- `src/java/org/apache/cassandra/io/util/DataOutputPlus.java` (`writeUnsignedVInt`)
- `src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java`
- `src/java/org/apache/cassandra/db/rows/Cell.java`
- `src/java/org/apache/cassandra/db/marshal/AbstractType.java`
- `src/java/org/apache/cassandra/db/marshal/ByteArrayAccessor.java`
- `src/java/org/apache/cassandra/db/SerializationHeader.java`
- `src/java/org/apache/cassandra/db/streaming/CassandraStreamReader.java`
- `src/java/org/apache/cassandra/db/streaming/CassandraCompressedStreamReader.java` (construction site)
- `src/java/org/apache/cassandra/hints/HintMessage.java` (construction site)
- `src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java` (construction site)
- `src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java`
- `src/java/org/apache/cassandra/io/sstable/AbstractSSTableIterator.java`
- `src/java/org/apache/cassandra/utils/vint/VIntCoding.java`
- `src/java/org/apache/cassandra/config/Config.java` (`max_value_size`)
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (`max_value_size` validation, `getMaxValueSize`)
- `test/unit/org/apache/cassandra/utils/BytesReadTrackerTest.java`
- `test/unit/org/apache/cassandra/streaming/StreamReaderTest.java`, `test/unit/org/apache/cassandra/hints/DTestSerializer.java` (grep only)
- `conf/cassandra.yaml` (`max_value_size`, `disk_failure_policy`, `sstable.selected_format`)
- `conf/cassandra-env.sh`, `conf/jvm11-server.options`
- `build.xml` (test JVM heap, `testsome`)
- `CHANGES.txt` (grep)

## D. Stage-4 feedback

**2026-11-24, run 1 (Jingsong's stage-4 agent, node `ms0640`, aarch64), results file `~/writeup-ext/out/o122/results.md`.**
- **Unit tier: Confirmed, does not cap** (B2g row 1). Per call, the thread allocated `V` + about 900 B at every `L`: 16.0009 MiB for `L` = 64 B and 1 MiB (`V` = 16 MiB), and 64.0009 MiB for `L` = 64 B and 16 MiB (`V` = 64 MiB). Every one of these reads threw `EOFException … out of V`. The control (`maxValueSize` = 8 MiB) allocated 2,408 B and threw `Corrupt value length 67108864`. The well-formed read allocated 16.0001 MiB. `testLimitFires` passed.
- **Cluster tier: Confirmed, does not cap** (B3g row 1). JFR recorded one `byte[]` of `V` + 16 B per corrupt read: 104,857,616 B in C1 and 209,715,216 B in C2 and in C3 (3 of 3 reads each). The stack is `ByteArrayAccessor.read:102 ← AbstractType.read:599 ← Cell$Serializer.deserialize:339`. Doubling `L` (C2 against C3) did not change it. Each read then logged `EOFException: EOF after 0 bytes out of V`, thrown at `TrackedDataInputPlus.checkCanRead:187` through `readFully:117` from `ByteArrayAccessor.java:103`, the line after the allocation. C4 (`max_value_size: 64MiB`) logged `Corrupt value length 209715200 …` 3 times and had no `byte[]` of 50 MiB or more. The node stayed up throughout.
- **Outcome class: true negative.**
- **Amendments:** the audit added B2i and B3i (2026-11-24, before any reading). They cover paths, repetitions, tolerances and a catch-all row; B1 and the predictions are unchanged.
- **For stage 3, not applied:**
  - The optional B3h `SELECT k` read did **not** skip the value. It allocated `V` and threw the same EOF in C1–C3, so on this CQL path the column filter treats `v` as queried. The B3h expectation is wrong; this is supporting evidence only.
  - The cluster tier varies `L` at two values only.
  - The `max_value_size` throw is at `AbstractType.java:595`; the `if` is at `:594`.
