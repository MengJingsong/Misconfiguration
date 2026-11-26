# NIO_DATA_OUTPUT_STREAM_PLUS_BUFFER_SIZE — verification solution  <!-- file: cases/NIO_DATA_OUTPUT_STREAM_PLUS_BUFFER_SIZE-BufferedDataOutputStreamPlus-bufferSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the direct allocation sized by the property: [`BufferedDataOutputStreamPlus.java:52`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L52) (`ByteBuffer.allocateDirect(bufferSize)`), reached from the one-argument constructor at [`BufferedDataOutputStreamPlus.java:45-48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L45-L48) |
| Pinned source | `cassandra-5.0.9` |
| Lead source | config-first |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code (CLI version not recorded), 2026-11-26 |
| Estimate | `positive` — the property is the exact capacity of an off-heap (direct) staging buffer that every `FileOutputStreamPlus` allocates when opened and frees when closed; the buffer never grows, so per-stream direct memory equals the value and peak direct memory from this source is value × (streams open at once). The bound is per stream, not aggregate, and at the 32 KiB default it is small; it becomes memory-significant only when the property is raised. |
| Ground | — |

> The property does not cap disk: the bytes written to each file are the same whatever the buffer size (§A2); the cluster tier checks this as a side reading.

## A. Constraint trace

**A1. The constraint.** `NIO_DATA_OUTPUT_STREAM_PLUS_BUFFER_SIZE`, a JVM system property
`-Dcassandra.nio_data_output_stream_plus_buffer_size`, declared at
[`CassandraRelevantProperties.java:375`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L375).
Unit: bytes (an `int`). Default `convertToString(32 * 1024)` = `"32768"` (32 KiB), a literal in the enum
constant. It is parsed by `getInt()` (`CassandraRelevantProperties.java:794-800`) with `Integer.decode`
(`CassandraRelevantProperties.java:973-983`), so decimal, `0x…` hex and leading `-` are accepted; a
non-integer throws `ConfigurationException`. It is read **once**, at class initialisation, into
`private static final int DEFAULT_BUFFER_SIZE` (`BufferedDataOutputStreamPlus.java:41`), so it can be set
only with `-D` at JVM start (e.g. via `JVM_EXTRA_OPTS`, which `conf/cassandra-env.sh:307` appends, or a line
in `conf/jvm-server.options`); a change needs a restart. Not in `cassandra.yaml`, not settable by JMX.
No range check at read time; the only check is `bufferSize >= 8` in the constructor (§A3), and the upper
bound is `Integer.MAX_VALUE` plus `-XX:MaxDirectMemorySize`.

**A2. What it caps.** **Off-heap (direct) memory**: the capacity of the `ByteBuffer` that one
`BufferedDataOutputStreamPlus` built through its one-argument constructor uses to stage writes before handing
them to a `WritableByteChannel`. In production the only class that uses that constructor is
`FileOutputStreamPlus` (`FileOutputStreamPlus.java:45-48`; every other constructor of it delegates there),
i.e. every `File.newOutputStream(...)` (`File.java:762-764`) and `FileWriter` (`FileWriter.java:30,35`).
The quantity governed is `buffer.capacity()` of that stream: it is allocated at exactly the value, staged
bytes never exceed it (the write paths flush when it is full), and it is released on `close()`. Total direct
memory from this source = value × number of such streams open at the same moment. The resource it does
**not** cap: disk (file length is whatever the caller writes) and heap (the buffer is direct).

**A3. Mechanism.**
1. Class init reads the property: `DEFAULT_BUFFER_SIZE = NIO_DATA_OUTPUT_STREAM_PLUS_BUFFER_SIZE.getInt()`
   (`BufferedDataOutputStreamPlus.java:41`). A malformed value fails here (ExceptionInInitializerError on first
   use of the class).
2. `BufferedDataOutputStreamPlus(WritableByteChannel wbc)` calls `this(wbc, DEFAULT_BUFFER_SIZE)`
   (`BufferedDataOutputStreamPlus.java:45-48`).
3. The two-argument constructor allocates **first** and checks afterwards:
   `this(wbc, ByteBuffer.allocateDirect(bufferSize))` at
   [`BufferedDataOutputStreamPlus.java:52`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L52),
   then `Preconditions.checkArgument(bufferSize >= 8, …)` at
   [`BufferedDataOutputStreamPlus.java:54`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L54).
   `allocateDirect` reserves the capacity against `-XX:MaxDirectMemorySize` and zero-fills it (so the pages
   become resident). Outcomes: value < 0 → `IllegalArgumentException` from `allocateDirect`; 0–7 → buffer
   allocated, then `IllegalArgumentException` (the buffer is left to the GC cleaner); value larger than the
   remaining direct-memory headroom → `OutOfMemoryError: Direct buffer memory` from the JDK, which
   `JVMStabilityInspector.inspectThrowable` logs and rethrows (`JVMStabilityInspector.java:108-131`).
4. The check that keeps staged bytes within the capacity: in `write(byte[],int,int)`
   [`if (buffer.hasRemaining())` at `BufferedDataOutputStreamPlus.java:104`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L104)
   copies at most `buffer.remaining()` (line 106), else calls `doFlush` (line 112); in `write(ByteBuffer)` the
   loop condition at `BufferedDataOutputStreamPlus.java:130` does the same; the primitive writes flush first when
   the buffer has no room (`doFlush(1)` at lines 146, 155; `buffer.remaining() < Long.BYTES` at line 169). `doFlush` (`:265-273`) writes the buffer
   to the channel and clears it; it never reallocates. `FileOutputStreamPlus` does not override `doFlush` or
   `allocate`, so its buffer is fixed for its lifetime. (Subclasses that grow their buffer, `DataOutputBuffer`,
   do not use this constructor.)
