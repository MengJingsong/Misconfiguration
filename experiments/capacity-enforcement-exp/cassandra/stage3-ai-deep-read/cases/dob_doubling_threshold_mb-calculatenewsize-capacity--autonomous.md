# cassandra.DOB_DOUBLING_THRESHOLD_MB — verification solution  <!-- file: cases/dob_doubling_threshold_mb-calculatenewsize-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (capacity-set unit: the growth-policy threshold field of `DataOutputBuffer`), **linked**: [`DataOutputBuffer.java:48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L48) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-opus-5-5, Claude Code 2.1.330, 2026-11-24 (autonomous) |
| Estimate | `negative`. The value only chooses the growth factor (x2 at or below the threshold, x1.5 above it) for a buffer that has to grow anyway. It never refuses, trims or bounds an allocation, so a buffer always reaches at least the bytes written to it, whatever the threshold. |
| Ground | `calculateNewSize` ([`DataOutputBuffer.java:166`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L166)) uses the threshold only to pick `max(capacity*3/2, capacity+count)` or `max(capacity*2, capacity+count)`. Both are always larger than the current capacity and at least `capacity+count`. Nothing compares usage with the threshold to stop growth. The only hard limit is `MAX_ARRAY_SIZE` (2^31-9), which does not depend on the knob. The final capacity is not even monotone in the knob. For the same 200-row page the default 64 gives about 216 MiB, 128 gives about 288 MiB and 1024 gives about 256 MiB (B2f/B3f). The knob bounds the slack ratio of large buffers, not the memory they use. |

## A. Constraint trace

**A1. The constraint.**
- **Name:** JVM system property `cassandra.DOB_DOUBLING_THRESHOLD_MB` (enum constant `DOB_DOUBLING_THRESHOLD_MB`).
- **Kind:** JVM system property, read once into a `static final` constant.
- **First declared:** [`CassandraRelevantProperties.java:203`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L203): `DOB_DOUBLING_THRESHOLD_MB("cassandra.DOB_DOUBLING_THRESHOLD_MB", "64")`.
- **Read:** read once, at class initialisation of `DataOutputBuffer`, into `static final long DOUBLING_THRESHOLD` (`DataOutputBuffer.java:48`) through `getLong()` (`CassandraRelevantProperties.java:806-812`: `System.getProperty(key)`, falling back to the default string).
- **Unit:** MiB. It is multiplied by `1024L*1024L` at the use site (`DataOutputBuffer.java:166`).
- **Default:** the literal `"64"`, so 64 MiB = 67,108,864 bytes. Nothing derives it from heap, RAM or the yaml.
- **How it is set:** only as `-Dcassandra.DOB_DOUBLING_THRESHOLD_MB=<n>` on the JVM command line (for a node, `JVM_EXTRA_OPTS`, appended at `conf/cassandra-env.sh:307`, or a line in `conf/jvm-server.options`). It has no yaml key and no JMX or nodetool setter.
- **Restart:** a change needs a JVM restart, because the field is `static final` and is read once.
- **Edge cases:** the property does not appear in `conf/` or `doc/` (grep found nothing). A value of 0 or a negative value makes every resize x1.5. A value above about 8.8e12 overflows the `long` product into a negative number, which has the same effect.

**A2. What it caps.**
- **Resource:** the capacity of growable `DataOutputBuffer` instances.
  - Heap `byte[]` for `new DataOutputBuffer()`: `BufferedDataOutputStreamPlus.allocate`, `BufferedDataOutputStreamPlus.java:75-78`.
  - Direct (off-heap) memory for the thread-local `scratchBuffer` by default: `DataOutputBuffer.java:55,84-89`; `cassandra.dob.allocate_type`, `CassandraRelevantProperties.java:183`.
  - Native memory for `SafeMemoryWriter` (`SafeMemoryWriter.java:44-48`).
- **Quantity compared:** the buffer's **current capacity** in bytes (`capacity()`, `DataOutputBuffer.java:143-146`, overridden by `SafeMemoryWriter.java:89-92`). It is compared with `1024*1024*DOUBLING_THRESHOLD` (`DataOutputBuffer.java:166`).
- **Effect of the comparison:** it selects the growth multiplier. It does not cap anything. The memory used is the new capacity, which is at least `capacity + count` (the bytes still to be written).

**A3. Mechanism.**
1. Writes go through `BufferedDataOutputStreamPlus`. When the buffer is full, `write(byte[],..)` calls `doFlush(len - copied)` (`BufferedDataOutputStreamPlus.java:102-113`). `write(ByteBuffer)` calls `doFlush(src.limit() - srcPos)` (`:130-136`). Single-byte writes call `doFlush(1)` (`:145-146`).
2. `DataOutputBuffer.doFlush(count)` calls `expandToFit(count)` (`DataOutputBuffer.java:136-139`).
3. `expandToFit` returns if `count <= 0`. Otherwise it allocates `checkedArraySizeCast(calculateNewSize(count))`, copies the old contents and calls `setBuffer` (`DataOutputBuffer.java:174-182`). `setBuffer` frees the old buffer only when it is direct (`FileUtils.clean`, `FileUtils.java:362-365`). For heap buffers, old and new arrays are both live during the copy, so the transient peak is old plus new capacity.
4. `calculateNewSize(count)` (`DataOutputBuffer.java:158-172`) computes `newSize = capacity + count`, then **the check**, [`DataOutputBuffer.java:166`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L166) (`if (capacity > 1024L * 1024L * DOUBLING_THRESHOLD)`):
   - **true** (capacity strictly above T MiB): `newSize = max(capacity*3/2, capacity+count)` (`:167`).
   - **false** (capacity at or below T MiB): `newSize = max(capacity*2, capacity+count)` (`:169`).
   - Then `validateReallocation(newSize)` (`:149-155`) saturates to `MAX_ARRAY_SIZE = Integer.MAX_VALUE-8` (`:118,121-125`). It throws `BufferOverflowException` only if the saturated size is not larger than the current capacity, which happens near 2 GiB and does not depend on T.
