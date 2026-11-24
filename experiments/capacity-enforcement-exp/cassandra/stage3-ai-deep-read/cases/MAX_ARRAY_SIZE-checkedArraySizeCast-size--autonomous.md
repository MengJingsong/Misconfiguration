# MAX_ARRAY_SIZE — verification solution  <!-- file: cases/MAX_ARRAY_SIZE-checkedArraySizeCast-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line, **linked**: [`DataOutputBuffer.java:131`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L131) — `Preconditions.checkArgument(size <= MAX_ARRAY_SIZE);` in `checkedArraySizeCast(long size)` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-opus-5-5, Claude Code 2.1.330, 2026-11-24 (autonomous agent) |
| Estimate | `positive` — `MAX_ARRAY_SIZE` (Integer.MAX_VALUE − 8 = 2,147,483,639 bytes) caps the capacity of every growable `DataOutputBuffer` (heap or direct): growth is clamped to it at line 124 and refused with `BufferOverflowException` at line 153 once the buffer is already at it. The given line 131 is a redundant second guard that cannot fail on any production path (its operand was already clamped), and the cap is per buffer, not an aggregate bound. |
| Ground | — |

> Unit kind: enforcement. Per the task, the template's "if statement" is read as "the given line"
> (line 131, a `Preconditions.checkArgument`, i.e. an `if (!cond) throw IllegalArgumentException`).

## A. Constraint trace

**A1. The constraint.**

- Name: `DataOutputBuffer.MAX_ARRAY_SIZE`.
- Kind: compile-time constant (`static final int`, package-private, `@VisibleForTesting`).
- Declared: [`DataOutputBuffer.java:118`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L118)
  `static final int MAX_ARRAY_SIZE = Integer.MAX_VALUE - 8;`
- Unit: bytes (it bounds `ByteBuffer` capacity, which is in bytes).
- Value: 2,147,483,647 − 8 = **2,147,483,639** bytes (≈ 2 GiB − 9 B). Derivation is in the comment at
  `DataOutputBuffer.java:115-116`: HotSpot's real limit is `Integer.MAX_VALUE − 2`; the code copies the
  conservative `− 8` used by `java.io.ByteArrayOutputStream` / `AbstractCollection`.
- Settable: **no** — not a yaml key, `-D` property or JMX attribute. Changing it needs a source edit and
  rebuild (and a restart). It is referenced only inside `DataOutputBuffer` (lines 118, 124, 131) and in
  `test/unit/.../DataOutputTest.java`, so recompiling `DataOutputBuffer.java` alone is enough to change it
  (javac inlines the constant only into referencing classes, and no other production class references it).

**A2. What it caps.**

- Resource: the memory held by one growable `DataOutputBuffer` (DOB) — **Java heap** for a plain
  `new DataOutputBuffer()` (`BufferedDataOutputStreamPlus.allocate`, `BufferedDataOutputStreamPlus.java:75-78`,
  `ByteBuffer.allocate`), **direct (off-heap) memory** for the thread-local `DataOutputBuffer.scratchBuffer`
  when `cassandra.dob.allocate_type` is `DIRECT` (the default, `DataOutputBuffer.java:55`, `:84-89`).
- Quantity compared: the requested new capacity of the backing `ByteBuffer`, a `long` computed by
  `calculateNewSize` (`DataOutputBuffer.java:158-172`). At line 131 the operand `size` is the value
  `calculateNewSize(count)` returned, i.e. the capacity about to be allocated at line 178.

**A3. Mechanism.**

1. Any write that does not fit in the current buffer calls `doFlush(count)`, where `count` is the
   number of bytes still to write: `write(byte[],int,int)` at `BufferedDataOutputStreamPlus.java:112`,
   `write(ByteBuffer)` at `:135`, `write(int)` / `writeBoolean` at `:146` / `:155`; multi-byte primitives go
   byte by byte through `writeSlow` (`:230-238`) when fewer than their width remain. The
   `GrowingChannel` path (`DataOutputBuffer.java:204-209`) calls `expandToFit` directly.
2. `DataOutputBuffer.doFlush` → `expandToFit(count)` (`DataOutputBuffer.java:136-139`, `:174-182`).
3. `calculateNewSize(count)` (`:158-172`): `newSize = capacity + count`; if `capacity > 64 MiB`
   (`DOUBLING_THRESHOLD`, property `cassandra.DOB_DOUBLING_THRESHOLD_MB`, default 64,
   `CassandraRelevantProperties.java:203`) then `max(1.5·capacity, newSize)`, else `max(2·capacity, newSize)`
   (`:163-169`). All in `long`, so no overflow.
