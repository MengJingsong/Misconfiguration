# MAX_ARRAY_SIZE — verification solution  <!-- file: cases/max_array_size-saturatedarraysizecast-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line, **linked**: [`DataOutputBuffer.java:124`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L124) (`return (int)Math.min(MAX_ARRAY_SIZE, size);` in `saturatedArraySizeCast(long size)`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `positive`. The line clamps every requested new capacity of a growing `DataOutputBuffer` to `MAX_ARRAY_SIZE` (2147483639 bytes), and the next check turns any growth past that into a `BufferOverflowException`, so one `DataOutputBuffer` (heap, or direct for the thread-local scratch buffers) never holds more than 2147483639 bytes. Caveats: it is a per-buffer ceiling equal to the JVM array limit, not a tunable or aggregate memory limit; the last growth step briefly holds old plus new buffer (about 3.4 GiB). |
| Ground | — |

> Link rule applied: the declaration (A1) and the given line (Entry pointer, A3) are permalinks
> at tag `cassandra-5.0.9`; other citations are plain `file:line` in the pinned tree.

## A. Constraint trace

**A1. The constraint.**
- Name: `DataOutputBuffer.MAX_ARRAY_SIZE`.
- Kind: compile-time **constant** (`static final int`, package-private, `@VisibleForTesting`).
- Declared at [`DataOutputBuffer.java:118`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L118):
  `static final int MAX_ARRAY_SIZE = Integer.MAX_VALUE - 8;`