5. **What each outcome does at the limit.** Both branches grow the buffer. Neither refuses, waits, spills or trims. "Reaching the limit" only changes the next growth step from x2 to x1.5. The comparison is strict (`>`), so a buffer at exactly T MiB still doubles. That is why, with 64 KiB writes, T=64 gives 64 → 128 → 192 → 288 MiB (B2f).
6. **Overshoot.**
   - Below the threshold the capacity can be up to about 2x the bytes held. Above it, up to about 1.5x.
   - The last resize can take the capacity from just under S to about 1.5S or 2S. If the threshold is crossed just before that, 1.5S can exceed the 2S-path value for the same S, which is why the result is non-monotone.
   - `buffer()` returns a duplicate that shares the whole backing array (`DataOutputBuffer.java:227-245`). A caller that keeps the result therefore keeps the full capacity, not just the bytes written.
7. **Paths that bypass or change it.**
   - `SafeMemoryWriter` (`SafeMemoryWriter.java:44-48,101-107`) uses the same `calculateNewSize` but overrides `validateReallocation`, so it has no `MAX_ARRAY_SIZE` saturation. `trim()` (`:69-72`) shrinks it back to its length afterwards.
   - `DataOutputBufferFixed` (`DataOutputBufferFixed.java:50-65`) never grows: it throws `BufferOverflowException`.
   - Buffers created with an explicit large initial size skip the growth steps, for example `IndexSummaryBuilder.java:126-127`.
   - The thread-local `scratchBuffer.close()` (`DataOutputBuffer.java:71-81`) shrinks a buffer back to 128 bytes when its capacity is above `cassandra.dob_max_recycle_bytes` (1 MiB default, `CassandraRelevantProperties.java:204`). That is a separate constraint, and it is the one that actually bounds the memory a thread retains between uses.

**A4. Other consumers.**
What else uses the same heap or off-heap memory outside this knob's control:
- **The caller's data size.** It decides how far each buffer grows. For a local read this is the page: `ReadResponse.java:197-203`, rows-per-page from the client fetch size or `SelectStatement.DEFAULT_PAGE_SIZE` = 10000 for aggregates (`SelectStatement.java:114,899-902`).
- **Other heap consumers:**
  - memtables (`memtable_allocation_type: heap_buffers`, `conf/cassandra.yaml:825`)
  - deserialisation of the response at the coordinator
  - encoding the CQL result
  - netty buffers
  - the commit log
  - hints buffers (`HintsBuffer`)
  - the sstable writers' scratch buffers
  - index summaries (`SafeMemoryWriter`)
  - caches
- **Accounting:** none. `DataOutputBuffer` memory is not counted against any budget. In 5.0.9, the read-size thresholds (`local_read_size_*`) are disabled by default.
- **Number of users:** 13 source files create `new DataOutputBuffer(...)` and 6 call sites use `scratchBuffer.get()` (grep in `src/java`).

**A5. Evidence beyond the source.**
- `CHANGES.txt:3315` (and `:3395`): "Fix IllegalArgumentException in DataOutputBuffer.reallocate for large buffers (CASSANDRA-10592)". This is the change family for large-buffer growth, and the 1.5x step is consistent with it. I did not open the JIRA ticket, and no claim here depends on it.
- `CHANGES.txt:601` (CASSANDRA-16471, on-heap/off-heap choice for the scratch buffer).
- Test `test/unit/org/apache/cassandra/io/util/SafeMemoryWriterTest.java:62-81`. It uses `DataOutputBuffer.DOUBLING_THRESHOLD` only to choose a starting size so that the x1.5 path is exercised past 2 GiB. It treats the threshold as a growth-rate switch and asserts no bound.
- Docs: none mention the property.
- JDK: JFR event `jdk.ObjectAllocationOutsideTLAB` and the `jdk.jfr.consumer.RecordingFile` API (JDK 11, https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html), used in B3.

## B. Verification solution

**B1. Claim under test.** For a growable `DataOutputBuffer` that receives S bytes, the final capacity C (the memory actually allocated) satisfies C ≥ S for every value T of `cassandra.DOB_DOUBLING_THRESHOLD_MB`. T only sets the ratio between consecutive capacities: exactly 2.0 (or `cap+count`) while the previous capacity is ≤ T MiB, and floor x1.5 above it. So usage does **not** follow T: it is not capped at or near T MiB, and it is not monotone in T. On a node, the heap `byte[]` that `ReadResponse.LocalDataResponse.build` allocates for a page of about 200 MiB is ≥ 200 MiB at every T. Halving the page, which is a limit known to bind this buffer, roughly halves it. The claim is **refuted** if any T gives C < S without an exception, if the largest allocation stays at or below about T MiB (or a fixed multiple of it) while S is larger, or if C decreases monotonically as T decreases, in proportion to T.