4. `validateReallocation(newSize)` (`:149-155`): `saturatedArraySizeCast` clamps the request to
   `min(MAX_ARRAY_SIZE, newSize)` (**`:124`, the effective cap**); if the clamped value is
   `<= capacity()` — i.e. the buffer is already at `MAX_ARRAY_SIZE` — it throws
   **`java.nio.BufferOverflowException`** (`:152-153`). Otherwise it returns the clamped size.
5. **The given line:** [`DataOutputBuffer.java:131`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L131)
   `Preconditions.checkArgument(size <= MAX_ARRAY_SIZE)` inside `checkedArraySizeCast` (`:128-133`), applied
   at `:178` to the value from step 4.
   - true branch (always taken on production paths): `(int) size` is returned and `allocate(size)` runs.
   - false branch: `IllegalArgumentException` (no message), no allocation. **Unreachable through
     `expandToFit`**, because step 4 already returned a value `<= MAX_ARRAY_SIZE` (line 124). It can fire
     only if a subclass overrides `calculateNewSize`/`validateReallocation` to return more than
     `MAX_ARRAY_SIZE` while inheriting `expandToFit`; no production subclass does this
     (`SafeMemoryWriter` overrides both `validateReallocation` *and* `expandToFit`, `SafeMemoryWriter.java:45-48`,
     `:102-107`; `DataOutputBufferFixed` overrides `doFlush`/`expandToFit` to throw, `DataOutputBufferFixed.java:49-64`).
     Line 131 is therefore a defensive guard; the enforcement that actually binds is lines 124 + 152-153.
6. Allocation and copy (`:178-181`): the new buffer is allocated, the old contents copied, and
   `setBuffer` (`:184-188`) frees the old buffer immediately only if it is direct (`FileUtils.clean`,
   `FileUtils.java:362-377`); a heap old buffer becomes garbage.
7. Outcome at the limit: the write that would need more than 2,147,483,639 bytes in one DOB fails with
   `BufferOverflowException`; the caller's operation fails (e.g. on the read path the exception escapes
   `StorageProxy.LocalReadRunnable.runMayThrow`, `StorageProxy.java:2242-2253`, after
   `handler.onFailure(..., UNKNOWN)` and is wrapped in a `RuntimeException` by `StorageProxy.java:2609-2611`, so the client sees a read failure).

Overshoot and bypass:

- **Transient overshoot:** during the last growth both the old buffer (≥ MAX/1.5 ≈ 1.43 GB, < MAX) and
  the new MAX-sized buffer are live (`:178-181`), so one DOB can hold ≈ 3.6 GB for the duration of the copy
  (stock growth from 128 B with 1-byte requests: …, 1,528,823,808 → 2,147,483,639, so 3,676,307,447 B).
- **Waste before failing:** a write whose total need exceeds MAX first grows the buffer to MAX (step 4
  returns MAX > capacity), fills it, and only the next `doFlush` throws — the 2 GiB is allocated even though
  the operation cannot succeed.
- **Not covered:** constructors `DataOutputBuffer(int size)` (`:99-102`) and `DataOutputBuffer(ByteBuffer)`
  (`:104-107`) take any `int`/buffer without this check (bounded only by `int` and the JVM);
  `SafeMemoryWriter` replaces the growth logic and grows off-heap memory beyond 2 GiB
  (`SafeMemoryWriter.java:45-67`, `:102-117`).
- **Per buffer only:** nothing bounds how many DOBs are large at once; N concurrent operations can each
  hold up to MAX (plus transient old copies).

**A4. Other consumers.**

- Other DOB instances on other threads (each separately capped) and the per-thread `scratchBuffer`
  (retained capacity after `close()` limited separately by `cassandra.dob_max_recycle_bytes`, default 1 MiB,
  `DataOutputBuffer.java:53`, `:71-81`; `CassandraRelevantProperties.java:204`).
- On the read path used in B3: the coordinator's deserialized rows and the native-protocol response built
  from the `LocalDataResponse` buffer (`ReadResponse.java:182-210`), memtables, the chunk cache, the
  network/streaming buffer pools, `SafeMemoryWriter` (index summaries / offsets, off-heap).
- The JVM's own limits: `-Xmx` (heap DOBs), `-XX:MaxDirectMemorySize` (direct scratch DOBs, default = `-Xmx`;
  Cassandra leaves it unset, `conf/jvm-server.options:174`), and HotSpot's own maximum array length.

**A5. Evidence beyond the source.**

- `CHANGES.txt:3315` / `:3395` — CASSANDRA-10592 "Fix IllegalArgumentException in DataOutputBuffer.reallocate
  for large buffers" (origin of the saturating/checked casts): https://issues.apache.org/jira/browse/CASSANDRA-10592
- `CHANGES.txt:1356` — CASSANDRA-16214 "Throw BufferOverflowException from DataOutputBuffer for better
  visibility": https://issues.apache.org/jira/browse/CASSANDRA-16214