- Unit: bytes (the capacity of the buffer's backing `ByteBuffer`).
- Value: 2147483647 − 8 = **2147483639** bytes (2 GiB − 9 B). Derivation is the comment at
  `DataOutputBuffer.java:115-116`: "The actual value observed in Hotspot is only -2 /
  ByteArrayOutputStream uses -8", i.e. it copies the JDK's conservative maximum array length so
  that `ByteBuffer.allocate(int)` (a `byte[]`) cannot fail with "Requested array size exceeds VM
  limit". The same value is noted in `utils/JVMStabilityInspector.java:202`.
- How it can be set: **not settable** (no yaml key, no `-D` property, no JMX). Changing it needs a
  source change and rebuild (both tiers below use a patched copy for that, see B2a/B2b). The
  neighbouring growth parameters are settable at JVM start only:
  `-Dcassandra.DOB_DOUBLING_THRESHOLD_MB` (default 64, `CassandraRelevantProperties.java:203`,
  read at `DataOutputBuffer.java:48`), `-Dcassandra.dob_max_recycle_bytes` (default 1 MiB,
  `CassandraRelevantProperties.java:204`, `DataOutputBuffer.java:53`) and
  `-Dcassandra.dob.allocate_type` (DIRECT/ONHEAP for scratch buffers, default DIRECT,
  `CassandraRelevantProperties.java:183`, `DataOutputBuffer.java:55`).

**A2. What it caps.**
- Resource: memory held by one `DataOutputBuffer`'s backing buffer. For `new DataOutputBuffer()`
  and `new DataOutputBuffer(int)` it is **heap** (`BufferedDataOutputStreamPlus.allocate` →
  `ByteBuffer.allocate`, `BufferedDataOutputStreamPlus.java:75-78`). For the thread-local
  `DataOutputBuffer.scratchBuffer` it is **off-heap direct memory** by default
  (`DataOutputBuffer.java:84-88`, allocation type default DIRECT at `:55`).
- Quantity compared: `size`, the proposed new capacity computed by `calculateNewSize`
  (`DataOutputBuffer.java:158-172`): `max(capacity + count, 2×capacity)` while capacity ≤ 64 MiB,
  `max(capacity + count, 1.5×capacity)` above it. Line 124 returns `min(MAX_ARRAY_SIZE, size)`.

**A3. Mechanism.**
1. A write that does not fit calls `doFlush(count)` (`BufferedDataOutputStreamPlus.java:112`
   for `write(byte[],..)`, `:135` for `write(ByteBuffer)`); `DataOutputBuffer.doFlush` →
   `expandToFit(count)` (`DataOutputBuffer.java:136-139`). The `GrowingChannel` path also calls
   `expandToFit` (`:204-210`).
2. `expandToFit` (`:174-182`) returns for `count <= 0`, else calls `calculateNewSize(count)`
   (`:158-172`), which computes the doubling / +50 % size in `long` arithmetic and passes it to
   `validateReallocation(newSize)` (`:149-155`).
3. `validateReallocation` calls `saturatedArraySizeCast(newSize)` (`:121-125`):
   `Preconditions.checkArgument(size >= 0)` (`:123`), then **the given line**
   [`DataOutputBuffer.java:124`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L124)
   `return (int)Math.min(MAX_ARRAY_SIZE, size);`.
4. Outcomes:
   - `size < MAX_ARRAY_SIZE`: the full size is returned; growth proceeds normally.
   - `size >= MAX_ARRAY_SIZE` (the limit is reached): the result is **saturated** to
     2147483639. Back in `validateReallocation` (`:152-153`) `if (saturatedSize <= capacity())
     throw new BufferOverflowException();` — so if the buffer is *not yet* at the ceiling it grows
     to exactly 2147483639 bytes; if it already is, the write fails with
     `java.nio.BufferOverflowException` and nothing is allocated.
   - `checkedArraySizeCast` (`:128-133`, called at `:178`) re-asserts `size <= MAX_ARRAY_SIZE`
     (cannot fail after step 3).
   - Then `allocate(n)` (`:178`), copy old contents (`:179-180`), `setBuffer` frees the old buffer
     if direct (`FileUtils.clean`, `:184-188`); an old heap buffer becomes garbage.
5. Growth sequence with default settings when written in 1 MiB pieces from the 128-byte start:
   1 MiB, 2, 4, … 64 MiB (doubling while capacity ≤ 64 MiB, strict `>` at `:166`), 128 MiB,
   then ×1.5: 201326592, 301989888, 452984832, 679477248, 1019215872, 1528823808, then
   2293235712 → saturated to **2147483639**; the next growth throws.
6. Bypasses and overshoots:
   - **Transient overshoot:** during the last growth the old (1528823808 B) and new
     (2147483639 B) buffers are both live: ≈ 3.42 GiB for one buffer, plus earlier heap buffers
     not yet collected.
   - **Copies outside the buffer:** `toByteArray()` / `asNewBuffer()` (`DataOutputBuffer.java:279-290`)
     allocate a second array of up to the same size (e.g. `Mutation.java:455`).
   - **Initial size not clamped:** `DataOutputBuffer(int size)` (`:99-102`) allocates `size`
     directly (an int, so still ≤ `Integer.MAX_VALUE`).
   - **Subclasses:** `SafeMemoryWriter.validateReallocation` (`SafeMemoryWriter.java:101-106`)
     overrides the check and allows growth beyond 2 GiB (off-heap `Memory`), so it is not
     governed by this constant; `DataOutputBufferFixed` (`DataOutputBufferFixed.java:50-64`)
     never grows (throws on any overflow).
   - **No aggregate bound:** the cap is per buffer; any number of buffers can coexist (one per
     in-flight local read in `ReadResponse.java:198-201`, one scratch buffer per thread).
7. Effect on a request: a local data read serializes the whole result into
   `new DataOutputBuffer()` (`ReadResponse.java:196-207`, reached from `ReadCommand.java:374/383`
   via `StorageProxy.LocalReadRunnable`, dispatched at `AbstractReadExecutor.java:165`). A result
   larger than 2147483639 serialized bytes throws `BufferOverflowException`, which
   `LocalReadRunnable` turns into `handler.onFailure(..., UNKNOWN)` and rethrows
   (`StorageProxy.java:2243-2254`): the client gets a read failure; the node keeps running (it is
   not an OOM, so `JVMStabilityInspector` does not kill it).

**A4. Other consumers.** Everything else on heap / direct memory: memtables, chunk cache, key and
row caches, coordinator result materialisation (`ResultMessage.Rows`), native-protocol frames,
the `toByteArray` copies above, `SafeMemoryWriter` (index summaries), `BufferPool`. Callers of
growing DOBs include `CommitLog.add` (`CommitLog.java:306`, bounded earlier by
`mutation.validateSize`, i.e. max_mutation_size), `Mutation` serialization caching
(`Mutation.java:453`, `:491`), `UnfilteredSerializer` row bodies (`UnfilteredSerializer.java:195`),
`HintsWriter.java:77`, `BatchlogManager.java:146`, `PartitionUpdate.toBytes`
(`PartitionUpdate.java:271`), trie writers, `DescribeStatement`. None of these has a byte limit of
its own on the DOB beyond this constant, except where an upstream check (max_mutation_size, read
size thresholds when enabled — disabled by default per `conf/cassandra.yaml:2015-2026`) stops the
work earlier.

**A5. Evidence beyond the source.**
- `test/unit/org/apache/cassandra/io/util/DataOutputTest.java:140-249`: `testDataOutputBufferMaxSizeFake`
  (spy overriding `capacity()` grows until `BufferOverflowException` and asserts the last size
  ≥ `MAX_ARRAY_SIZE`), `testDataOutputBufferMaxSize` (real 2 GiB write, skipped unless the heap is
  ≥ ~4.7 GiB; then `write(42)` must throw `BufferOverflowException`), and direct tests of
  `saturatedArraySizeCast` / `checkedArraySizeCast` / `validateReallocation` (`:224-248`).
- JDK 11 `java.io.ByteArrayOutputStream` / `java.util.ArrayList` use `MAX_ARRAY_SIZE =
  Integer.MAX_VALUE - 8` for the same reason:
  https://github.com/openjdk/jdk11u/blob/master/src/java.base/share/classes/java/io/ByteArrayOutputStream.java
- `ByteBuffer.allocate(int)` / `allocateDirect(int)` take an `int` capacity:
  https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html
- JFR consumer API used by the cluster instrument:
  https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html
- The source copy has no git history, so the introducing ticket was not identified.

## B. Verification solution

**B1. Claim under test.** No single `DataOutputBuffer` ever allocates a backing buffer larger than
`MAX_ARRAY_SIZE` (2147483639 bytes stock, or the patched value): growth past it is clamped to
exactly that size once, and the next growth fails with `BufferOverflowException` instead of
allocating more; changing the constant moves this ceiling to the new value. The claim is wrong if
a DOB allocation larger than the constant is seen, if a write/read that needs more than the
constant in one buffer succeeds, or if the ceiling does not move with a patched constant.

### B2. Unit tier

**B2a. Environment and build.**
- Linux node, JDK 11 (`java -version` shows 11.x), Ant ≥ 1.10.
- Local-disk working directory (not NFS/shared), ≥ 20 GB free:
  ```bash
  export S4=/mydata/s4-o172          # any local-disk path; adjust
  mkdir -p $S4 && df -hT $S4         # type must not be nfs/ceph/lustre
  ```
- Two copies of the pinned tree (never build in the shared tree):
  ```bash
  rsync -a ~/cassandra-5.0.9/ $S4/cass-stock/      # or from the stage-4 source location of tag cassandra-5.0.9
  rsync -a ~/cassandra-5.0.9/ $S4/cass-patched/
  # instrumentation patch (patched copy only): read the constant from a -D property, default unchanged
  sed -i 's/static final int MAX_ARRAY_SIZE = Integer.MAX_VALUE - 8;/static final int MAX_ARRAY_SIZE = Integer.getInteger("o172.dob.max_array_size", Integer.MAX_VALUE - 8);/' \
      $S4/cass-patched/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java
  grep -n 'MAX_ARRAY_SIZE =' $S4/cass-patched/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java   # must show getInteger
  (cd $S4/cass-stock && ant jar) && (cd $S4/cass-patched && ant jar)
  ```
- Harness source outside both trees: `$S4/harness/src/org/apache/cassandra/io/util/DobCapProbe.java`
  (same package, so it can read the package-private `MAX_ARRAY_SIZE` and `capacity()`):
  ```java
  package org.apache.cassandra.io.util;

  import java.lang.management.BufferPoolMXBean;
  import java.lang.management.ManagementFactory;
  import java.nio.BufferOverflowException;
  import java.nio.ByteBuffer;

  import org.apache.cassandra.config.DatabaseDescriptor;

  public class DobCapProbe
  {
      static long heapUsed() { System.gc(); return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed(); }
      static long directUsed()
      {
          for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
              if (b.getName().equals("direct")) return b.getMemoryUsed();
          return -1;
      }

      public static void main(String[] args) throws Exception
      {
          DatabaseDescriptor.clientInitialization();
          String mode = args[0];                    // heap | scratch | fixed
          long total = Long.parseLong(args[1]);     // bytes to attempt
          int chunk = Integer.parseInt(args[2]);    // bytes per write call
          System.out.printf("MAX_ARRAY_SIZE=%d mode=%s total=%d chunk=%d%n", DataOutputBuffer.MAX_ARRAY_SIZE, mode, total, chunk);
          System.out.printf("BASELINE heapUsed=%d directUsed=%d%n", heapUsed(), directUsed());
          DataOutputBuffer dob = mode.equals("heap")    ? new DataOutputBuffer()
                               : mode.equals("scratch") ? DataOutputBuffer.scratchBuffer.get()
                               : new DataOutputBufferFixed(ByteBuffer.allocate(64 << 20));
          byte[] b = new byte[chunk];
          long lastCap = dob.capacity();
          System.out.printf("CAP %d at position=0%n", lastCap);
          long written = 0;
          String outcome = "COMPLETED";
          try
          {
              while (written < total)
              {
                  int n = (int) Math.min(chunk, total - written);
                  dob.write(b, 0, n);
                  written += n;
                  long cap = dob.capacity();
                  if (cap != lastCap) { System.out.printf("CAP %d at position=%d%n", cap, dob.position()); lastCap = cap; }
              }
          }
          catch (BufferOverflowException e) { outcome = "OVERFLOW"; e.printStackTrace(System.out); }
          catch (OutOfMemoryError e)        { outcome = "OOM " + e.getMessage(); }
          System.out.printf("RESULT outcome=%s position=%d capacity=%d heapUsed=%d directUsed=%d%n",
                            outcome, dob.position(), dob.capacity(), heapUsed(), directUsed());
          dob.close();
          System.out.printf("AFTER_CLOSE capacity=%d heapUsed=%d directUsed=%d%n",
                            dob.buffer == null ? -1 : dob.capacity(), heapUsed(), directUsed());
      }
  }
  ```
  (A `CAP` line is printed after the write that caused the growth; with 1 MiB chunks every growth
  point above 1 MiB falls on a chunk boundary, so the printed position is the position at which
  the buffer was full.)
- Compile once per build (classes go to `$S4/harness/out-<build>`, never into a tree):
  ```bash
  for B in stock patched; do
    C=$S4/cass-$B; mkdir -p $S4/harness/out-$B
    javac -cp "$C/build/classes/main:$C/lib/*:$C/build/lib/jars/*" -d $S4/harness/out-$B \
          $S4/harness/src/org/apache/cassandra/io/util/DobCapProbe.java
  done
  ```
- JVM options for every run: `-Xms12g -Xmx12g -XX:+UseG1GC -XX:MaxDirectMemorySize=8g
  -Dlogback.configurationFile=$C/conf/logback-tools.xml`. 12 GiB covers the ≈3.42 GiB transient
  plus earlier garbage; 8 GiB direct covers the scratch run.

**B2b. Knobs.**
- The constant itself, via the patched copy's `-Do172.dob.max_array_size`: **unset**
  (= 2147483639, stock behaviour; run on both builds to show the patch is neutral),
  **314572800** (300 MiB: between chain values 301989888 and 452984832, so the clamp, not the
  growth rule, sets the final size), **104857600** (100 MiB: between 64 MiB and 128 MiB).
- Bytes written `total` relative to the ceiling: 1400 MiB (below the last unclamped step
  1528823808), 1500 MiB (forces the saturated 2147483639 allocation but fits), 2304 MiB (needs
  more than the ceiling), 400 MiB (for patched caps, the stock comparison, and the fixed control).
- Buffer kind: `heap` (`new DataOutputBuffer()`), `scratch` (thread-local, direct),
  `fixed` (`DataOutputBufferFixed` over 64 MiB: a cap known to bind, positive control).
- Chunk size fixed at 1048576 bytes so all growth points fall on chunk boundaries (every chain
  value in A3 step 5 is a multiple of 1 MiB).

**B2c. Workload.** Repeated `write(byte[1048576])` into the buffer until `total` bytes or an
exception. Arithmetic: 2304 MiB = 2415919104 B > 2147483639 B, so the ceiling is passed by
268435465 B; the 2048th chunk is copied only partly (1048567 B), then `doFlush(9)` asks for
max(1.5×2147483639, 2147483648) → saturated 2147483639 ≤ capacity → throw. 1500 MiB =
1572864000 B > 1528823808, so the 1459th chunk triggers the saturated allocation. Patched
300 MiB: 400 MiB > 314572800, overflow after exactly 300 chunks. Patched 100 MiB: overflow after
exactly 100 chunks.

**B2d. Observables and instruments.**
- `CAP` lines: every backing-buffer capacity change (the check's operand after clamping) and the
  position; `DataOutputBuffer.capacity()` is exact.
- `RESULT outcome`: COMPLETED / OVERFLOW (stack trace must name
  `DataOutputBuffer.validateReallocation`, or `DataOutputBufferFixed.doFlush` for the fixed
  control) / OOM.
- `heapUsed` after `System.gc()` (MemoryMXBean) and `directUsed` (BufferPoolMXBean "direct"):
  the real resource held, at baseline, at the end and after `close()`.
- Not observable directly: the transient peak during the copy at `DataOutputBuffer.java:179-180`
  (inferred as old + new capacity). Optional: add `-Xlog:gc*:file=$S4/unit-gc-<run>.log` to see
  heap-after-GC per collection.

**B2e. Procedure.**
```bash
MiB=1048576
run() { B=$1; NAME=$2; shift 2; C=$S4/cass-$B
  java -Xms12g -Xmx12g -XX:+UseG1GC -XX:MaxDirectMemorySize=8g \
       -Dlogback.configurationFile=$C/conf/logback-tools.xml "$@" \
       -cp "$S4/harness/out-$B:$C/build/classes/main:$C/lib/*:$C/build/lib/jars/*" \
       org.apache.cassandra.io.util.DobCapProbe $ARGS 2>&1 | tee $S4/unit-$NAME.txt; }
ARGS="heap $((2304*MiB)) $MiB"    run stock   U1
ARGS="heap $((1500*MiB)) $MiB"    run stock   U2
ARGS="heap $((1400*MiB)) $MiB"    run stock   U3
ARGS="scratch $((2304*MiB)) $MiB" run stock   U4
ARGS="fixed $((400*MiB)) $MiB"    run stock   U5
ARGS="heap $((400*MiB)) $MiB"     run patched U6 -Do172.dob.max_array_size=314572800
ARGS="heap $((400*MiB)) $MiB"     run patched U7 -Do172.dob.max_array_size=104857600
ARGS="heap $((2304*MiB)) $MiB"    run patched U8
ARGS="heap $((400*MiB)) $MiB"     run stock   U9
grep -H 'MAX_ARRAY_SIZE=\|^CAP\|^RESULT\|^AFTER_CLOSE\|BufferOverflowException\|at org.apache.cassandra.io.util' $S4/unit-U*.txt
pgrep -f DobCapProbe || echo "no harness JVM left"
```
(Each run is a separate JVM, one at a time; each takes seconds to a minute.)

**B2f. Predictions** (stated before any run; B = baseline heap, tens of MB):

| Run | Build / cap | Kind, total | Outcome | Final capacity | Last `CAP` values | Memory at RESULT |
|---|---|---|---|---|---|---|
| U1 | stock 2147483639 | heap, 2304 MiB | OVERFLOW at position **2147483639** | **2147483639** | …1019215872, 1528823808, 2147483639 (at position 1528823808) | heapUsed ≈ B + 2147483639 (≈ 2.0 GiB + B) |
| U2 | stock | heap, 1500 MiB | COMPLETED, position 1572864000 | **2147483639** (saturated) | …1528823808, 2147483639 | heapUsed ≈ B + 2.0 GiB |
| U3 | stock | heap, 1400 MiB | COMPLETED, position 1468006400 | 1528823808 | …1019215872, 1528823808 | heapUsed ≈ B + 1.42 GiB |
| U4 | stock | scratch, 2304 MiB | OVERFLOW at 2147483639 | 2147483639 | same as U1 | directUsed ≈ 2147483639 (+ < 1 MiB); AFTER_CLOSE capacity 128 and directUsed back to ≈ baseline |
| U5 | stock | fixed 64 MiB, 400 MiB | OVERFLOW at 67108864 (stack in `DataOutputBufferFixed.doFlush`) | 67108864 | only `CAP 67108864 at position=0` | heapUsed ≈ B + 64 MiB |
| U6 | patched 314572800 | heap, 400 MiB | OVERFLOW at **314572800** | **314572800** | …201326592, 301989888, 314572800 | heapUsed ≈ B + 300 MiB |
| U7 | patched 104857600 | heap, 400 MiB | OVERFLOW at **104857600** | **104857600** | …33554432, 67108864, 104857600 | heapUsed ≈ B + 100 MiB |
| U8 | patched, property unset | heap, 2304 MiB | identical to U1 | 2147483639 | identical to U1 | identical to U1 |
| U9 | stock | heap, 400 MiB | COMPLETED, position 419430400 | 452984832 | …301989888, 452984832 | heapUsed ≈ B + 432 MiB |

In every run no `CAP` value exceeds the run's `MAX_ARRAY_SIZE` and no OOM occurs. The first
`CAP` after 128 is 1048576 (`max(256, 128 + 1048448)`).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| U1/U4 end OVERFLOW at position and capacity exactly 2147483639, stack through `validateReallocation`; no `CAP` above it | Claim confirmed for stock heap and direct buffers |
| U6/U7 end at exactly 314572800 / 104857600 while U9 (same 400 MiB workload, stock) completes at 452984832 | Ceiling follows the constant: confirmed (usage follows the constraint) |
| Any `CAP` > that run's `MAX_ARRAY_SIZE`, or U1 COMPLETED | **Claim wrong** |
| U6/U7 complete, or stop at a different capacity | **Claim wrong** (ceiling not set by the constant), unless the `MAX_ARRAY_SIZE=` header shows the patch was not in force |
| U2 final capacity < 2147483639 although position is 1572864000 | Growth model (A3 step 5) wrong; re-trace before reading the rest |
| OOM in U1/U2/U4 | Inconclusive: heap/direct too small for the ≈3.42 GiB transient; raise `-Xmx`/`MaxDirectMemorySize` and rerun |
| U5 does not overflow at 64 MiB | Harness/instrument broken (known-binding control failed): results invalid |
| U8 differs from U1 | Patch not neutral; patched-build results invalid |
| U4 AFTER_CLOSE directUsed still ≈ 2 GiB | Scratch trimming (`DataOutputBuffer.java:71-81`) not working; separate finding, does not refute the cap |

**B2h. Controls.**
- Positive control (cap known to bind): U5 `DataOutputBufferFixed` stops at its 64 MiB buffer with
  the same harness and instruments, so an overflow is detectable.
- Same workload, cap moved: U9 (stock, completes) vs U6/U7 (patched, stop at the cap) separates
  "the clamp binds" from "the workload is too small".
- Patch neutrality: U8 = U1.
- Below / at / above the ceiling: U3 (no clamp), U2 (clamp hit, fits), U1 (clamp, then overflow).
- The `MAX_ARRAY_SIZE=` header line records the value in force in each run.

### B3. Cluster tier

**B3a. Environment and build.**
- One node (the cap is per buffer in one JVM), RF = 1, so every read is a local data read
  serialized through `ReadResponse.LocalDataResponse.build` (`ReadResponse.java:196-207`).
- Builds `$S4/cass-stock` and `$S4/cass-patched` from B2a. Both use the same data directories and
  run one at a time.
- Configuration (same edits in `conf/` of both copies):
  ```bash
  for B in stock patched; do C=$S4/cass-$B
    cat >> $C/conf/cassandra.yaml <<EOF
  data_file_directories:
      - $S4/node/data
  commitlog_directory: $S4/node/commitlog
  hints_directory: $S4/node/hints
  saved_caches_directory: $S4/node/saved_caches
  cdc_raw_directory: $S4/node/cdc_raw
  native_transport_timeout: 600s
  EOF
    sed -i -e 's/^storage_port: 7000/storage_port: 17000/' \
           -e 's/^native_transport_port: 9042/native_transport_port: 19042/' \
           -e 's/- seeds: "127.0.0.1:7000"/- seeds: "127.0.0.1:17000"/' \
           -e 's/^read_request_timeout: 5000ms/read_request_timeout: 600000ms/' $C/conf/cassandra.yaml
    sed -i 's/^JMX_PORT="7199"/JMX_PORT="17199"/' $C/conf/cassandra-env.sh
  done
  mkdir -p $S4/node/{data,commitlog,hints,saved_caches,cdc_raw,logs}
  ss -ltn | grep -E ':(17000|19042|17199)\b' && echo "PORT IN USE: pick others" || echo ports free
  ```
  (The directory keys are commented out in the stock yaml, `conf/cassandra.yaml:97,395,408,431,611`,
  so appending them is safe; `native_transport_timeout` is `Config.java:1399`.)
- JVM: `MAX_HEAP_SIZE=16G HEAP_NEWSIZE=4G` (G1 from `conf/jvm11-server.options:63`, 16 MiB regions
  `:66`), GC log via `JVM_EXTRA_OPTS` (`conf/cassandra-env.sh:307`).
- Client: Python 3 with the driver bundled in the tree (loaded the way cqlsh does,
  `bin/cqlsh.py:31-56`). If `import cassandra` fails, use
  `python3 -m venv $S4/venv && $S4/venv/bin/pip install cassandra-driver==3.29.0` and run the
  client with `$S4/venv/bin/python`.

**B3b. Knobs.**
- Constant: stock build (2147483639); patched build with `-Do172.dob.max_array_size=314572800`
  (300 MiB) in `JVM_EXTRA_OPTS`.
- Result size (one partition per size, rows of 1 MiB): **P150** (150 rows ≈ 157 MB serialized;
  1.5× ≈ 236 MB, below both ceilings), **P400** (400 rows ≈ 419.4 MB: below stock, above
  300 MiB), **P2560** (2560 rows ≈ 2684 MB: above stock).

**B3c. Workload.**
- Schema: `CREATE KEYSPACE o172 WITH replication = {'class':'SimpleStrategy','replication_factor':1};`
  `CREATE TABLE o172.p (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression = {'enabled':'false'};`
- Load: partitions pk = 150, 400, 2560 with that many rows each, `v` = 1048576 random bytes
  (`os.urandom`), one INSERT per row (1 MiB < max_mutation_size, 16 MiB by default). Total
  3110 MiB of values; on disk ≈ 3.3 GB data, plus commit log until flushed.
- Read: `SELECT pk, ck, v FROM o172.p WHERE pk = X` with paging **off** (`fetch_size=None`), so one
  local read serializes the whole partition into one `DataOutputBuffer`. Serialized size ≈ rows ×
  (1048576 + a small per-row overhead): P2560 ≈ 2684 MB > 2147483639, passing the ceiling by
  > 500 MB; P400 ≈ 419 MB > 314572800 for the patched run.
- Duration: load a few minutes; each read seconds to a few minutes (timeouts raised to 600 s).
- Scripts (in `$S4/client/`, outside any tree):
  ```python
  # $S4/client/o172.py   usage: python3 o172.py <cassandra_home> load | read <pk>
  import sys, os, glob, time
  C = sys.argv[1]
  z = glob.glob(os.path.join(C, 'lib', 'cassandra-driver-internal-only-*.zip'))[0]
  ver = os.path.basename(z)[len('cassandra-driver-internal-only-'):-4]
  sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + ver))
  from cassandra.cluster import Cluster
  from cassandra.query import SimpleStatement
  s = Cluster(['127.0.0.1'], port=19042, connect_timeout=60).connect()
  s.default_timeout = 900
  if sys.argv[2] == 'load':
      s.execute("CREATE KEYSPACE IF NOT EXISTS o172 WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
      s.execute("CREATE TABLE IF NOT EXISTS o172.p (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression = {'enabled':'false'}")
      ins = s.prepare("INSERT INTO o172.p (pk, ck, v) VALUES (?, ?, ?)")
      for pk in (150, 400, 2560):
          for ck in range(pk):
              s.execute(ins, (pk, ck, os.urandom(1048576)))
          print('loaded', pk, flush=True)
  else:
      pk = int(sys.argv[3]); t = time.time()
      try:
          rows = list(s.execute(SimpleStatement("SELECT pk, ck, v FROM o172.p WHERE pk = %s", fetch_size=None), (pk,)))
          print('READ pk=%d OK rows=%d bytes=%d secs=%.1f' % (pk, len(rows), sum(len(r.v) for r in rows), time.time() - t))
      except Exception as e:
          print('READ pk=%d FAIL %s: %s secs=%.1f' % (pk, type(e).__name__, e, time.time() - t))
  ```
  ```java
  // $S4/client/JfrDob.java   usage: java JfrDob.java <file.jfr>   (JDK 11 single-file launch)
  import jdk.jfr.consumer.*;
  import java.nio.file.Path;
  public class JfrDob {
      public static void main(String[] a) throws Exception {
          long max = 0;
          for (RecordedEvent e : RecordingFile.readAllEvents(Path.of(a[0]))) {
              if (!e.getEventType().getName().equals("jdk.ObjectAllocationOutsideTLAB")) continue;
              long size = e.getLong("allocationSize");
              RecordedStackTrace st = e.getStackTrace();
              if (size < (16L << 20) || st == null) continue;
              boolean dob = false; StringBuilder sb = new StringBuilder();
              for (RecordedFrame f : st.getFrames()) {
                  String m = f.getMethod().getType().getName() + "." + f.getMethod().getName();
                  if (m.startsWith("org.apache.cassandra.io.util.DataOutputBuffer")) dob = true;
                  if (sb.length() < 400) sb.append(" <- ").append(m);
              }
              if (!dob) continue;
              max = Math.max(max, size);
              System.out.println("DOB_ALLOC " + e.getStartTime() + " size=" + size + sb);
          }
          System.out.println("DOB_ALLOC_MAX " + max);
      }
  }
  ```

**B3d. Observables and instruments.**
- **DOB allocation sizes** (the resource the cap governs): JFR `jdk.ObjectAllocationOutsideTLAB`
  with stack traces (enabled in the JDK 11 `profile` settings), filtered by `JfrDob.java` to
  stacks through `DataOutputBuffer`. `allocationSize` is the object size, i.e. array length plus
  the 16-byte header rounded up to 8: length 2147483639 → **2147483656**; 314572800 →
  **314572816**; 452984832 → 452984848. Every DOB growth above 16 MiB is allocated outside a TLAB,
  and each such allocation is an event.
- Heap: `jstat -gc <pid> 1000` (OU/OC; humongous arrays live in old regions) into a file, and the
  GC log (`-Xlog:gc*:file=$S4/node/logs/gc-<run>.log:time,uptime`) for heap-after-GC.
- Outcome: client line `READ ... OK/FAIL`; `$S4/node/logs/system.log` for
  `java.nio.BufferOverflowException` with frames `DataOutputBuffer.validateReallocation` ←
  `calculateNewSize` ← `expandToFit` ← … ← `ReadResponse$LocalDataResponse.build`.
- Node health after each read: `bin/nodetool -p 17199 status` shows `UN`.
- Not observable directly: the copy-time peak (old + new buffer); inferred from consecutive
  `DOB_ALLOC` sizes and the jstat OU peak.

**B3e. Procedure.**
```bash
export S4=/mydata/s4-o172; export CASSANDRA_LOG_DIR=$S4/node/logs
start() { B=$1; RUN=$2; EXTRA=$3; C=$S4/cass-$B
  MAX_HEAP_SIZE=16G HEAP_NEWSIZE=4G \
  JVM_EXTRA_OPTS="-Xlog:gc*:file=$S4/node/logs/gc-$RUN.log:time,uptime $EXTRA" \
    $C/bin/cassandra -p $S4/node/cassandra.pid > $S4/node/logs/start-$RUN.out 2>&1
  sleep 10; until grep -q "Starting listening for CQL clients" $S4/node/logs/system.log 2>/dev/null; do sleep 5; done
  PID=$(cat $S4/node/cassandra.pid); echo "node pid $PID"; ps -o args= -p $PID | tr ' ' '\n' | grep -E 'Xmx|o172' ; }
stop() { kill $(cat $S4/node/cassandra.pid); while kill -0 $(cat $S4/node/cassandra.pid) 2>/dev/null; do sleep 2; done
  mv $S4/node/logs/system.log $S4/node/logs/system-$1.log; }
readrun() { B=$1; RUN=$2; PK=$3; C=$S4/cass-$B
  jcmd $PID JFR.start name=$RUN settings=profile filename=$S4/jfr-$RUN.jfr
  jstat -gc $PID 1000 > $S4/jstat-$RUN.txt & JS=$!
  python3 $S4/client/o172.py $C read $PK | tee $S4/client-$RUN.txt
  sleep 5; kill $JS; jcmd $PID JFR.stop name=$RUN
  java $S4/client/JfrDob.java $S4/jfr-$RUN.jfr | tee $S4/dob-$RUN.txt | tail -3
  $C/bin/nodetool -p 17199 status | grep 127.0.0.1; }

# 1. stock node: load data once
start stock S0
python3 $S4/client/o172.py $S4/cass-stock load
$S4/cass-stock/bin/nodetool -p 17199 flush o172
du -sh $S4/node/data $S4/node/commitlog
# 2. stock reads: small, large-but-below, over the ceiling, small again (node health)
readrun stock C1 150
readrun stock C2 400
mark=$(wc -l < $S4/node/logs/system.log)
readrun stock C3 2560
tail -n +$mark $S4/node/logs/system.log | grep -A12 BufferOverflowException | head -40 | tee $S4/bofe-C3.txt
readrun stock C4 150
stop stock
# 3. patched node, cap 300 MiB, same data
start patched P0 "-Do172.dob.max_array_size=314572800"
readrun patched C5 150
mark=$(wc -l < $S4/node/logs/system.log)
readrun patched C6 400
tail -n +$mark $S4/node/logs/system.log | grep -A12 BufferOverflowException | head -40 | tee $S4/bofe-C6.txt
readrun patched C7 2560
stop patched
# 4. nothing left running
pgrep -f "$S4/cass-" || echo "no node left"; pgrep -f "jstat -gc" || echo "no jstat left"
```

**B3f. Predictions** (before any run):

| Run | Build / cap | Read | Client | DOB_ALLOC_MAX (JFR) | system.log | Heap (jstat OU) |
|---|---|---|---|---|---|---|
| C1 | stock | P150 | OK, 150 rows, 157286400 value bytes | between ≈157 MB and ≈236 MB | no BufferOverflowException | rises by ≤ ~0.5 GB, collected |
| C2 | stock | P400 | OK, 400 rows, 419430400 value bytes | between ≈419 MB and ≈630 MB (452984848 if growth follows the ×1.5 chain); < 2147483656 | none | rises ~1–2 GB transiently (DOB + result copies) |
| C3 | stock | P2560 | **FAIL** (`ReadFailure`, or a server error carrying it) | **exactly 2147483656** (length 2147483639), preceded by a DOB allocation > 1431655759 (the last ×1.5 step); **none** larger | ERROR with `java.nio.BufferOverflowException` at `DataOutputBuffer.validateReallocation` ← `LocalDataResponse.build` | peak rise ≥ ~3.5 GB (old + new buffer), drops after GC; stays < 16 GiB; no OOM |
| C4 | stock | P150 | OK (node healthy after C3) | as C1 | none | as C1 |
| C5 | patched 314572800 | P150 | OK | < 314572816 | none | as C1 |
| C6 | patched 314572800 | P400 | **FAIL** | **exactly 314572816**; none larger | BufferOverflowException as in C3 | rise ≤ ~0.6 GB |
| C7 | patched 314572800 | P2560 | **FAIL** | **exactly 314572816**; none larger | BufferOverflowException | as C6 |

`nodetool status` shows `UN` after every read.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| C3 fails with BufferOverflowException and DOB_ALLOC_MAX = 2147483656, while C2 succeeds | Stock ceiling binds on the real client path: confirmed |
| C6/C7 DOB_ALLOC_MAX = 314572816 and fail, while C2 (same P400 read, stock) succeeds | Ceiling follows the constant: confirmed |
| Any DOB allocation > 2147483656 (stock) or > 314572816 (patched) | **Claim wrong** |
| C3 returns all 2560 rows | **Claim wrong**, unless JFR shows the read was split into several smaller DOBs (paging was not off): fix `fetch_size=None` and repeat |
| C6 succeeds | **Claim wrong**, unless the `ps` line at node start lacks `-Do172.dob.max_array_size` (property not applied) |
| C3 fails with `OutOfMemoryError` / node dies | Inconclusive for the cap (heap too small for the ≈3.4 GiB transient plus result copies; G1 needs 128 contiguous 16 MiB regions); raise to `MAX_HEAP_SIZE=24G` and repeat |
| C3 fails with a timeout and no BufferOverflowException in the log | Inconclusive: timeouts not raised; check `read_request_timeout` / `native_transport_timeout` and repeat |
| C1/C5 fail | Setup problem (client, ports, timeouts): fix before reading other rows |
| JFR shows no DOB allocation in C2 | Instrument not working (it must see the known growth): fix JFR settings before trusting C3/C6 |

**B3h. Controls.**
- Positive control (cap known to bind, same workload): C6 — the same P400 read that succeeds on
  stock (C2) fails at exactly the patched size, so the JFR + log instruments detect a binding cap.
- Below-ceiling controls: C1/C2/C5 succeed, so failures in C3/C6 are not caused by the table,
  client or timeouts.
- Node-health control: C4 after C3.
- Same data and JVM settings; only the constant changes between C2 and C6.
- The `ps` line printed at each node start records the effective JVM options.

**B4. Risks and cleanup.**
- Disk: data ≈ 3.3 GB + commit log up to ≈ 3.3 GB before flush + two builds (≈ 1–2 GB each) under
  `$S4` on local disk; check `df -h $S4` ≥ 20 GB free first. Nothing is written to the shared
  source tree, `/proj` or an NFS home (harness, client, logs, JFR files all under `$S4`).
- Memory: unit runs need 12 GiB heap + up to 8 GiB direct; the node 16 GiB heap. Run one JVM at a
  time; check `free -g` first.
- Ports 17000/19042/17199 must be free; pick others if `ss` shows them in use.
- Leftover processes: after each tier `pgrep -f DobCapProbe`, `pgrep -f "$S4/cass-"`,
  `pgrep -f "jstat -gc"` must print nothing; kill any that remain (`kill <pid>`, then `kill -9`).
  JFR recordings end with `JFR.stop` (and with the JVM).
- Cleanup: `rm -rf $S4/node $S4/jfr-*.jfr` once results are filed (keep `unit-*.txt`,
  `client-*.txt`, `dob-*.txt`, `jstat-*.txt`, `bofe-*.txt`); then
  `rm -rf $S4/cass-stock $S4/cass-patched $S4/harness` if no further runs are planned.

## C. Sources read

- src/java/org/apache/cassandra/io/util/DataOutputBuffer.java
- src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java (lines 30-140)
- src/java/org/apache/cassandra/io/util/DataOutputBufferFixed.java (doFlush/expandToFit)
- src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java (lines 40-110)
- src/java/org/apache/cassandra/io/util/FileUtils.java (static fields)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (lines 183, 203, 204)
- src/java/org/apache/cassandra/config/Config.java (read_request_timeout, max_mutation_size, native_transport_timeout)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (clientInitialization signatures)
- src/java/org/apache/cassandra/db/ReadResponse.java (lines 40-65, 180-230)
- src/java/org/apache/cassandra/db/ReadCommand.java (lines 374, 383)
- src/java/org/apache/cassandra/service/StorageProxy.java (LocalReadRunnable 2184-2262, DroppableRunnable 2595-2615)
- src/java/org/apache/cassandra/service/reads/AbstractReadExecutor.java (lines 155-168)
- src/java/org/apache/cassandra/db/commitlog/CommitLog.java (lines 290-340)
- src/java/org/apache/cassandra/db/Mutation.java (lines 440-505)
- src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java (lines 185-215)
- src/java/org/apache/cassandra/batchlog/BatchlogManager.java (lines 140-160)
- src/java/org/apache/cassandra/db/partitions/PartitionUpdate.java (lines 265-280)
- src/java/org/apache/cassandra/utils/JVMStabilityInspector.java (lines 195-210)
- grep of `new DataOutputBuffer(` and `scratchBuffer.get()` over src/java
- test/unit/org/apache/cassandra/io/util/DataOutputTest.java (lines 140-285)
- conf/cassandra.yaml, conf/jvm11-server.options, conf/cassandra-env.sh, conf/ (listing)
- build.xml (testsome, maxMemory)
- bin/cqlsh.py (lines 31-56); lib/cassandra-driver-internal-only-3.29.0.zip (listing)
- https://github.com/openjdk/jdk11u/blob/master/src/java.base/share/classes/java/io/ByteArrayOutputStream.java (cited from knowledge of the JDK source, not fetched)
- https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html (cited, not fetched)
- https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html (cited, not fetched)

## D. Stage-4 feedback

none yet