### B2. Unit tier

**B2a. Environment and build.**
- **Hardware and JDK:** Linux, JDK 11 (`java -version` shows 11.x), Ant 1.10+, at least 4 GB free RAM.
- **Copy and build:** set `RUN=<local, non-shared directory with ≥ 10 GB free>` and check it with `df -h $RUN`. Then run `rsync -a <pristine cassandra-5.0.9 tree>/ $RUN/cassandra/` and `cd $RUN/cassandra && ant jar`. Never build in the shared tree.
- **Probe location:** the probe source lives in `$RUN/probe/src/org/apache/cassandra/io/util/DobGrowthProbe.java`, outside the Cassandra tree. It goes in that package so it can call the package-private `capacity()` and `expandToFit`.
- **JVM options:** `-Xmx2g -Xms2g`, plus `-Dcassandra.DOB_DOUBLING_THRESHOLD_MB=<T>` when T is set. Use a fresh JVM per T, because the field is `static final`.

```java
package org.apache.cassandra.io.util;

import java.nio.BufferOverflowException;
import java.nio.ByteBuffer;

public class DobGrowthProbe
{
    static long prev = -1;
    // usage: DobGrowthProbe <mode: bytes|rows|fixed> <n: MiB for bytes/fixed, row count for rows>
    public static void main(String[] a) throws Exception
    {
        String mode = a[0];
        long n = Long.parseLong(a[1]);
        System.out.println("DOUBLING_THRESHOLD_MB=" + DataOutputBuffer.DOUBLING_THRESHOLD);
        DataOutputBuffer dob;
        if (mode.equals("fixed"))
            dob = new DataOutputBufferFixed(1 << 20);
        else
            dob = new DataOutputBuffer()
            {
                @Override
                protected void expandToFit(long count)
                {
                    long before = capacity();
                    super.expandToFit(count);
                    long after = capacity();
                    System.out.printf("EXPAND count=%d %d -> %d ratio=%.4f transient=%d%n",
                                      count, before, after, (double) after / before, before + after);
                }
            };
        System.out.println("INITIAL capacity=" + dob.capacity());
        try
        {
            if (mode.equals("rows"))
            {
                dob.write(new byte[40]);                        // "partition header"
                byte[] rowHdr = new byte[12];
                ByteBuffer value = ByteBuffer.allocate(1 << 20); // 1 MiB cell value
                for (long i = 0; i < n; i++)
                {
                    dob.write(rowHdr);
                    dob.write(value.duplicate());
                }
            }
            else
            {
                byte[] chunk = new byte[65536];
                for (long w = 0; w < (n << 20); w += chunk.length)
                    dob.write(chunk);
            }
        }
        catch (BufferOverflowException e)
        {
            System.out.println("OVERFLOW position=" + dob.position() + " capacity=" + dob.capacity());
        }
        System.out.printf("FINAL written=%d capacity=%d ratio=%.4f%n",
                          dob.position(), dob.capacity(), (double) dob.capacity() / Math.max(1, dob.position()));
    }
}
```

**B2b. Knobs.**
- **Values of `cassandra.DOB_DOUBLING_THRESHOLD_MB`:**

  | Value | Why |
  |---|---|
  | *unset* | The default. It must equal 64. |
  | 0 | Always x1.5. |
  | 16 | Crossed early. |
  | 64 | The default, set explicitly. |
  | 128 | Crossed just before the last resize. |
  | 1024 | Never crossed for a 200 MiB payload, so always x2. |

  The values bracket the 64 MiB default and place the crossing before, at, and after the last resize for a payload of about 200 MiB.
- **How it is set:** with `-D` on the probe's java command line.
- **Secondary variable (positive control):** the payload S, 100 MiB or 200 MiB (200 or 100 rows), which is the quantity known to drive the buffer.

**B2c. Workload.**
- **Mode `bytes`:** writes S = n MiB in 64 KiB `byte[]` chunks.
- **Mode `rows`:** imitates an intra-node read response, which is the B3 workload: 40 header bytes, then n rows of 12 header bytes plus a 1 MiB value written as a `ByteBuffer`.
- **Arithmetic:** S = 200 MiB = 209,715,200 bytes (`bytes 200`), or 209,717,640 bytes (`rows 200`). Both exceed every T tested except 1024, so the T crossing happens during the run. For T=1024 the buffer is never above T, which is the always-x2 reference.
- **Memory:** the peak live heap is about 510 MB (old plus new array), which fits in `-Xmx2g`.
- **Mode `fixed`:** writes the same 200 MiB into a `DataOutputBufferFixed(1 MiB)`. This is the positive control, a cap known to bind.

**B2d. Observables and instruments.**
- **Measured:** each line of the probe's stdout.
  - `EXPAND`: count, old capacity, new capacity, ratio, and transient old+new. This is sampled at every resize, so the record is complete.
  - `FINAL`: bytes written, final capacity, capacity/written.
  - `DOUBLING_THRESHOLD_MB`: the value the class actually read.