- `CHANGES.txt:601` — CASSANDRA-16471 scratch buffer on-heap/off-heap switch:
  https://issues.apache.org/jira/browse/CASSANDRA-16471
- Existing tests: `test/unit/org/apache/cassandra/io/util/DataOutputTest.java:169-249`
  (`testDataOutputBufferMaxSizeFake` simulates growth without allocating; `testDataOutputBufferMaxSize` needs
  ≥ 5,033,164,800 B max heap and is skipped otherwise; `testDataOutputBufferBigReallocation` checks the casts).
- JDK: `ByteBuffer.allocate(int)` / `allocateDirect(int)` capacity is an `int`
  (https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html);
  JFR consumer API used in B2/B3 (https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
- No git history in the working copy (it is not a git checkout).

## B. Verification solution

**B1. Claim under test.** No single growable `DataOutputBuffer` ever reaches a capacity above
`MAX_ARRAY_SIZE` (2,147,483,639 bytes with the stock constant, or the patched value when the constant is
rebuilt smaller): a workload that needs more than that in one buffer stops at exactly that capacity and the
next growth fails with `BufferOverflowException` (from `DataOutputBuffer.java:153`, never
`IllegalArgumentException` from line 131); with a smaller patched constant, the same workload's buffer stops at
the smaller value, so DOB memory follows the constant.

### B2. Unit tier

**B2a. Environment and build.**

- Linux node, JDK 11 (`java -version` 11.x), Ant, ≥ 16 GiB free RAM, ≥ 10 GiB free on a **local** disk.
- Pick a local work dir and copy the tree there (never build in the shared tree):
  ```bash
  export W=/mydata/dobcap            # any local (non-NFS) path; check: df -h $(dirname $W)
  mkdir -p $W && rsync -a ~/cassandra-5.0.9/ $W/src/
  cd $W/src && ant jar               # builds build/classes/main and the jar; deps land in lib/
  export JOPTS="$(grep -E '^--add-(exports|opens)' $W/src/conf/jvm11-clients.options | tr '\n' ' ')"
  export CP="$W/probe:$W/src/build/classes/main:$W/src/lib/*"
  ```
- Probe source location: `$W/probe-src/org/apache/cassandra/io/util/DobCapProbe.java` (same package so it can
  read the package-private `MAX_ARRAY_SIZE`, `DOUBLING_THRESHOLD`, `capacity()`, `checkedArraySizeCast`).
- Probe program (exact text):
  ```java
  package org.apache.cassandra.io.util;

  import java.lang.management.*;
  import java.nio.BufferOverflowException;
  import java.nio.ByteBuffer;
  import java.util.ArrayList;
  import java.util.List;

  public class DobCapProbe
  {
      static final List<Integer> ALLOCS = new ArrayList<>();

      // heap DOB whose allocate(size) records size == the value that passed line 131
      static class ProbeDOB extends DataOutputBuffer
      {
          @Override protected ByteBuffer allocate(int size) { ALLOCS.add(size); return ByteBuffer.allocate(size); }
      }

      static long direct()
      {
          for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
              if (b.getName().equals("direct")) return b.getTotalCapacity();
          return -1;
      }

      static long heapUsedAfterGc() { System.gc(); return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed(); }

      public static void main(String[] args) throws Exception
      {
          String mode = args[0];                         // heap | direct
          org.apache.cassandra.config.DatabaseDescriptor.clientInitialization();
          System.out.printf("MAX_ARRAY_SIZE=%d DOUBLING_THRESHOLD_MB=%d%n", DataOutputBuffer.MAX_ARRAY_SIZE, DataOutputBuffer.DOUBLING_THRESHOLD);
          // sanity: the check at line 131 works when reached directly
          try { DataOutputBuffer.checkedArraySizeCast(DataOutputBuffer.MAX_ARRAY_SIZE + 1L); System.out.println("L131 direct: NO THROW"); }
          catch (IllegalArgumentException e) { System.out.println("L131 direct: IAE as expected"); }

          long heap0 = heapUsedAfterGc(), direct0 = direct();
          DataOutputBuffer dob = mode.equals("heap") ? new ProbeDOB() : DataOutputBuffer.scratchBuffer.get();
          long written = 0, lastCap = dob.capacity();
          System.out.printf("GROW cap=%d written=%d direct=%d%n", lastCap, written, direct() - direct0);
          String outcome = "none";
          try
          {
              while (true)
              {
                  dob.write(0);                          // 1 byte; every growth is doFlush(1)
                  written++;
                  long c = dob.capacity();
                  if (c != lastCap) { System.out.printf("GROW cap=%d written=%d direct=%d%n", c, written, direct() - direct0); lastCap = c; }
              }
          }
          catch (BufferOverflowException e) { outcome = "BOE at " + e.getStackTrace()[0]; }
          catch (IllegalArgumentException e) { outcome = "IAE (line 131 fired) at " + e.getStackTrace()[0]; }
          catch (OutOfMemoryError e) { outcome = "OOM " + e.getMessage(); }
          System.out.printf("END outcome=%s written=%d finalCap=%d heapDelta=%d directDelta=%d allocs=%s%n",
                            outcome, written, dob.capacity(), heapUsedAfterGc() - heap0, direct() - direct0, ALLOCS);
          dob.close();
          System.out.printf("AFTER_CLOSE cap=%d directDelta=%d%n", dob.capacity(), direct() - direct0);
      }
  }
  ```
- JFR reader (`$W/probe-src/JfrDob.java`, run with the JDK 11 single-file launcher):
  ```java
  import jdk.jfr.consumer.*;
  import java.nio.file.Paths;

  public class JfrDob
  {
      public static void main(String[] a) throws Exception
      {
          long max = 0; int n = 0;
          for (RecordedEvent e : RecordingFile.readAllEvents(Paths.get(a[0])))
          {
              String t = e.getEventType().getName();
              if (!t.equals("jdk.ObjectAllocationOutsideTLAB") && !t.equals("jdk.ObjectAllocationInNewTLAB")) continue;
              RecordedStackTrace st = e.getStackTrace();
              if (st == null) continue;
              boolean dob = st.getFrames().stream().anyMatch(f -> f.getMethod().getType().getName()
                                .equals("org.apache.cassandra.io.util.DataOutputBuffer") && f.getMethod().getName().equals("expandToFit"));
              if (!dob) continue;
              long sz = e.getLong("allocationSize");
              System.out.println(e.getStartTime() + " " + (e.getThread() == null ? "-" : e.getThread().getJavaName()) + " " + sz);
              max = Math.max(max, sz); n++;
          }
          System.out.println("DOB_GROWTH_ALLOCS=" + n + " MAX_ALLOCATION_SIZE=" + max);
      }
  }
  ```
- Compile:
  ```bash
  mkdir -p $W/probe && javac -cp "$W/src/build/classes/main:$W/src/lib/*" -d $W/probe \
      $W/probe-src/org/apache/cassandra/io/util/DobCapProbe.java
  ```
- JVM options for every run: `-Xms10g -Xmx10g -XX:+UseG1GC -XX:MaxDirectMemorySize=6g $JOPTS`.

**B2b. Knobs.**

| Knob | Values | Why | How |
|---|---|---|---|
| `MAX_ARRAY_SIZE` (the constraint) | stock 2,147,483,639; patched **268,435,448** (= 256 MiB − 8) | the constant is not settable; a rebuilt smaller value shows the cap moves with it, at a size cheap to reach | patched: `cp $W/src/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java $W/patch-src/org/apache/cassandra/io/util/`; `sed -i 's/Integer.MAX_VALUE - 8;/256 * 1024 * 1024 - 8;/' $W/patch-src/org/apache/cassandra/io/util/DataOutputBuffer.java`; `javac -cp "$W/src/build/classes/main:$W/src/lib/*" -d $W/patched $W/patch-src/org/apache/cassandra/io/util/DataOutputBuffer.java`; run with `$W/patched` **first** on the classpath |
| allocation type | `heap` (`ProbeDOB`, heap) and `direct` (`scratchBuffer`, `allocateDirect`) | both memory kinds the cap governs | probe arg; `-Dcassandra.dob.allocate_type=DIRECT` (default) for `direct` |
| `cassandra.DOB_DOUBLING_THRESHOLD_MB` (control) | 64 (default), 4096 | changes the growth path but must not change the final cap | `-Dcassandra.DOB_DOUBLING_THRESHOLD_MB=4096` |

**B2c. Workload.** Write one byte at a time into a single DOB until it throws. Each growth is
`doFlush(1)`, so `calculateNewSize` reduces to 2× (≤ 64 MiB) or 1.5× (> 64 MiB). Stock, threshold 64:
128 → 256 → … → 67,108,864 (19 doublings) → 134,217,728 → 201,326,592 → 301,989,888 → 452,984,832 →
679,477,248 → 1,019,215,872 → 1,528,823,808 → 1.5× = 2,293,235,712 > MAX → clamped **2,147,483,639**; next
request 1.5×MAX clamps to MAX ≤ capacity → BOE. Bytes written before BOE = 2,147,483,639 (≈ 2.1 G
single-byte writes, seconds to a minute). Patched: … 134,217,728 → 201,326,592 → 301,989,888 > 268,435,448 →
clamped **268,435,448** → BOE after 268,435,448 bytes. Threshold 4096 (stock): pure doubling to
1,073,741,824 → 2,147,483,648 → clamped 2,147,483,639 → BOE.

**B2d. Observables and instruments.**

- Operand at line 131 / allocated size: every value passed to `allocate(int)` (the `allocs` list, heap
  mode) and every capacity change (`GROW` lines, both modes) — these equal the value checked at line 131.
- Outcome: exception type and top stack frame (`BOE at …validateReallocation(DataOutputBuffer.java:153)`
  expected; `IAE …checkedArraySizeCast(DataOutputBuffer.java:131)` would mean line 131 fired).
- Actual memory: heap mode — `heapDelta` (heap used after `System.gc()` with the DOB still referenced) and
  JFR allocation events filtered to `DataOutputBuffer.expandToFit` stacks (`MAX_ALLOCATION_SIZE` is the
  array size plus a 16-byte header, rounded to 8); direct mode — `BufferPoolMXBean("direct").getTotalCapacity()`
  delta at each growth, at the end and after `close()`.
- Not directly observable: the instant when old and new buffers coexist inside `expandToFit` (only inferred
  from the sizes; JFR shows the allocation of the new one while the old one is still referenced).

**B2e. Procedure.**

```bash
cd $W
J="java -Xms10g -Xmx10g -XX:+UseG1GC -XX:MaxDirectMemorySize=6g $JOPTS"
# U1 stock, heap, with JFR
$J -XX:StartFlightRecording=settings=profile,filename=$W/u1.jfr -cp "$CP" org.apache.cassandra.io.util.DobCapProbe heap | tee $W/u1.log
java $W/probe-src/JfrDob.java $W/u1.jfr | tail -3 | tee -a $W/u1.log
# U2 stock, direct
$J -cp "$CP" org.apache.cassandra.io.util.DobCapProbe direct | tee $W/u2.log
# U3 stock, heap, doubling threshold 4096 (control)
$J -Dcassandra.DOB_DOUBLING_THRESHOLD_MB=4096 -cp "$CP" org.apache.cassandra.io.util.DobCapProbe heap | tee $W/u3.log
# U4/U5 patched constant (patched class first on the classpath), heap then direct
$J -XX:StartFlightRecording=settings=profile,filename=$W/u4.jfr -cp "$W/patched:$CP" org.apache.cassandra.io.util.DobCapProbe heap | tee $W/u4.log
java $W/probe-src/JfrDob.java $W/u4.jfr | tail -3 | tee -a $W/u4.log
$J -cp "$W/patched:$CP" org.apache.cassandra.io.util.DobCapProbe direct | tee $W/u5.log
# confirm nothing left running
pgrep -f DobCapProbe || echo "no probe JVM left"
```
Check each log's first line prints the expected `MAX_ARRAY_SIZE` (2147483639 stock, 268435448 patched) —
otherwise the classpath order is wrong and the run is void.

**B2f. Predictions** (stated before any run).

| Run | Final capacity | Last GROW sizes | Outcome | Memory |
|---|---|---|---|---|
| U1 stock heap | **2,147,483,639** | …1,019,215,872, 1,528,823,808, 2,147,483,639 (27 growths after the initial 128) | `BOE at …validateReallocation(DataOutputBuffer.java:153)`, `written=2147483639` | `heapDelta` ≈ 2.147 GB (+ < 50 MB); JFR `MAX_ALLOCATION_SIZE` = 2,147,483,656 (array + 16 B header, 8-aligned; any value in 2,147,483,639…2,147,483,663 counts); no DOB allocation larger |
| U2 stock direct | 2,147,483,639 | same as U1 | BOE at line 153 | `directDelta` at END ≈ 2,147,483,639; never above ≈ 3.68 GB during a growth; after close ≈ 128 B (trimmed, `:77-80`) |
| U3 stock heap, threshold 4096 | 2,147,483,639 | …, 536,870,912, 1,073,741,824, 2,147,483,639 | BOE at line 153 | as U1 |
| U4 patched heap | **268,435,448** | …, 134,217,728, 201,326,592, 268,435,448 | BOE at line 153, `written=268435448` | `heapDelta` ≈ 268 MB; JFR max ≈ 268,435,464 |
| U5 patched direct | 268,435,448 | as U4 | BOE at line 153 | `directDelta` ≈ 268,435,448 |
| all | — | — | "L131 direct: IAE as expected"; **no run ends with `IAE (line 131 fired)`** | — |

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Final capacity = constant value (stock and patched), BOE from line 153, no allocation above it | Claim confirmed: the constant caps one DOB, and usage follows it |
| A GROW line or JFR DOB allocation > constant (+ header) | Claim refuted: the cap is bypassed |
| Patched run stops at 2,147,483,639 or keeps growing past 268,435,448 | Either the patch was not on the classpath (check first line) or the cap does not follow the constant; refuted only if the first line shows 268435448 |
| Outcome `IAE (line 131 fired)` | Line 131 is reachable on this path, contrary to A3 step 5 (trace wrong; the cap still holds but at a different line) |
| Outcome `OOM …` before reaching the constant | Not confirmed (heap/direct too small or fragmented); raise `-Xmx` / `MaxDirectMemorySize` and repeat |
| U3 final cap ≠ U1 final cap | Refuted: the bound depends on the growth policy, not the constant |
| Capacity never grows (positive control fails) | Workload or instrument broken; nothing concluded |

**B2h. Controls.**

- Positive control: the GROW sequence itself — capacity must rise with bytes written up to the cap,
  showing the workload drives usage and the instrument sees it.
- U3 (different growth policy, same final cap) separates the cap from the doubling threshold.
- U4/U5 vs U1/U2 (only the constant differs) separate the constant from the JVM's own array limit
  (which would stop at ≈ 2^31, not at 268 MB).
- The first output line confirms which constant is loaded; the "L131 direct" line confirms the check at
  line 131 works when reached, so its silence in the growth runs is due to the clamping, not a broken check.

### B3. Cluster tier

**B3a. Environment and build.**

- One Linux node, JDK 11, ≥ 32 GiB RAM, ≥ 20 GiB free on local disk; the B2 build in `$W/src` (jar from
  `ant jar`). Use a second copy for the patched run so the stock jar stays intact:
  ```bash
  rsync -a $W/src/ $W/src-patched/
  cp $W/src-patched/build/apache-cassandra-*.jar $W/stock-jar.bak
  (cd $W/patched && jar uf $(ls $W/src-patched/build/apache-cassandra-*.jar | grep -v -e javadoc -e sources) org/apache/cassandra/io/util/DataOutputBuffer*.class)
  ```
- Configuration (`$C/conf/cassandra.yaml`, `C` = `$W/src` or `$W/src-patched`), changes only:
  ```yaml
  cluster_name: dobcap
  data_file_directories: [ <W>/data-<variant> ]
  commitlog_directory: <W>/cl-<variant>
  saved_caches_directory: <W>/caches-<variant>
  hints_directory: <W>/hints-<variant>
  commitlog_total_space: 2048MiB
  read_request_timeout: 600000ms
  native_transport_timeout: 600s
  ```
  (listen/rpc on 127.0.0.1, defaults). `native_transport_max_frame_size` (16 MiB), `max_mutation_size`
  (16 MiB) and `max_value_size` (256 MiB) stay default: each insert is 1 MiB.
- JVM: `export MAX_HEAP_SIZE=12G` (G1, `conf/jvm11-server.options:63`) and
  `export JVM_EXTRA_OPTS="-Xlog:gc*:file=$W/gc-<variant>.log -XX:FlightRecorderOptions=stackdepth=128"`.
- Client: Python 3 with `cassandra-driver==3.29.0` in a local venv
  (`python3 -m venv $W/venv && $W/venv/bin/pip install cassandra-driver==3.29.0`).

**B3b. Knobs.**

| Knob | Values | Why |
|---|---|---|
| `MAX_ARRAY_SIZE` | stock 2,147,483,639; patched 268,435,448 (jar updated as above) | shows usage follows the constant on a real node |
| N = rows of 1 MiB in the one partition read | stock: 1000, 2600 (and 1800 optional); patched: 200, 400 | places the serialized read result below / above each cap |

**B3c. Workload.** Table `dobcap.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))`, RF 1, compression off,
one partition `pk=0` with N rows of 1,048,576 random bytes each. The read `SELECT ck, v FROM dobcap.t WHERE pk=0`
with **paging off** makes the local read serialize the whole partition into one
`new DataOutputBuffer()` in `ReadResponse.LocalDataResponse.build` (`ReadResponse.java:197-203`; reached via
`StorageProxy.LocalReadRunnable` → `ReadCommand.createResponse`, `StorageProxy.java:2211`,
`ReadCommand.java:366-374`). The serialized size S ≈ N × (1,048,576 + ~20) bytes:
N=200 → 0.21 GB, 400 → 0.42 GB, 1000 → 1.05 GB, 1800 → 1.89 GB, 2600 → 2.73 GB. So N=2600 > 2,147,483,639
and N=400 > 268,435,448, while N=1000/1800 (stock) and N=200 (patched) fit. The 600 s timeouts stop the query
cancellation check (`ReadCommand.java:777-791`) from ending the read first. Load ≈ 3 min for 2600 rows; each read
seconds to a minute.

Load script `$W/load.py`:
```python
import os, sys
from cassandra.cluster import Cluster
n = int(sys.argv[1])
s = Cluster(['127.0.0.1']).connect()
s.default_timeout = 120
s.execute("CREATE KEYSPACE IF NOT EXISTS dobcap WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
s.execute("DROP TABLE IF EXISTS dobcap.t")
s.execute("CREATE TABLE dobcap.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression = {'enabled':'false'}")
ins = s.prepare("INSERT INTO dobcap.t (pk, ck, v) VALUES (0, ?, ?)")
for i in range(n):
    s.execute(ins, (i, os.urandom(1 << 20)))
print("loaded", n)
```
Read script `$W/read.py`:
```python
import time
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
s = Cluster(['127.0.0.1']).connect()
t0 = time.time()
try:
    rows = s.execute(SimpleStatement("SELECT ck, v FROM dobcap.t WHERE pk=0", fetch_size=None), timeout=900)
    n = 0; b = 0
    for r in rows: n += 1; b += len(r.v)
    print("READ_OK rows=%d bytes=%d secs=%.1f" % (n, b, time.time() - t0))
except Exception as e:
    print("READ_FAIL %s: %s secs=%.1f" % (type(e).__name__, e, time.time() - t0))
```

**B3d. Observables and instruments.**

- DOB allocations on the node: JFR started with `jcmd <pid> JFR.start name=dob settings=profile` before the
  read and dumped after (`jcmd <pid> JFR.dump name=dob filename=...`), read with `JfrDob.java`
  (filter: stack contains `DataOutputBuffer.expandToFit`; this read path uses a heap DOB, so every growth is a
  Java allocation). Reported: count and maximum `allocationSize`, and the thread (`ReadStage-*`, or a `Native-Transport-Requests-*` thread when `Stage.READ.maybeExecuteImmediately` runs it inline, `AbstractReadExecutor.java:165`).
- Heap actually used: `jstat -gc <pid> 500` during the read (S0U+S1U+EU+OU, KB) and the GC log
  (`$W/gc-<variant>.log`, humongous allocations / heap after GC).
- Failure: `grep -n "BufferOverflowException" -A12 $C/logs/system.log` (logged as `RuntimeException` caused by `java.nio.BufferOverflowException`, wrapped at `StorageProxy.java:2609-2611`; stack through
  `DataOutputBuffer.validateReallocation` ← `calculateNewSize` ← `expandToFit` … `ReadResponse$LocalDataResponse.build`);
  client `READ_FAIL` (expected `ReadFailure`) vs `READ_OK`.
- Not directly observable: the copy window inside `expandToFit`; inferred from the JFR sizes and the jstat peak.

**B3e. Procedure.** For each variant V ∈ {stock (`C=$W/src`), patched (`C=$W/src-patched`)}, one at a time:

```bash
export C=$W/src            # or $W/src-patched
export CASSANDRA_HOME=$C MAX_HEAP_SIZE=12G
export JVM_EXTRA_OPTS="-Xlog:gc*:file=$W/gc-$(basename $C).log -XX:FlightRecorderOptions=stackdepth=128"
# edit $C/conf/cassandra.yaml as in B3a (paths <W>/data-<variant> etc.), then:
$C/bin/cassandra -p $W/node.pid            # background daemon
until $C/bin/nodetool status 2>/dev/null | grep -q '^UN'; do sleep 5; done
PID=$(cat $W/node.pid)
for N in <list for this variant>; do        # stock: 1000 2600 [1800] [400]; patched: 200 400
  $W/venv/bin/python $W/load.py $N && $C/bin/nodetool flush dobcap
  jcmd $PID JFR.start name=dob settings=profile
  jstat -gc $PID 500 > $W/jstat-$(basename $C)-$N.log & JS=$!
  $W/venv/bin/python $W/read.py | tee $W/read-$(basename $C)-$N.log
  kill $JS
  jcmd $PID JFR.dump name=dob filename=$W/c-$(basename $C)-$N.jfr && jcmd $PID JFR.stop name=dob
  java $W/probe-src/JfrDob.java $W/c-$(basename $C)-$N.jfr | tail -3 | tee -a $W/read-$(basename $C)-$N.log
  grep -c BufferOverflowException $C/logs/system.log
done
$C/bin/nodetool stopdaemon; sleep 10; pgrep -f CassandraDaemon && kill $(pgrep -f CassandraDaemon)
```
(`sleep` here is inside the operator's shell, not an agent tool.) Before the patched run, confirm the jar holds
the patched class: `javap -cp $(ls $C/build/apache-cassandra-*.jar | grep -v -e javadoc -e sources) -constants -p org.apache.cassandra.io.util.DataOutputBuffer | grep MAX_ARRAY_SIZE`
shows `268435448`.

**B3f. Predictions** (stated before any run).

| Variant, N | S (GB) | Max DOB `allocationSize` (JFR) | Read | system.log |
|---|---|---|---|---|
| stock, 1000 | 1.05 | in [S, 1.5·S] ≈ 1.05–1.58 GB, **< 2,147,483,639** | `READ_OK rows=1000` | no BOE |
| stock, 1800 (optional) | 1.89 | in [S, 2,147,483,656] | no BOE on the node (the client may still fail for unrelated size reasons) | no BOE |
| stock, 2600 | 2.73 | **= 2,147,483,639 + header (2,147,483,656)**; nothing larger | `READ_FAIL` (`ReadFailure`) | BOE stack through `DataOutputBuffer.java:153` and `LocalDataResponse.build`; no `IllegalArgumentException` from line 131 |
| patched, 200 | 0.21 | < 268,435,448 | `READ_OK rows=200` | no BOE |
| patched, 400 | 0.42 | **= 268,435,448 + header (≈ 268,435,464)** | `READ_FAIL` | BOE via line 153 |
| stock vs patched, same N=400 (extra stock run optional) | 0.42 | stock: in [0.42, 0.63] GB, success | — | — |

Heap (jstat): for stock N=2600 the heap used rises by roughly the DOB growth sequence, peaking at about
c_prev + 2.15 GB (c_prev ∈ [1.43, 2.15) GB, so ≈ 3.6–4.3 GB above the pre-read baseline) and falls after the
next GC; it never shows a DOB growth beyond the cap. For patched N=400 the read-attributable peak is ≈ 0.2 + 0.27 GB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| stock 2600 and patched 400 stop at exactly their constant and fail with BOE; below-cap runs succeed | Claim confirmed on a real node: the constant caps the read-result buffer and follows the constant |
| Any JFR `expandToFit` allocation larger than the constant + 24 B | Refuted |
| stock 2600 reads OK | Refuted for this path (result not serialized into one DOB as traced) — check the JFR for where it went |
| `IllegalArgumentException` from `DataOutputBuffer.java:131` | Line 131 reachable, A3 step 5 wrong; cap still enforced |
| Node dies with `OutOfMemoryError` before a BOE | Not confirmed (heap too small/fragmented for the 2 GiB humongous array); rerun with larger `MAX_HEAP_SIZE` |
| Read cancelled by timeout (`QueryCancelledException` in debug.log) before the DOB reaches the cap | Not confirmed; raise timeouts |
| stock 1000 shows no DOB allocations at all in JFR (positive control fails) | Instrument or path wrong; nothing concluded |

**B3h. Controls.**

- Positive control: stock N=1000 and patched N=200 — the same table, query and instrument show DOB allocations
  growing with S and a successful read, so the instrument and path work.
- Same N=400 on stock vs patched: only the constant differs, so a different outcome is due to it.
- `nodetool flush` before each read so the read path is the same (sstables), and only one query runs at a time
  (no other DOBs of that size).
- `javap -constants` check that the patched jar holds the patched value.

**B4. Risks and cleanup.**

- Memory: unit runs need ≈ 10 GiB heap + up to 6 GiB direct; the node needs 12 GiB heap plus the Python client
  holding up to ~2 GB (N=1800). Do not run tiers at the same time.
- Disk: everything under `$W` on local disk: ≈ 2.8 GB sstables + ≤ 2 GB commit log per variant, JFR files
  (hundreds of MB each), the two source copies (~1 GB each). Never under the shared tree or shared storage.
- Processes: after each variant, `nodetool stopdaemon`, then `pgrep -f CassandraDaemon` and `pgrep -f DobCapProbe`
  must print nothing; kill any leftover `jstat`.
- Cleanup: `rm -rf $W/data-* $W/cl-* $W/hints-* $W/caches-* $W/*.jfr` after recording results; `rm -rf $W` when done.

## C. Sources read

- src/java/org/apache/cassandra/io/util/DataOutputBuffer.java
- src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java
- src/java/org/apache/cassandra/io/util/DataOutputBufferFixed.java
- src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java
- src/java/org/apache/cassandra/io/util/FileUtils.java (lines 70-120, 362-380)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (lines 183, 203-204)
- src/java/org/apache/cassandra/config/Config.java (timeouts, frame/value/mutation sizes)
- src/java/org/apache/cassandra/db/ReadResponse.java
- src/java/org/apache/cassandra/db/ReadCommand.java (lines 366-383, 770-800)
- src/java/org/apache/cassandra/service/StorageProxy.java (LocalReadRunnable, ~2195-2260)
- src/java/org/apache/cassandra/utils/JVMStabilityInspector.java (lines 190-215)
- grep of `DataOutputBuffer` call sites under src/java
- test/unit/org/apache/cassandra/io/util/DataOutputTest.java
- test/unit/org/apache/cassandra/io/util/SafeMemoryWriterTest.java (grep)
- conf/cassandra.yaml, conf/cassandra-env.sh, conf/jvm-server.options, conf/jvm11-server.options, conf/jvm11-clients.options
- bin/cassandra.in.sh, bin/cqlsh.py, build.xml (targets/properties), CHANGES.txt
- https://issues.apache.org/jira/browse/CASSANDRA-10592
- https://issues.apache.org/jira/browse/CASSANDRA-16214
- https://issues.apache.org/jira/browse/CASSANDRA-16471
- https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html
- https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html

## D. Stage-4 feedback

none yet