5. `close()` (`:283-292`) flushes, closes the channel and calls `FileUtils.clean(buffer)` (`:290`;
   `FileUtils.java:362-377` invokes the direct buffer's cleaner), so the memory is returned immediately, not
   at the next GC.

Bypass / overshoot: nothing in this class can exceed the capacity. The caveats are (a) a stream not closed
holds its buffer until the GC collects it; (b) the 0–7 failure path leaks one small buffer to the GC;
(c) the bound is per stream — there is no count limit on streams; concurrency comes from the callers
(flush writers, compactors, streaming, snapshots), each of which holds at most one such stream at a time
on its thread in the paths listed below (every call site is a try-with-resources block).

**A4. Other consumers.** Of the same direct-memory pool (all count toward `MaxDirectMemorySize` and the JDK
`direct` BufferPool MXBean, none governed by this property): `BufferPool` chunk cache / networking macro chunks
(`BufferPool.java:238,460,1095-1101`); `SequentialWriter` buffers when `BufferType.OFF_HEAP` (default is
on-heap, `SequentialWriterOption.java:109`), including `Data.db` writers, which pass their own buffer
(`SequentialWriter.java:171`) and so ignore this property; commit-log segment buffers; the JDK's per-thread
temporary direct buffer cache (`sun.nio.ch.Util`) for heap buffers written to channels. Of native memory but
not the direct pool: Netty pooled buffers, bloom filters and compression offsets in `Memory`/`SafeMemory`,
off-heap memtables. Heap: everything else. `DataOutputBuffer` (heap, `DataOutputBuffer.java:96-106`) and
`AsyncChannelOutputPlus` (passes a null buffer, `AsyncChannelOutputPlus.java:81-83`) are subclasses that do
**not** read the property.

**A5. Evidence beyond the source.**
- `CHANGES.txt:3798` — "Constrain internode message buffer sizes, and improve IO class hierarchy
  (CASSANDRA-8670)", the change that introduced the NIO buffered output stream family:
  https://issues.apache.org/jira/browse/CASSANDRA-8670
- `CHANGES.txt:3570` — "SequentialWriter should extend BufferedDataOutputStreamPlus (CASSANDRA-9500)":
  https://issues.apache.org/jira/browse/CASSANDRA-9500
- Existing tests that use the one-argument constructor with the default size:
  `test/unit/org/apache/cassandra/io/util/DataOutputTest.java:78,365`,
  `test/unit/org/apache/cassandra/net/AsyncStreamingInputPlusTest.java:246`; the size check is tested in
  `test/unit/org/apache/cassandra/io/util/BufferedDataOutputStreamTest.java:108-117`.
- JDK 11 `ByteBuffer.allocateDirect` and `java.lang.management.BufferPoolMXBean`:
  https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html#allocateDirect(int),
  https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/BufferPoolMXBean.html
- Linux `proc(5)`: `VmHWM` in `/proc/<pid>/status`, and writing `5` to `/proc/<pid>/clear_refs` resets the
  peak RSS (Linux ≥ 4.0): https://man7.org/linux/man-pages/man5/proc.5.html
- No documentation of the property itself was found in `doc/`, `conf/`, `NEWS.txt`.

## Config-first: places found

Value flow from the declaration (all paths relative to the source root):

1. `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java:375` — declaration, default 32768.
2. `src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java:41` — read once into
   `DEFAULT_BUFFER_SIZE` (static final; restart to change).
3. `src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java:47` — one-argument constructor
   passes it as `bufferSize`.
4. **`src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java:52` — `allocateDirect(bufferSize)`:
   the off-heap capacity of each stream. The only place that restricts memory. → this case file.**
5. `src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java:54` — lower bound `bufferSize >= 8`
   (checked after allocation); restricts nothing upward.
6. `src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java:104,130` (and the primitive writes'
   `remaining()` checks) — staged bytes ≤ capacity; flush when full. Same buffer as 4.
7. `src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java:290` — `FileUtils.clean` frees it on
   close. Same buffer as 4.
8. `src/java/org/apache/cassandra/io/util/FileOutputStreamPlus.java:47` — the only production subclass using the
   one-argument constructor; reached via `File.java:762-764` (`newOutputStream`) and `FileWriter.java:30,35`.

Call sites that open such a stream (each holds value bytes of direct memory while open; all are the same place 4,
so no separate case files):

- `src/java/org/apache/cassandra/io/sstable/format/FilterComponent.java:76` — `Filter.db` at every SSTable
  finish (`SortedTableWriter.java:454`) and on filter rebuild at load (`BigSSTableReaderLoadingBuilder.java:135`,
  `BtiTableReaderLoadingBuilder.java:108`).
- `src/java/org/apache/cassandra/io/compress/CompressionMetadata.java:423` — `CompressionInfo.db` at every
  compressed SSTable finish (`CompressedSequentialWriter.java:394`).
- `src/java/org/apache/cassandra/io/util/ChecksumWriter.java:93` — `Digest.crc32` at every SSTable finish
  (`CompressedSequentialWriter.java:393`, `ChecksummedSequentialWriter.java:70`; component chosen at
  `DataComponent.java:47-59`).
- `src/java/org/apache/cassandra/io/sstable/format/big/IndexSummaryComponent.java:123` — `Summary.db` (BIG format):
  `BigTableWriter.java:323`, `BigTableReader.java:619` (summary redistribution),
  `BigSSTableReaderLoadingBuilder.java:127`.
- `src/java/org/apache/cassandra/io/sstable/metadata/MetadataSerializer.java:269` — `Statistics.db` rewrite
  (metadata mutation: repaired-at / level reset). The normal `Statistics.db` write uses `SequentialWriter`
  (`StatsComponent.java:114`) and is not affected.
- `src/java/org/apache/cassandra/cache/AutoSavingCache.java:367` — cache-save metadata file.
- `src/java/org/apache/cassandra/utils/JsonUtils.java:177,194` — snapshot `manifest.json`
  (`ColumnFamilyStore.java:2239`) and the data-resurrection heartbeat (`DataResurrectionCheck.java:258`).
- `src/java/org/apache/cassandra/db/ColumnFamilyStore.java:2260` — `schema.cql` in snapshots.
- `src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java:381` — CDC index file (only with CDC on).
- `src/java/org/apache/cassandra/tools/NodeTool.java:307` — nodetool history file (client JVM, not the server).

Not reached by the value: `SequentialWriter` (`SequentialWriter.java:171`), `DataOutputBuffer` and its subclasses
(`DataOutputBuffer.java:96-106`), `AsyncChannelOutputPlus` (`AsyncChannelOutputPlus.java:83`), test-only
subclasses (`test/distributed/.../DirectStreamingConnectionFactory.java`).

Count: 8 places on the value's path, of which 1 restricts memory (place 4); 10 call-site groups.

## B. Verification solution

**B1. Claim under test.** Every `FileOutputStreamPlus` (hence every SSTable `Filter.db` / `CompressionInfo.db` /
`Digest.crc32` / `Summary.db` write) allocates exactly V bytes of direct memory for its lifetime, where V is
`-Dcassandra.nio_data_output_stream_plus_buffer_size`, never more, and returns them on close; so the node's
transient peak direct (and resident) memory during SSTable finishing rises by about V × (streams open at once)
as V is raised, and an allocation that does not fit under `MaxDirectMemorySize` fails with
`OutOfMemoryError: Direct buffer memory`. The claim is wrong if direct/resident peak does not move with V, or
if a stream's buffer differs from V.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11 (`java -version` shows 11.x), Ant ≥ 1.10, ≥ 4 GB free RAM, ≥ 5 GB local disk.
- `WORK=/mydata/$USER-nio-s4` (any local, non-shared disk of known size; `df -h $WORK` first).
- Copy and build outside the shared tree:
  ```
  mkdir -p $WORK && rsync -a /users/jason92/cassandra-5.0.9/ $WORK/src/
  cd $WORK/src && ant jar          # produces build/classes/main and build/lib/jars
  ```
- Probe source in `$WORK/probe/src/org/apache/cassandra/io/util/NioBufProbe.java` (same package as the class
  under test so it can read the protected `buffer` field; split package on the classpath is fine in JDK 11
  classpath mode):
  ```java
  package org.apache.cassandra.io.util;

  import java.lang.management.*;
  import java.lang.reflect.Field;
  import java.nio.ByteBuffer;
  import java.nio.channels.WritableByteChannel;
  import java.util.*;

  public class NioBufProbe
  {
      static BufferPoolMXBean direct()
      {
          for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
              if (b.getName().equals("direct")) return b;
          throw new AssertionError();
      }
      static long cap() { return direct().getTotalCapacity(); }
      static long cnt() { return direct().getCount(); }

      static final class CountingChannel implements WritableByteChannel
      {
          long calls, maxWrite, total; boolean open = true;
          public int write(ByteBuffer src) { int n = src.remaining(); src.position(src.limit());
              calls++; total += n; maxWrite = Math.max(maxWrite, n); return n; }
          public boolean isOpen() { return open; }
          public void close() { open = false; }
      }

      public static void main(String[] a) throws Exception
      {
          String dir = a[0];
          System.out.println("property=" + System.getProperty("cassandra.nio_data_output_stream_plus_buffer_size"));
          Field f = BufferedDataOutputStreamPlus.class.getDeclaredField("DEFAULT_BUFFER_SIZE");
          f.setAccessible(true);
          int v = f.getInt(null);
          System.out.println("DEFAULT_BUFFER_SIZE=" + v);

          // (1) one FileOutputStreamPlus: capacity and direct-pool delta while open, after close
          long c0 = cap(), n0 = cnt();
          FileOutputStreamPlus fos = new File(dir + "/f1").newOutputStream(File.WriteMode.OVERWRITE);
          System.out.printf("open1 capacity=%d isDirect=%b dCap=%d dCount=%d%n",
                            fos.buffer.capacity(), fos.buffer.isDirect(), cap() - c0, cnt() - n0);
          byte[] mib = new byte[1 << 20];
          fos.write(mib); fos.flush(); fos.close();
          System.out.printf("closed1 dCap=%d dCount=%d fileLen=%d%n", cap() - c0, cnt() - n0,
                            new File(dir + "/f1").length());

          // (2) K=4 streams open at once
          List<FileOutputStreamPlus> l = new ArrayList<>();
          for (int i = 0; i < 4; i++) l.add(new File(dir + "/k" + i).newOutputStream(File.WriteMode.OVERWRITE));
          System.out.printf("open4 dCap=%d dCount=%d%n", cap() - c0, cnt() - n0);
          for (FileOutputStreamPlus s : l) s.close();
          System.out.printf("closed4 dCap=%d%n", cap() - c0);

          // (3) staging bound: write W = 3V+123 bytes through the one-arg ctor to a counting sink
          CountingChannel ch = new CountingChannel();
          BufferedDataOutputStreamPlus s = new BufferedDataOutputStreamPlus(ch);
          long w = 3L * v + 123, left = w;
          while (left > 0) { int n = (int) Math.min(left, mib.length); s.write(mib, 0, n); left -= n; }
          s.close();
          System.out.printf("stage W=%d calls=%d maxWrite=%d total=%d%n", w, ch.calls, ch.maxWrite, ch.total);

          // (4) positive control: explicit 4 MiB via the two-arg ctor (ignores the property)
          long c1 = cap();
          BufferedDataOutputStreamPlus pc = new BufferedDataOutputStreamPlus(new CountingChannel(), 4 << 20);
          System.out.printf("ctrl4MiB dCap=%d%n", cap() - c1);
          pc.close();

          // (5) negative control: DataOutputBuffer (heap) with 1 MiB
          long c2 = cap();
          DataOutputBuffer dob = new DataOutputBuffer(1 << 20);
          dob.write(mib);
          System.out.printf("ctrlHeap dCap=%d%n", cap() - c2);
          dob.close();
      }
  }
  ```
- Compile (once):
  ```
  CP="$WORK/src/build/classes/main:$WORK/src/build/lib/jars/*:$WORK/src/lib/*"
  mkdir -p $WORK/probe/classes
  javac -d $WORK/probe/classes -cp "$CP" $WORK/probe/src/org/apache/cassandra/io/util/NioBufProbe.java
  ```
- JVM options for every run: `-Xms1g -Xmx1g -XX:MaxDirectMemorySize=2g` unless the knob row says otherwise.

**B2b. Knobs.** `-Dcassandra.nio_data_output_stream_plus_buffer_size=V` on the probe's `java` command line:

| Arm | V | MaxDirectMemorySize | Why |
|---|---|---|---|
| U0 | unset (default 32768) | 2g | the shipped value |
| U1 | `8` | 2g | smallest accepted value |
| U2 | `1048576` (1 MiB) | 2g | mid |
| U3 | `67108864` (64 MiB) | 2g | large, still 4 × V = 256 MiB fits |
| U4 | `268435456` (256 MiB) | 2g | 4 × V = 1 GiB fits under 2 GiB |
| U5 | `268435456` | `128m` | past the direct-memory limit: allocation must fail |
| U6 | `7` | 2g | below the lower bound |
| U7 | `-1` | 2g | negative |
| U8 | `abc` | 2g | malformed |

**B2c. Workload.** Per arm the probe (1) opens one stream, writes 1 MiB, closes; (2) opens 4 streams at once;
(3) writes W = 3V + 123 bytes through the one-argument constructor into a counting sink (U4: 768 MiB + 123
bytes, CPU only, no disk); (4)/(5) controls. Arithmetic: in (3) the buffer fills ⌊W/V⌋ = 3 times and the
close flushes the remaining 123 bytes, so the sink sees exactly 4 writes for any V ≥ 124 (for U1, V = 8:
W = 147 = 18 full buffers + 3 bytes, so 19 writes of ≤ 8 bytes). File output in (1) is 1 MiB per arm; (2) creates 4 empty files.

**B2d. Observables and instruments.**
- `fos.buffer.capacity()` and `isDirect()` — the operand itself.
- JDK `BufferPoolMXBean` "direct": `TotalCapacity` and `Count` deltas around open / close (exact bytes; the
  JDK updates them synchronously inside `allocateDirect` and the cleaner).
- Counting sink: number of `write` calls and the largest single write (= bytes staged before a flush).
- Exceptions printed for U5–U8.
- Not observable here: resident memory of a real node, concurrency of real callers (cluster tier).

**B2e. Procedure.**
```
mkdir -p $WORK/probe/out
for arm in U0 U1 U2 U3 U4 U6 U7 U8; do
  case $arm in U0) P="";; U1) P=8;; U2) P=1048576;; U3) P=67108864;; U4) P=268435456;; U6) P=7;; U7) P=-1;; U8) P=abc;; esac
  D=""; [ -n "$P" ] && D="-Dcassandra.nio_data_output_stream_plus_buffer_size=$P"
  rm -rf $WORK/probe/run && mkdir -p $WORK/probe/run
  java -Xms1g -Xmx1g -XX:MaxDirectMemorySize=2g $D -cp "$WORK/probe/classes:$CP" \
       org.apache.cassandra.io.util.NioBufProbe $WORK/probe/run > $WORK/probe/out/$arm.txt 2>&1
  echo "$arm exit=$?" >> $WORK/probe/out/exit.txt
done
rm -rf $WORK/probe/run && mkdir -p $WORK/probe/run
java -Xms1g -Xmx1g -XX:MaxDirectMemorySize=128m -Dcassandra.nio_data_output_stream_plus_buffer_size=268435456 \
     -cp "$WORK/probe/classes:$CP" org.apache.cassandra.io.util.NioBufProbe $WORK/probe/run > $WORK/probe/out/U5.txt 2>&1
echo "U5 exit=$?" >> $WORK/probe/out/exit.txt
rm -rf $WORK/probe/run
```
Repeat U0, U3, U4 three times to check the deltas are identical run to run.

**B2f. Predictions** (stated before any run; V as configured):

| Arm | `DEFAULT_BUFFER_SIZE` | open1 capacity / dCap / dCount | closed1 dCap | open4 dCap | stage calls / maxWrite | ctrl4MiB dCap | ctrlHeap dCap |
|---|---|---|---|---|---|---|---|
| U0 | 32768 | 32768 / 32768 / 1, direct | 0 | 131072 | 4 / 32768 | 4194304 | 0 |
| U1 | 8 | 8 / 8 / 1 | 0 | 32 | 19 / 8 (W = 147: 18 full + 1 of 3) | 4194304 | 0 |
| U2 | 1048576 | 1048576 / 1048576 / 1 | 0 | 4194304 | 4 / 1048576 | 4194304 | 0 |
| U3 | 67108864 | 67108864 / 67108864 / 1 | 0 | 268435456 | 4 / 67108864 | 4194304 | 0 |
| U4 | 268435456 | 268435456 / 268435456 / 1 | 0 | 1073741824 | 4 / 268435456 | 4194304 | 0 |
| U5 | 268435456 | first open throws `java.lang.OutOfMemoryError: Direct buffer memory` (JDK 11 text), stack through `BufferedDataOutputStreamPlus.<init>` ← `FileOutputStreamPlus.<init>`; exit ≠ 0 | — | — | — | — | — |
| U6 | 7 | first open throws `IllegalArgumentException: Buffer size must be large enough to accommodate a long/double` | — | — | — | — | — |
| U7 | -1 | first open throws `IllegalArgumentException` from `ByteBuffer.allocateDirect` ("capacity < 0") | — | — | — | — | — |
| U8 | — | reading `DEFAULT_BUFFER_SIZE` throws `ExceptionInInitializerError` caused by `ConfigurationException: Invalid value for system property: expected integer value but got 'abc'` | — | — | — | — | — |

(U1 arithmetic: W = 3·8 + 123 = 147 bytes = 18 full buffers of 8 + 3 bytes at close = 19 writes.)
Deltas are exact (± 0 bytes) because nothing else in the probe JVM allocates direct buffers between the two
reads; a non-zero baseline drift from JDK-internal allocations would show up in U0's `closed1 dCap` and is
subtracted if present. The file `f1` is 1048576 bytes in every successful arm.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| capacity = dCap = V, closed dCap = 0, open4 = 4V, maxWrite = V, for U0–U4 | claim confirmed at the unit level: per-stream direct memory follows V exactly and is returned on close |
| capacity ≠ V, or dCap ≠ capacity, or `isDirect` false | **claim wrong**: the property does not size (or does not size direct) memory as traced |
| closed1 dCap = V (not 0) | buffer not released on close (cleaner not effective); the bound still holds per stream but memory lingers — revise A3 step 5 |
| maxWrite > V | staging exceeds the buffer: the capacity is not the bound on staged bytes — **claim wrong** in A3 step 4 |
| U5 does not throw | the allocation is not charged to `MaxDirectMemorySize` — **claim wrong** about the resource |
| ctrl4MiB dCap ≠ 4194304 | instrument broken; discard the run |
| ctrlHeap dCap ≠ 0 | something else allocates direct memory in the probe; deltas are contaminated |

**B2h. Controls.** Positive control (4): an explicit 4 MiB direct buffer via the two-argument constructor must
show dCap = 4194304 whatever V is — shows the instrument sees direct allocations and that only the one-argument
path reads the property. Negative control (5): `DataOutputBuffer` (heap) must show 0. Reading
`DEFAULT_BUFFER_SIZE` by reflection rules out a property-name or parsing mismatch. Repeats of U0/U3/U4 rule out
JIT/GC timing effects (there should be none: the counters are exact).

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node, JDK 11, ≥ 8 GB RAM free, Python 3 for `cqlsh`, local disk `$WORK` (≥ 10 GB free).
  Reuse `$WORK/src` from B2a (already built with `ant jar`).
- Make a node directory and point the copied `conf/cassandra.yaml` at it (edit `$WORK/src/conf/cassandra.yaml`,
  the private copy):
  ```
  mkdir -p $WORK/node
  ```
  and set in `$WORK/src/conf/cassandra.yaml` (edit by hand; `$WORK` written out as the literal path):
  `data_file_directories: [$WORK/node/data]`, `commitlog_directory: $WORK/node/commitlog`,
  `saved_caches_directory: $WORK/node/saved_caches`, `hints_directory: $WORK/node/hints`,
  `cdc_raw_directory: $WORK/node/cdc_raw`, `listen_address: 127.0.0.1`, `rpc_address: 127.0.0.1`,
  `seeds: "127.0.0.1:7000"`. Leave `cdc_enabled: false`, `sstable.selected_format` unset (BIG).
  Check ports 7000, 9042, 7199 are free (`ss -ltn | grep -E ':(7000|9042|7199) '`); if not, change
  `storage_port`, `native_transport_port` and `JMX_PORT` in `conf/cassandra-env.sh` and use them below.
- Environment for every start (heap fixed and pre-touched, so heap does not move RSS during the workload;
  `-XX:+AlwaysPreTouch` is already in `conf/jvm-server.options:128`, G1 in `conf/jvm11-server.options:63`):
  ```
  export CASSANDRA_LOG_DIR=$WORK/node/logs MAX_HEAP_SIZE=2G MAX_DIRECT_MEMORY_SIZE=2G
  export JVM_EXTRA_OPTS="-Dcassandra.nio_data_output_stream_plus_buffer_size=$V"   # omit for the default arm
  ```
- JMX poller `$WORK/probe/src/JmxDirectPoller.java` (default package):
  ```java
  import javax.management.*; import javax.management.remote.*;
  import java.nio.file.*; import java.util.*;
  public class JmxDirectPoller {
    public static void main(String[] a) throws Exception {
      JMXConnector c = JMXConnectorFactory.connect(new JMXServiceURL(
          "service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi"));
      MBeanServerConnection m = c.getMBeanServerConnection();
      ObjectName on = new ObjectName("java.nio:type=BufferPool,name=direct");
      Path stop = Paths.get(a[1]); long t0 = System.currentTimeMillis();
      long[] base = new long[200]; int nb = 0; long maxCap = 0, maxCnt = 0, samples = 0;
      while (!Files.exists(stop)) {
        AttributeList l = m.getAttributes(on, new String[]{"TotalCapacity","Count"});
        long cap = (Long)((Attribute)l.get(0)).getValue(), cnt = (Long)((Attribute)l.get(1)).getValue();
        if (nb < base.length) base[nb++] = cap;
        if (cap > maxCap) { maxCap = cap; System.out.println((System.currentTimeMillis()-t0) + " newmax cap=" + cap + " count=" + cnt); }
        maxCnt = Math.max(maxCnt, cnt); samples++; Thread.sleep(2);
      }
      Arrays.sort(base, 0, nb);
      System.out.println("baselineMedianCap=" + base[nb/2] + " maxCap=" + maxCap + " maxCount=" + maxCnt + " samples=" + samples);
      c.close();
    }
  }
  ```
  Compile: `javac -d $WORK/probe/classes $WORK/probe/src/JmxDirectPoller.java`.
- Workload file `$WORK/probe/ins.cql`: 500 `INSERT INTO ks1.t1 (k, v) VALUES (<i>, '<1000 random chars>');`
  lines, generated once:
  ```
  python3 -c "import random,string
  for i in range(500): print(\"INSERT INTO ks1.t1 (k,v) VALUES (%d,'%s');\"%(i,''.join(random.choices(string.ascii_letters,k=1000))))" > $WORK/probe/ins.cql
  ```

**B3b. Knobs.** `JVM_EXTRA_OPTS="-Dcassandra.nio_data_output_stream_plus_buffer_size=V"` at node start:

| Arm | V | `MAX_DIRECT_MEMORY_SIZE` | Why |
|---|---|---|---|
| C0 | unset (32768) | 2G | baseline / control |
| C1 | 67108864 (64 MiB) | 2G | clearly above noise of other off-heap users |
| C2 | 268435456 (256 MiB) | 2G | 4× C1, linearity |
| C3 | 1073741824 (1 GiB) | 512M | past the direct-memory limit: SSTable finishing must fail |

Each arm starts from an empty `$WORK/node` (`rm -rf $WORK/node/{data,commitlog,saved_caches,hints,cdc_raw}`).

**B3c. Workload.** Schema (once per arm, after start):
```
bin/cqlsh 127.0.0.1 -e "CREATE KEYSPACE ks1 WITH replication={'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE ks1.t1 (k int PRIMARY KEY, v text) WITH compaction={'class':'SizeTieredCompactionStrategy'};
CREATE TABLE ks1.t2 (k int PRIMARY KEY, v text) WITH compaction={'class':'SizeTieredCompactionStrategy'};"
bin/nodetool disableautocompaction ks1
```
Phase S (serial): 30 iterations of `cqlsh -f ins.cql` (≈ 0.5 MB into `t1`) then `nodetool flush ks1 t1`.
Each flush finishes one compressed BIG SSTable, which opens, one after another, `Digest.crc32`,
`CompressionInfo.db`, `Filter.db`, `Summary.db` through `FileOutputStreamPlus` (§Places): 4 × 30 = 120
allocations of V, at most one open at a time on the flush thread. Phase P (parallel): 10 iterations of
inserting the same 500 rows into both `t1` and `t2` (`sed 's/ks1.t1/ks1.t2/' ins.cql > ins2.cql`) then
`nodetool flush ks1` (both tables flush on the two default flush writers, `conf/cassandra.yaml:899-912`), so
up to 2 streams can be open at once. Duration ≈ 5–10 min per arm. Arithmetic: with V = 256 MiB each allocation
zero-fills 256 MiB (resident), so one open stream adds 256 MiB to RSS for its lifetime (ms to tens of ms,
including the `fsync`), which `VmHWM` records regardless of sampling.

**B3d. Observables and instruments.**
- Peak resident set: `VmHWM` from `/proc/$PID/status`, reset to current RSS before each phase with
  `echo 5 > /proc/$PID/clear_refs` (owner may write it). ΔHWM = `VmHWM` after phase − `VmRSS` at reset.
- Direct-pool peak: `JmxDirectPoller` at 2 ms sampling: `maxCap − baselineMedianCap` and `maxCount`.
  Short-lived buffers can be missed by sampling (a 32 KiB buffer lives < 1 ms); `VmHWM` is the
  primary instrument, the poller is supporting.
- Disk: `du -sb $WORK/node/data/ks1` and `ls $WORK/node/data/ks1/t1-*/ | grep -c Data.db` after phase S
  (expect 30).
- Errors: `grep -n "OutOfMemoryError\|Direct buffer memory\|FSWriteError" $WORK/node/logs/system.log`.
- Not directly observable: which call site a given peak comes from (the stack is visible only in a failure,
  arm C3); off-heap users outside the direct pool (Netty, `Memory`) appear only in RSS.

**B3e. Procedure** (per arm C0, C1, C2; C3 below):
```
cd $WORK/src
rm -rf $WORK/node/{data,commitlog,saved_caches,hints,cdc_raw,logs}; mkdir -p $WORK/node/logs
export CASSANDRA_LOG_DIR=$WORK/node/logs MAX_HEAP_SIZE=2G MAX_DIRECT_MEMORY_SIZE=2G
export JVM_EXTRA_OPTS="-Dcassandra.nio_data_output_stream_plus_buffer_size=$V"   # unset for C0
bin/cassandra -p $WORK/node/cass.pid > $WORK/node/logs/start.out 2>&1
until bin/nodetool status 2>/dev/null | grep -q '^UN'; do sleep 5; done
PID=$(cat $WORK/node/cass.pid)
ps -o args= -p $PID | tr ' ' '\n' | grep nio_data_output    # confirm the -D reached the JVM
# schema + disableautocompaction (B3c); then settle
sleep 60
rm -f $WORK/stop; java -cp $WORK/probe/classes JmxDirectPoller 7199 $WORK/stop > $WORK/probe/out/poll-$ARM-S.txt &
POLL=$!; sleep 3
echo 5 > /proc/$PID/clear_refs; grep -E 'VmRSS|VmHWM' /proc/$PID/status > $WORK/probe/out/hwm-$ARM-S0.txt
for i in $(seq 1 30); do bin/cqlsh 127.0.0.1 -f $WORK/probe/ins.cql; bin/nodetool flush ks1 t1; done
grep -E 'VmRSS|VmHWM' /proc/$PID/status > $WORK/probe/out/hwm-$ARM-S1.txt
touch $WORK/stop; wait $POLL
# phase P: same with poll-$ARM-P / hwm-$ARM-P*, 10 iterations of: cqlsh -f ins.cql; cqlsh -f ins2.cql; nodetool flush ks1
du -sb $WORK/node/data/ks1 > $WORK/probe/out/du-$ARM.txt
ls $WORK/node/data/ks1/t1-*/ | grep -c Data.db >> $WORK/probe/out/du-$ARM.txt
grep -n "OutOfMemoryError\|Direct buffer memory\|FSWriteError" $WORK/node/logs/system.log > $WORK/probe/out/err-$ARM.txt
bin/nodetool stopdaemon || kill $PID; while kill -0 $PID 2>/dev/null; do sleep 2; done
```
Run C0 twice more at the end (C0b, C0c) to measure run-to-run noise of ΔHWM.

C3: same start with `MAX_DIRECT_MEMORY_SIZE=512M` and V = 1073741824. Record whether startup completes
(a system-table SSTable finish during startup can already trip it); if it does, run one iteration of phase S
and grep the log. Then stop the node (`kill $PID`; if the JVM is wedged, `kill -9 $PID`).

**B3f. Predictions** (before any run). Let N₀ = the largest ΔHWM among C0, C0b, C0c (noise from other off-heap
users at the 32 KiB default; expected tens of MiB at most).

| Arm | ΔHWM phase S | poller `maxCap − baseline` phase S | ΔHWM / poller phase P | Data.db count, `du` | log |
|---|---|---|---|---|---|
| C0 | N₀ (reference) | < 1 MiB attributable (32 KiB buffers mostly missed) | ≈ N₀ | 30; D₀ | no OOM |
| C1 | ≥ 64 MiB and ≤ N₀ + 2 × 64 MiB | 64 MiB ≤ x ≤ 128 MiB if a buffer is caught; Count rises by ≥ 1 at the peak | between 64 and 128 MiB above C0 (128 if two flushes overlap) | 30; D₀ ± 2 % | no OOM |
| C2 | ≥ 256 MiB and ≤ N₀ + 2 × 256 MiB | 256 MiB ≤ x ≤ 512 MiB | between 256 and 512 MiB above C0 | 30; D₀ ± 2 % | no OOM |
| C3 | — | — | — | the SSTable whose finish failed has `Data.db` but no `Filter.db`/`TOC.txt` | `java.lang.OutOfMemoryError: Direct buffer memory` with `BufferedDataOutputStreamPlus.<init>` / `FileOutputStreamPlus.<init>` in the stack, logged by `JVMStabilityInspector` ("OutOfMemory error letting the JVM handle the error") |

Relations that must hold: ΔHWM(C2) − ΔHWM(C0) ≈ 4 × (ΔHWM(C1) − ΔHWM(C0)) within ± 30 %; disk use does not
depend on V (± 2 %, write timestamps differ).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| ΔHWM and poller peak rise by ≈ V (C1, C2) above C0, ≈ linear in V; disk unchanged; C3 fails with direct-buffer OOM | claim confirmed: the property sets real per-stream off-heap memory on the node's SSTable-finishing path |
| ΔHWM(C2) − ΔHWM(C0) within noise (< N₀) and poller never above baseline + 32 MiB | **claim wrong**: the property does not govern node memory on this path (e.g. a different writer is used) |
| ΔHWM above C0 by ≫ 2V | more streams are open at once than traced (concurrency or a leak); revise A3 caveat (c) |
| C3 runs 30 flushes without OOM | **claim wrong**: the allocation is not charged to direct memory or is not V |
| disk use differs by > 2 % with V | the buffer size affects what is written — contradicts A2 |
| C0 noise N₀ ≥ 128 MiB | the measurement cannot separate C1; rely on C2 and C3 |

**B3h. Controls.** C0 (and its repeats) is the same workload with the default V, isolating V's contribution.
Pre-touched fixed heap (`-Xms = -Xmx`, `AlwaysPreTouch`) removes heap growth from RSS. Autocompaction
disabled, no reads, one data directory, CDC off: removes compaction, chunk-cache growth and CDC index writes.
Confirming the `-D` on the JVM command line (`ps`) rules out a value that never reached the JVM. C3 is the
positive control for the resource: `MaxDirectMemorySize`, a cap known to bind direct allocations, is shown to
bind exactly this allocation, which ties the observed peaks to the direct buffer and not to some other
allocator. Equal `Data.db` counts across arms show every arm did the same number of SSTable finishes.

**B4. Risks and cleanup.**
- Disk: everything under `$WORK` on local disk (~ 3 GB build + < 100 MB data per arm); `df -h $WORK` before.
  Nothing in the shared source tree or shared storage.
- Memory: C2 peaks at heap 2 GiB + up to 512 MiB of these buffers + other off-heap; keep ≥ 8 GB free. U4 needs
  ~ 2.2 GB. C3 may leave the JVM in an OOM state; kill it.
- Processes: after each arm `nodetool stopdaemon` or `kill $(cat $WORK/node/cass.pid)`; kill the poller
  (`touch $WORK/stop`). Final check: `pgrep -u $USER -af 'CassandraDaemon|JmxDirectPoller|NioBufProbe'` prints
  nothing; `ss -ltn | grep -E ':(7000|9042|7199) '` empty.
- Cleanup: `rm -rf $WORK/node $WORK/probe/run $WORK/stop`; keep `$WORK/probe/out` (readings) until filed;
  remove `$WORK` entirely when stage 4 is done.

## C. Sources read

src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (375, 719, 794-800, 964-983)
src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java
src/java/org/apache/cassandra/io/util/FileOutputStreamPlus.java
src/java/org/apache/cassandra/io/util/File.java (747-765)
src/java/org/apache/cassandra/io/util/FileWriter.java
src/java/org/apache/cassandra/io/util/FileUtils.java (71-117, 362-377)
src/java/org/apache/cassandra/io/util/DataOutputBuffer.java (constructors)
src/java/org/apache/cassandra/io/util/DataOutputBufferFixed.java (constructors)
src/java/org/apache/cassandra/io/util/SequentialWriter.java (37, 171)
src/java/org/apache/cassandra/io/util/SequentialWriterOption.java
src/java/org/apache/cassandra/io/util/ChecksumWriter.java (85-100)
src/java/org/apache/cassandra/io/util/ChecksummedSequentialWriter.java (70)
src/java/org/apache/cassandra/net/AsyncChannelOutputPlus.java (45, 81-83)
src/java/org/apache/cassandra/net/AsyncMessageOutputPlus.java (68)
src/java/org/apache/cassandra/net/AsyncStreamingOutputPlus.java (65)
src/java/org/apache/cassandra/io/compress/CompressionMetadata.java (375-430)
src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java (80-106, 388-395)
src/java/org/apache/cassandra/io/sstable/format/FilterComponent.java (65-85)
src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java (440-460)
src/java/org/apache/cassandra/io/sstable/format/SSTableWriter.java (375-395)
src/java/org/apache/cassandra/io/sstable/format/StatsComponent.java (111-123)
src/java/org/apache/cassandra/io/sstable/format/DataComponent.java (40-62)
src/java/org/apache/cassandra/io/sstable/format/SSTableFormat.java (166, 182)
src/java/org/apache/cassandra/io/sstable/format/TOCComponent.java (100-106)
src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java (318-324)
src/java/org/apache/cassandra/io/sstable/format/big/BigFormat.java (119)
src/java/org/apache/cassandra/io/sstable/format/big/IndexSummaryComponent.java (115-130)
src/java/org/apache/cassandra/io/sstable/metadata/MetadataSerializer.java (255-275)
src/java/org/apache/cassandra/cache/AutoSavingCache.java (355-380)
src/java/org/apache/cassandra/utils/JsonUtils.java (175-200)
src/java/org/apache/cassandra/db/ColumnFamilyStore.java (2239, 2255-2262)
src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java (378-383)
src/java/org/apache/cassandra/utils/JVMStabilityInspector.java (87-135)
src/java/org/apache/cassandra/utils/memory/BufferPool.java (136, 238, 385, 460, 1095-1101)
src/java/org/apache/cassandra/tools/NodeTool.java (307)
test/unit/org/apache/cassandra/io/util/DataOutputTest.java (grep of uses)
test/unit/org/apache/cassandra/io/util/BufferedDataOutputStreamTest.java (grep of uses)
test/unit/org/apache/cassandra/net/AsyncStreamingInputPlusTest.java (grep of uses)
conf/cassandra-env.sh (17-66, 85-162, 307)
conf/jvm-server.options (123-174, grep)
conf/jvm11-server.options (grep)
conf/cassandra.yaml (899-912, 1172, 1225-1236; grep)
build.xml (94, 1192, 1382; grep)
CHANGES.txt (3570, 3798)
https://issues.apache.org/jira/browse/CASSANDRA-8670 (cited, not fetched)
https://issues.apache.org/jira/browse/CASSANDRA-9500 (cited, not fetched)
https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html (cited, not fetched)
https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/BufferPoolMXBean.html (cited, not fetched)
https://man7.org/linux/man-pages/man5/proc.5.html (cited, not fetched)

## D. Stage-4 feedback

none yet