- **Not observable here:** GC timing and when garbage is actually reclaimed. Capacity is the memory allocated for the buffer: a heap `byte[]` of that length plus a 16-byte header.

**B2e. Procedure.**
1. `cd $RUN/probe && mkdir -p classes && javac -cp "$RUN/cassandra/build/classes/main:$RUN/cassandra/lib/*" -d classes src/org/apache/cassandra/io/util/DobGrowthProbe.java`
2. `CP="$RUN/probe/classes:$RUN/cassandra/build/classes/main:$RUN/cassandra/lib/*:$RUN/cassandra/conf"`
3. Run the default first:
   - `java -Xms2g -Xmx2g -cp "$CP" org.apache.cassandra.io.util.DobGrowthProbe bytes 200 > $RUN/probe/out-unset-bytes200.txt`
   - The same with `rows 200`.
4. For each `T in 0 16 64 128 1024`, and for each `mode/n in "bytes 200" "bytes 100" "rows 200" "rows 100"`:
   - `java -Xms2g -Xmx2g -Dcassandra.DOB_DOUBLING_THRESHOLD_MB=$T -cp "$CP" org.apache.cassandra.io.util.DobGrowthProbe $mode $n > $RUN/probe/out-T$T-$mode$n.txt`
5. Positive control: `java -Xms2g -Xmx2g -cp "$CP" org.apache.cassandra.io.util.DobGrowthProbe fixed 200 > $RUN/probe/out-fixed.txt`
6. `grep -h "DOUBLING\|FINAL\|OVERFLOW" $RUN/probe/out-*.txt`. Repeat step 4 once more for `bytes 200`. The output must be identical, because the code is deterministic.
7. If class initialisation fails (for example a logging or `FileUtils` static error), add `-Dcassandra.config=file://$RUN/cassandra/conf/cassandra.yaml` and call `org.apache.cassandra.config.DatabaseDescriptor.clientInitialization()` at the top of `main`. Record that the fallback was used.
8. Optional, off-heap variant: the same loop on `new SafeMemoryWriter(128)` (capacity = `capacity()`, `SafeMemoryWriter.java:89-92`). It is predicted to show the same sequence as `bytes`. Close it at the end.

**B2f. Predictions.** These were computed from `DataOutputBuffer.java:158-172` and `BufferedDataOutputStreamPlus.java:102-136` before any run. Capacities are in bytes, with MiB in brackets.

| T | mode, n | last-but-one capacity | final capacity C | C / S | transient old+new at last resize | # resizes |
|---|---|---|---|---|---|---|
| unset (= 64) | bytes 200 | 201,326,592 (192.00) | 301,989,888 (288.00) | 1.440 | 480.00 MiB | 14 |
| 0 | bytes 200 | 193,710,244 (184.74) | 290,565,366 (277.10) | 1.386 | 461.84 MiB | 21 |
| 16 | bytes 200 | 169,869,312 (162.00) | 254,803,968 (243.00) | 1.215 | 405.00 MiB | 15 |
| 64 | bytes 200 | 201,326,592 (192.00) | 301,989,888 (288.00) | 1.440 | 480.00 MiB | 14 |
| 128 | bytes 200 | 134,217,728 (128.00) | 268,435,456 (256.00) | 1.280 | 384.00 MiB | 13 |
| 1024 | bytes 200 | 134,217,728 (128.00) | 268,435,456 (256.00) | 1.280 | 384.00 MiB | 13 |
| 0 / 16 / 64 / 128 / 1024 | bytes 100 | 82.11 / 72.00 / 64.00 / 64.00 / 64.00 MiB | 129,140,163 / 113,246,208 / 134,217,728 / 134,217,728 / 134,217,728 | 1.23 / 1.08 / 1.28 / 1.28 / 1.28 | 205.3 / 180.0 / 192.0 / 192.0 / 192.0 MiB | 19 / 13 / 12 / 12 / 12 |
| unset (= 64) | rows 200 | 151,002,432 (144.01) | 226,503,648 (216.01) | 1.080 | 360.02 MiB | 10 |
| 0 | rows 200 | 204,083,397 (194.63) | 306,125,095 (291.94) | 1.460 | 486.57 MiB | 15 |
| 16 | rows 200 | 191,112,453 (182.26) | 286,668,679 (273.39) | 1.367 | 455.65 MiB | 12 |
| 64 | rows 200 | 151,002,432 (144.01) | 226,503,648 (216.01) | 1.080 | 360.02 MiB | 10 |
| 128 | rows 200 | 201,336,576 (192.01) | 302,004,864 (288.01) | 1.440 | 480.02 MiB | 10 |
| 1024 | rows 200 | 134,224,384 (128.01) | 268,448,768 (256.01) | 1.280 | 384.02 MiB | 9 |
| 0 / 16 / 64 / 128 / 1024 | rows 100 | 86.50 / 81.00 / 96.00 / 64.00 / 64.00 MiB | 136,055,598 / 127,408,302 / 151,002,432 / 134,224,384 / 134,224,384 | 1.30 / 1.22 / 1.44 / 1.28 / 1.28 | 216.3 / 202.5 / 240.0 / 192.0 / 192.0 MiB | 13 / 10 / 9 / 8 / 8 |
| any | fixed 200 | n/a | 1,048,576 (1.00), constant | n/a | n/a | 0, then `OVERFLOW position=1048576` |

Relations predicted:
- **(i)** C ≥ S in every growable row.
- **(ii)** Every `EXPAND` ratio is exactly 2.0, or `(before+count)/before` on the first resize, while `before` ≤ T·2^20. It is 1.5 (floor) once `before` > T·2^20.
- **(iii)** C is not monotone in T. For `rows 200`: T=64 < T=1024 < T=128. For `bytes 200`: T=64 = unset > T=1024.
- **(iv)** `DOUBLING_THRESHOLD_MB` prints the T passed, and 64 when unset.
- **(v)** Halving S roughly halves C at each T: the ratios C(200)/C(100) are between 1.5 and 2.25.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| (i)-(v) hold, the table matches exactly, and `fixed` overflows at 1 MiB | Claim confirmed at unit level: T changes only the growth ratio. Capacity follows the payload and is never held at or near T, while a real cap (fixed buffer) does bind. |
| For some T, C < S with no `OVERFLOW`, or growth stops near T MiB while writes still succeed | The knob caps usage. **Claim refuted.** |
| C decreases steadily as T decreases, proportionally to T (for example about T·k MiB) | Usage follows the knob. **Claim refuted.** |
| C flat across T at the T=1024 values, and `DOUBLING_THRESHOLD_MB` shows 64 for every run | The property was not applied. Invalid: fix the `-D` spelling (case-sensitive key) and rerun. |
| Usage follows the payload (C changes 100 → 200 MiB) while it is flat or non-monotone in T, and `fixed` binds | Claim confirmed: the positive control moved and the knob did not cap. |
| `fixed` does not overflow, or S never exceeds T for any T < 1024 | Not confirmed: the instrument or the workload did not reach the regime under test. |
| Numbers differ slightly from B2f but (i)-(iii) hold | The write path differs from the trace (for example extra flushes). The claim stands; record the difference in D. |

**B2h. Controls.**
- **Property read back:** the printed `DOUBLING_THRESHOLD_MB` confirms what the class read, which rules out a misspelled property.
- **Defaults:** the unset run must equal the T=64 run, which confirms the default.
- **Cap visibility:** the `DataOutputBufferFixed` run shows that the instrument sees a real cap.
- **Payload effect:** the 100 vs 200 MiB pair shows that the payload drives capacity.
- **Repeatability:** a repeated run must be identical, which rules out nondeterminism.
- **One JVM per T:** this avoids the static-final caching trap.

### B3. Cluster tier

**B3a. Environment and build.**
- **Node:** one Linux node with ≥ 8 GB RAM, JDK 11 and Ant. Use the same `$RUN` copy and `ant jar` as B2a.
- **Python:** python3 for the driver script, using the bundled `lib/cassandra-driver-internal-only-3.29.0.zip` the same way `bin/cqlsh.py:46-64` does. If `import cassandra.cluster` fails (for example on Python ≥ 3.12 without asyncore), create a venv: `python3 -m venv $RUN/venv && $RUN/venv/bin/pip install cassandra-driver==3.29.0`, and run the script with `$RUN/venv/bin/python`.
- **Configuration:** leave `conf/cassandra.yaml` at its defaults. Data, commit log, hints and saved caches then go under `$CASSANDRA_HOME/data` = `$RUN/cassandra/data`, which is on local disk. If ports 7000, 9042 or 7199 are in use on the node, change `storage_port` and `native_transport_port` in `conf/cassandra.yaml` and set `JMX_PORT` in the environment.
- **Environment per run:**

```
export CASSANDRA_HOME=$RUN/cassandra
export MAX_HEAP_SIZE=4G                 # G1 (conf/jvm11-server.options:63); leave HEAP_NEWSIZE unset
export CASSANDRA_LOG_DIR=$RUN/logs/T${T:-unset}
export JVM_EXTRA_OPTS="-XX:FlightRecorderOptions=stackdepth=128 ${T:+-Dcassandra.DOB_DOUBLING_THRESHOLD_MB=$T}"
```

- **JFR settings:** check that the JDK's `profile` settings enable the event: `grep -A3 'jdk.ObjectAllocationOutsideTLAB' $JAVA_HOME/lib/jfr/profile.jfc` must show `enabled` = `true` and `stackTrace` = `true`. If not, copy the file to `$RUN/dob.jfc`, set both to `true`, and use `settings=$RUN/dob.jfc` below.
- **Parser:** `$RUN/probe/JfrDob.java`. Run it with JDK 11 single-file launch: `java $RUN/probe/JfrDob.java <file>`.

```java
import java.nio.file.Paths;
import jdk.jfr.consumer.*;

public class JfrDob
{
    public static void main(String[] a) throws Exception
    {
        for (RecordedEvent e : RecordingFile.readAllEvents(Paths.get(a[0])))
        {
            if (!e.getEventType().getName().equals("jdk.ObjectAllocationOutsideTLAB") || e.getStackTrace() == null)
                continue;
            boolean dob = false, local = false;
            for (RecordedFrame f : e.getStackTrace().getFrames())
            {
                String m = f.getMethod().getType().getName() + "." + f.getMethod().getName();
                if (m.equals("org.apache.cassandra.io.util.DataOutputBuffer.expandToFit")) dob = true;
                if (m.equals("org.apache.cassandra.db.ReadResponse$LocalDataResponse.build")) local = true;
            }
            if (dob && local)
                System.out.println(e.getStartTime() + " " + e.getThread("eventThread").getJavaName()
                                   + " " + e.getClass("objectClass").getName() + " " + e.getLong("allocationSize"));
        }
    }
}
```

**B3b. Knobs.**
- **`cassandra.DOB_DOUBLING_THRESHOLD_MB`:** unset, 0, 16, 64, 128, 1024. These are the same values and reasons as B2b. Each value is set through `JVM_EXTRA_OPTS` and needs a node restart.
- **Positive control:** the page size, a limit known to bind this buffer. The read runs with client paging off, so the internal aggregate page is 10000 rows and holds all 200 rows (`SelectStatement.java:899-902`). The control repeats it with `fetch_size=100`, so each internal page holds 100 rows.

**B3c. Workload.**
- **Schema:** `CREATE KEYSPACE dob WITH replication={'class':'SimpleStrategy','replication_factor':1}` and `CREATE TABLE dob.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression={'enabled':false}`.
- **Load:** 200 rows in partition 0, each with a 1 MiB random `v` (`os.urandom(1048576)`), using a prepared INSERT at CL ONE.
  - Each mutation is about 1 MiB. That is below `max_mutation_size` (half of `commitlog_segment_size: 32MiB`, `conf/cassandra.yaml:652-660`) and below the native message limit.
  - Total data is about 200 MiB, plus a commit log of the same order.
- **Read:** `SELECT max(v) FROM dob.t WHERE pk = 0` at CL ONE.
  - `max` accepts any type (`AggregateFcts.java:65-71`), so `v` is fetched, but the client receives only one 1 MiB value.
  - With paging off, the single local read goes through `StorageProxy.LocalReadRunnable` → `command.createResponse` (`StorageProxy.java:2211`, `ReadCommand.java:374`) → `ReadResponse.LocalDataResponse.build`. That method serialises all 200 rows (S ≈ 200 MiB + about 200·15 B) into **one** heap `new DataOutputBuffer()` (`ReadResponse.java:197-203`).
  - The response keeps the full backing array (`buffer.buffer()`).
- **Reachability:** S ≈ 200 MiB, which exceeds T for every T except 1024 and exceeds the heap's G1 humongous threshold (1 MiB with 2 MiB regions). The default T=64 is crossed partway through.
- **Repetitions:** 3 recorded queries per T, 5 s apart, after 1 unrecorded warm-up. With the positive control, 3 more queries with `fetch_size=100`.
- **Duration:** under 2 minutes per T after startup.

`$RUN/probe/dob.py`. One script, with mode in `argv[1]`:

```python
import sys, os, glob, time
CH = os.environ['CASSANDRA_HOME']
z = glob.glob(CH + '/lib/cassandra-driver-internal-only-*.zip')
if z:
    ver = os.path.basename(z[0])[len('cassandra-driver-internal-only-'):-4]
    sys.path.insert(0, os.path.join(z[0], 'cassandra-driver-' + ver))
    for p in glob.glob(CH + '/lib/*.zip'):
        if p != z[0]: sys.path.insert(1, p)
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
from cassandra import ConsistencyLevel
s = Cluster(['127.0.0.1'], port=int(os.environ.get('CQLPORT', '9042'))).connect()
if sys.argv[1] == 'load':
    s.execute("CREATE KEYSPACE IF NOT EXISTS dob WITH replication={'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE IF NOT EXISTS dob.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression={'enabled':false}")
    ins = s.prepare("INSERT INTO dob.t (pk, ck, v) VALUES (0, ?, ?)")
    for ck in range(200):
        s.execute(ins, (ck, os.urandom(1048576)))
    print('loaded', s.execute("SELECT count(*) FROM dob.t WHERE pk=0").one())
else:  # read <fetch_size or 0> <repeats>
    fs = int(sys.argv[2]); reps = int(sys.argv[3])
    for i in range(reps):
        st = SimpleStatement("SELECT max(v) FROM dob.t WHERE pk=0", consistency_level=ConsistencyLevel.ONE,
                             fetch_size=(fs if fs > 0 else None))
        t0 = time.time(); r = s.execute(st, timeout=120).one()
        print('read', i, 'fetch', fs, 'len', len(r[0]), 'secs', round(time.time() - t0, 2)); time.sleep(5)
```

**B3d. Observables and instruments.**
- **Primary:** JFR `jdk.ObjectAllocationOutsideTLAB` events whose stack contains both `DataOutputBuffer.expandToFit` and `ReadResponse$LocalDataResponse.build`.
  - Each event's `allocationSize` is the heap bytes of one new buffer array: capacity + 16-byte array header, aligned to 8.
  - Every expansion large enough to fall outside a TLAB is recorded. In JDK 11 this event is not sampled. That covers all expansions of about 1 MiB and above. Smaller early expansions may be missing, which is acceptable because only the tail matters.
  - Instrument: `jcmd <pid> JFR.start/JFR.dump`, parsed with `JfrDob.java`.
- **Secondary:** the G1 log `$CASSANDRA_LOG_DIR/gc.log`, written by default by `cassandra-env.sh:83`.
  - Read `Heap Region Size` and, for GCs during the queries, the `Humongous regions: a->b` lines. A buffer of capacity C occupies ceil(C/region) regions.
  - Also `jcmd <pid> GC.heap_info` before and right after a query.
- **Applied knob:** `jcmd <pid> VM.system_properties | grep -i DOB_DOUBLING`.
- **Not directly observable:** the in-JVM value of the `static final` field (inferred from the ratio pattern and the system property), and exactly when the array is freed.

**B3e. Procedure.**
1. `df -h $RUN` (≥ 10 GB free); `free -g` (≥ 8 GB).
2. First T (start with *unset*):
   - Set the env (B3a).
   - `mkdir -p $CASSANDRA_LOG_DIR $RUN/jfr`
   - `$CASSANDRA_HOME/bin/cassandra -p $RUN/cassandra.pid > $CASSANDRA_LOG_DIR/stdout.txt 2>&1`
   - Poll `$CASSANDRA_HOME/bin/nodetool status` until it shows `UN`, up to 3 min.
3. `PID=$(cat $RUN/cassandra.pid)`. Run `jcmd $PID VM.system_properties | grep -i DOB_DOUBLING` and record the output. It must be absent for unset, and show `=T` otherwise.
4. Only on the very first start:
   - `python3 $RUN/probe/dob.py load`
   - `$CASSANDRA_HOME/bin/nodetool flush dob`
   - `du -sh $CASSANDRA_HOME/data` (expect about 200-450 MB).

   The data persists across restarts and is reused for every T.
5. Warm-up: `python3 $RUN/probe/dob.py read 0 1`.
6. Record the main reads:
   - `jcmd $PID JFR.start name=dob settings=profile` (or `settings=$RUN/dob.jfc`)
   - `jcmd $PID GC.heap_info > $RUN/jfr/T${T:-unset}-heap-before.txt`
   - `python3 $RUN/probe/dob.py read 0 3`
   - `jcmd $PID GC.heap_info > $RUN/jfr/T${T:-unset}-heap-after.txt`
   - `jcmd $PID JFR.dump name=dob filename=$RUN/jfr/T${T:-unset}.jfr`
   - `jcmd $PID JFR.stop name=dob`
7. Positive control, recorded in the same way to `$RUN/jfr/T${T:-unset}-ctl.jfr`, with `python3 $RUN/probe/dob.py read 100 3`. It is mandatory for unset, 64 and 1024, and optional for the others.
8. Stop the node:
   - `$CASSANDRA_HOME/bin/nodetool drain; kill $PID`
   - Wait until `kill -0 $PID` fails, up to 60 s. Use `kill -9` only if needed, and note it.
   - `pgrep -u $USER -f CassandraDaemon` must print nothing started by this run.
9. Repeat steps 2-3 and 5-8 for T = 0, 16, 64, 128, 1024.
10. Parse: `for f in $RUN/jfr/*.jfr; do java $RUN/probe/JfrDob.java $f > ${f%.jfr}.txt; done`. Each query is a burst of lines on one `ReadStage` thread. Per burst, take capacity = `allocationSize - 16` for the last two lines, and compute the consecutive ratios.
11. Copy `$RUN/jfr/*.txt`, the heap_info files and the `gc.log` Humongous lines to the results location, then clean up (B4).

**B3f. Predictions.** These were stated before any run. They come from the same rule as B2f, assuming the page starts with h ≈ 20-60 header bytes before the first value, so the first large capacity is 1 MiB + h. Values are given to about ±0.1 MiB.

| T | last-but-one buffer capacity per query | largest buffer capacity C per query | consecutive ratio pattern (from about 1 MiB up) |
|---|---|---|---|
| unset = 64 | ≈ 144.0 MiB | ≈ 216.0 MiB | 2.0 ×6 (1 → 64.0x MiB), then 1.5 ×3 (96, 144, 216) |
| 0 | ≈ 194.6 MiB | ≈ 291.9 MiB | 1.5 throughout |
| 16 | ≈ 182.3 MiB | ≈ 273.4 MiB | 2.0 up to about 16.0x MiB, then 1.5 |
| 64 | ≈ 144.0 MiB | ≈ 216.0 MiB | as unset |
| 128 | ≈ 192.0 MiB | ≈ 288.0 MiB | 2.0 up to about 128.0x MiB, then 1.5 |
| 1024 | ≈ 128.0 MiB | ≈ 256.0 MiB | 2.0 throughout |
| control (fetch 100), T=64 / unset | ≈ 96.0 MiB | ≈ 144.0 MiB per internal page (2 pages per query) | as T=64 |
| control (fetch 100), T=1024 | ≈ 64.0 MiB | ≈ 128.0 MiB per internal page | 2.0 throughout |

Relations predicted:
- In every T run, C ≥ S ≈ 200.0 MiB, and C ≥ T MiB whenever T < 200.
- C is not monotone in T: C(64) < C(1024) < C(128).
- The three queries of one T give the same sizes (±0.1 MiB).
- In the control, C drops by a factor of about 1.5 (T=64: 216 → 144) to 2 (T=1024: 256 → 128). The page size moves usage; T does not cap it.
- GC log: Humongous region growth during a query of at least ceil(C/region size). With 4 GB G1 the region size is 2 MiB, so at least 108 regions for T=64 and at least 144 for T=128.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Per T, largest capacity ≥ 200 MiB, ratios as in B3f, C non-monotone in T, and control C about 1.5-2x smaller | **Claim confirmed:** usage follows the page, not T. T only sets the growth factor. |
| Largest capacity at or near T MiB (for example ≤ about 2·T for T=16) while the query still succeeds and returns 1 MiB | The knob caps the buffer. **Claim refuted.** |
| Largest capacity decreases monotonically with T, roughly in proportion | Usage follows the knob. **Claim refuted.** |
| Usage flat across T (all values equal to T=1024's ≈ 256 MiB) and the system property absent | The knob was not applied. Invalid run: fix `JVM_EXTRA_OPTS` and redo. |
| Capacities flat or non-monotone across T while the fetch-100 control drops them | **Claim confirmed**, with the positive control moved. |
| Control does not reduce C, or no `LocalDataResponse` events at all | Not confirmed. Either the read did not take the local path (for example remote replica, other coordinator, or digest read) or JFR did not capture the event. Check the stack depth, the event enablement, and that RF=1 on one node. |
| Query fails (`OutOfMemoryError`, timeout) | The node is undersized. Raise `MAX_HEAP_SIZE` to 6G, or use 150 rows (rerun B2 `rows 150` for exact predictions). That is not a cap. |
| Sizes off by more than 1 MiB but the ratio rule holds | The serialisation header differs from the assumed h. The claim stands; record it in D. |

**B3h. Controls.**
- **Knob applied:** confirmed by `jcmd VM.system_properties`.
- **Default:** the unset run must equal T=64.
- **Same data for every T:** loaded and flushed once, so the payload is constant.
- **Repeats and warm-up:** 3 repeats per T, and a warm-up query that is excluded.
- **Positive control:** the page size, a limit known to bind this buffer, shows that the instrument and the workload can move usage.
- **No other traffic:** single node, RF=1, CL ONE, no other clients. The stack filter on `LocalDataResponse.build` excludes other allocations.
- **Unit agreement:** B2 `rows 200` / `rows 100` give the exact values that B3 should approximate.

**B4. Risks and cleanup.**
- **Disk:**
  - Unit tier: none beyond `$RUN` (classes and text output under 10 MB).
  - Cluster tier: about 200 MB sstable, up to about 300 MB commit log, logs under 100 MB, and JFR files of about 10-100 MB each (about 1 GB in all). Everything stays under `$RUN` on local disk. Never use shared storage.
- **Memory:**
  - Unit: 2 GB heap.
  - Cluster: 4 GB heap plus off-heap. Check `free -g` first, and do not run alongside other memory-heavy jobs on the node.
- **Processes:** the probe JVMs exit on their own. Stop the node after every T (B3e step 8). At the end, run `pgrep -u $USER -f 'CassandraDaemon|DobGrowthProbe|JfrDob'`; it must print nothing. Stop any leftover JFR recordings first: `jcmd $PID JFR.check`, then `JFR.stop`.
- **Ports:** if defaults collide with another instance on the node, change them (B3a) rather than stopping someone else's process.
- **Cleanup:** after copying results, `rm -rf $RUN/cassandra/data $RUN/cassandra/logs $RUN/logs $RUN/jfr`, then optionally `rm -rf $RUN`. Do not touch the pristine source tree.

## C. Sources read

- src/java/org/apache/cassandra/io/util/DataOutputBuffer.java
- src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java
- src/java/org/apache/cassandra/io/util/DataOutputBufferFixed.java
- src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java
- src/java/org/apache/cassandra/io/util/FileUtils.java (static fields, `clean`)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (lines 183, 200-206, 806-818)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (native_transport_max_message_size default, 903-918)
- src/java/org/apache/cassandra/db/ReadResponse.java (40-60, 182-210)
- src/java/org/apache/cassandra/db/ReadCommand.java (366-383, grep)
- src/java/org/apache/cassandra/service/StorageProxy.java (2178-2240)
- src/java/org/apache/cassandra/service/reads/range/RangeCommandIterator.java (207, grep)
- src/java/org/apache/cassandra/cql3/statements/SelectStatement.java (114, 285-345, 890-910)
- src/java/org/apache/cassandra/cql3/functions/AggregateFcts.java (65-71, 845, grep)
- src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java (190-205)
- src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java (126-127, grep)
- test/unit/org/apache/cassandra/io/util/SafeMemoryWriterTest.java
- test/unit/org/apache/cassandra/io/util/BufferedDataOutputStreamTest.java (grep, 580-625)
- conf/cassandra.yaml (directories, 652-660, 825, 883)
- conf/cassandra-env.sh (61-135, 307)
- conf/jvm11-server.options (63)
- bin/cqlsh.py (40-70)
- bin/cassandra (118-119, 184)
- build.xml (jvmarg and target lines, grep)
- CHANGES.txt (grep: 601, 1356, 3315, 3395)
- lib/ listing (cassandra-driver-internal-only-3.29.0.zip)
- https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html (API relied on; not fetched in this session)

## D. Stage-4 feedback

none yet
