# MAX_KEY_SIZE — `BoundedByteArrayOutputStream.java:91` — verification solution  <!-- file: cases/MAX_KEY_SIZE-write-limit-2--autonomous.md -->

<!-- Hadoop version of ../../stage3-ai-deep-read/_TEMPLATE-autonomous.md (2026-11-06): same headings;
     tag, permalinks, configuration and build wording changed for Hadoop 3.4.2. -->

| Field | Value |
|---|---|
| Entry pointer | [`BoundedByteArrayOutputStream.java:91`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/BoundedByteArrayOutputStream.java#L91) — `if (currentPointer + len > limit)` in `BoundedByteArrayOutputStream.write(byte[], int, int)` (unit kind: row; not a helper unit) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `negative` — the check only bounds the write position inside a `byte[]` that the constructor has already allocated at full capacity, so heap use is fixed before any write and does not follow `limit`; the object it bounds (a TFile key buffer, 64 KiB) is not memory- or disk-significant, and the in-memory shuffle buffers that also use this class are sized and capped elsewhere (`MergeManagerImpl.reserve`). |
| Ground | (1) Memory is committed by `new byte[capacity]` at `BoundedByteArrayOutputStream.java:56`; the check at line 91 neither allocates nor frees anything, it only turns an out-of-range copy into `EOFException`, so with or without the check the array cannot grow. (2) The named limit, TFile's hard-coded `MAX_KEY_SIZE = 64 KiB`, caps the *length of one key* (a record-format rule); it fixes two 64 KiB buffers per `TFile.Writer` regardless of data, and does not bound file size, value size, record count or daemon heap. (3) In MapReduce shuffle the stream's limit equals the exact reserved size; the memory constraints there (`mapreduce.reduce.shuffle.input.buffer.percent`, `mapreduce.reduce.shuffle.memory.limit.percent`) are enforced at `MergeManagerImpl.java:268` and `:292`, not at line 91. |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). Use a permalink at the pinned tag,
> `[`File.java:123`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/<full path under the repository root>#L123)`
> (a range is `#L123-L130`). Check that the line number is the line you mean. Other citations may
> stay plain `file:line`.

**Name parts (recorded because the file name is not parsed back).** `[constraint]` = `MAX_KEY_SIZE`
(the only named value that sets the stream's limit in production; see A1), `[function]` = `write`
(the method that directly encloses line 91), `[operand]` = `limit` (the limit-side operand as written
at the check).

## A. Constraint trace

**A1. The constraint.**

- **At the check.** The limit-side operand is the instance field `limit`
  (`BoundedByteArrayOutputStream.java:37`), set in `resetBuffer` to `offset + limit`
  (`BoundedByteArrayOutputStream.java:71`), reset by `reset(int newlim)` to `newlim` (`:107`) or by
  `reset()` to `buffer.length - startOffset` (`:113`). Constructors: `(int capacity)` uses
  `limit = capacity` (`:45-46`); `(int capacity, int limit)` allocates `new byte[capacity]` and stores
  `limit` (`:55-56`); `resetBuffer` rejects `capacity < limit` (`:65`). So the field never exceeds the
  array length that is already allocated.
- **Where the value comes from (production callers, found by grep over the tree):**
  1. **TFile key buffers** (primary, the named constraint): `MAX_KEY_SIZE`, declared
     [`TFile.java:155`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/file/tfile/TFile.java#L155)
     as `private static final int MAX_KEY_SIZE = 64 * 1024; // 64KB`. Used for
     `currentKeyBufferOS` and `lastKeyBufferOS` at `TFile.java:289-290` and for the reader's
     `keyBuffer` at `TFile.java:1291`. The class javadoc states "Keys are restricted to 64KB, value
     length is not restricted" (`TFile.java:57`). Per key, `KeyRegister` narrows the limit to the
     announced key length with `reset(len)` (`TFile.java:425`) or restores it to 64 KiB with
     `reset()` (`TFile.java:427`).
  2. **MapReduce reduce-side shuffle** (secondary): `InMemoryMapOutput` builds
     `new BoundedByteArrayOutputStream(size)` (`InMemoryMapOutput.java:60`) with `size` = the
     reserved bytes from `MergeManagerImpl.unconditionalReserve` (`MergeManagerImpl.java:310-314`).
     The stream's `write` is used only for the memory-to-memory merge output
     (`MergeManagerImpl.java:405-409`, via `InMemoryWriter` → `IFileOutputStream`), which is off by
     default (`mapreduce.reduce.merge.memtomem.enabled`, read at `MergeManagerImpl.java:222`,
     default `false`). The normal fetch path writes directly into the array with
     `IOUtils.readFully(input, memory, 0, memory.length)` (`InMemoryMapOutput.java:91`) and never
     reaches line 91. The user-tunable memory keys on this path are
     `mapreduce.reduce.shuffle.input.buffer.percent` (default 0.70, `mapred-default.xml:514-515`) and
     `mapreduce.reduce.shuffle.memory.limit.percent` (default 0.25, `mapred-default.xml:532-533`);
     they are enforced in `MergeManagerImpl.reserve`, not here.
- **Kind:** constant (hard-coded `private static final`), not a configuration key; no
  `*-default.xml` entry; not settable by `-site.xml`, `-D` or refresh. Changing it requires editing
  `TFile.java` and rebuilding `hadoop-common`; a TFile written with a larger value would not be
  readable by stock readers whose `keyBuffer` is 64 KiB (`TFile.java:1291`, `:1606`).
- **Unit:** bytes. **Default:** 65,536.
- **Who reads it:** any process that writes or reads a TFile: in a running cluster, the NodeManager
  (YARN log aggregation, `AggregatedLogFormat.LogWriter`, `AggregatedLogFormat.java:491-494`), the
  `yarn logs` client and the JobHistory/Timeline web UI when reading aggregated logs, and the
  ApplicationHistoryServer's `FileSystemApplicationHistoryStore` (`FileSystemApplicationHistoryStore.java:738`,
  `:756`).

**A2. What it caps.** Nominally: the number of bytes a single TFile key may occupy in the
writer's key buffer (and therefore the length of one key in the file). The quantity compared at
line 91 is `currentPointer + len` — the write position after the requested copy — against `limit`.
Resource view: the buffer behind it is heap (`byte[]`) allocated in full at construction
(`BoundedByteArrayOutputStream.java:56`), 2 × 64 KiB per open `TFile.Writer` and 64 KiB per
`TFile.Reader.Scanner`. The check caps neither heap (the allocation is fixed beforehand) nor disk
(file size, value size and record count are unbounded). For the shuffle caller the compared
quantity is the merged-output write position against the exact reserved size of the merge buffer.

**A3. Mechanism.**

1. A `TFile.Writer` is constructed: two `BoundedByteArrayOutputStream(MAX_KEY_SIZE)` objects
   allocate 64 KiB each immediately (`TFile.java:289-290` → `BoundedByteArrayOutputStream.java:45-46`,
   `:55-56`, `:63-72`).
2. `prepareAppendKey(length)` (`TFile.java:527-536`) returns a `KeyRegister` (`TFile.java:418-428`),
   a `DataOutputStream` wrapping `currentKeyBufferOS`. With `length >= 0`, `reset(length)` sets
   `limit = length`; `length > 64 KiB` is rejected immediately with `IndexOutOfBoundsException`
   ("Limit exceeds buffer size", `BoundedByteArrayOutputStream.java:104-105`). With `length = -1`,
   `reset()` sets `limit = 65,536`.
3. Every key byte array written through that `DataOutputStream` (`TFile.append` at
   `TFile.java:396`, `LogKey.write` → `DataOutputStream.writeUTF`, `HistoryDataKey.write`) reaches
   `BoundedByteArrayOutputStream.write(byte[],int,int)`. The check
   [`BoundedByteArrayOutputStream.java:91`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/BoundedByteArrayOutputStream.java#L91)
   `if (currentPointer + len > limit)`:
   - **within the limit:** `System.arraycopy` into the pre-allocated array, `currentPointer += len`
     (`:95-96`). No allocation.
   - **past the limit:** `throw new EOFException("Reach the limit of the buffer")` (`:92`). The
     whole write is rejected (no partial copy). Single-byte writes have the same guard at `:76-77`.
4. When the key stream is closed (`KeyRegister.close`, `TFile.java:431-472`), the bytes buffered so
   far are written to the block appender (`TFile.java:450-451`); with `length >= 0` a short key is
   rejected ("Incorrect key length", `TFile.java:445-447`). The two buffers then swap roles
   (`TFile.java:465-467`).
5. **Behaviour at the limit, as traced:** in `TFile.append`, the `EOFException` leaves `errorCount`
   incremented (`TFile.java:395-397`), the `finally` still closes the key stream, which writes the
   truncated prefix (up to 64 KiB) to the block (`TFile.java:398-400`, `:450-451`), and
   `Writer.close` then skips the meta and index blocks because `errorCount != 0`
   (`TFile.java:308-336`), leaving an unreadable file on disk. So hitting the limit wastes disk
   rather than saving it. With the streaming API, the caller decides; a subsequent `Writer.close`
   in a non-READY state throws `IllegalStateException` (`TFile.java:309-311`).
6. **Bypass / overshoot:** none in memory terms — the array cannot grow, and without the check
   `System.arraycopy` would throw `ArrayIndexOutOfBoundsException` at the same point. `reset(int)`
   sets `limit = newlim` without adding `startOffset` (`:107`, versus `:71`); harmless in production
   because every production instance has `startOffset = 0`.
7. **Shuffle caller:** `unconditionalReserve` adds `mergeOutputSize` to `usedMemory` and allocates
   the merge buffer before writing (`MergeManagerImpl.java:310-314`, `:405-406`); the merged output
   (one EOF marker and one checksum instead of N) is never larger than the sum of its inputs
   (`MergeManagerImpl.java:620-645`), so line 91 is not expected to fire there. The memory-to-memory
   merge reserves the merge buffer while the inputs are still held, a transient overshoot of
   `memoryLimit` that is outside line 91's control.

**A4. Other consumers.** Of reducer heap: `MergeManagerImpl` in-memory map outputs (governed by
the shuffle keys above, with the documented one-thread overshoot at `MergeManagerImpl.java:281-293`),
merge iterators, user reduce code. Of NodeManager heap during log aggregation: the TFile value
path (`TFile.getChunkBufferSize`, `tfile.io.chunk.size`, default 1 MiB, `TFile.java:142-145`),
`BCFile` output buffers (`tfile.fs.output.buffer.size`, 256 KiB, `TFile.java:151-153`), the HDFS
client's packet buffers — all far larger than the 128 KiB of key buffers. Of disk/HDFS: aggregated
log files grow with container log volume (TFile values are unbounded), capped only by HDFS quotas,
retention (`yarn.log-aggregation.retain-seconds`) and NM-side policies.

**A5. Evidence beyond the source.**

- Unit tests in the tree confirm the mechanism (not memory):
  `hadoop-common/src/test/java/org/apache/hadoop/io/TestBoundedByteArrayOutputStream.java:40-90`
  (writing past the limit throws), and
  `hadoop-common/src/test/java/org/apache/hadoop/io/file/tfile/TestTFileStreams.java:313-350`
  (`testFailureKeyLongerThan64K` expects `IndexOutOfBoundsException` for `prepareAppendKey(64K+1)`;
  `testFailureKeyLongerThan64K_2` expects `EOFException` when streaming more than 64 KiB).
- TFile class javadoc, `TFile.java:55-58` ("Keys are restricted to 64KB").
- `yarn-default.xml:1608-1616` (`yarn.log-aggregation.file-formats` default `TFile`) and
  `YarnConfiguration.java:2826-2828` (aggregation compression default `none`).
- No JIRA relied on.

## B. Verification solution

**B1. Claim under test.** The limit checked at `BoundedByteArrayOutputStream.java:91` (for TFile,
`MAX_KEY_SIZE` = 64 KiB) does **not** govern memory or disk usage: the heap taken by a
`BoundedByteArrayOutputStream` equals its construction `capacity` and does not change with `limit`
or with the bytes written up to and past the limit, and the disk written through the TFile path
(YARN aggregated logs) follows the data volume, not the 64 KiB limit. The claim is refuted if heap
allocation tracks `limit` (at fixed capacity) or the bytes written, or if aggregated log size is
held near 64 KiB per key/container by this check.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 8 (HotSpot; `com.sun.management.ThreadMXBean` is used),
Maven 3.3+. Copy the tree to local disk, never build in a shared tree:
`rsync -a <pristine-source>/ $WORK/hadoop-3.4.2/` with `$WORK` on local disk (≥ 20 GB free).
Build the module and its dependencies once:
`cd $WORK/hadoop-3.4.2 && mvn -pl hadoop-common-project/hadoop-common -am install -DskipTests -Dmaven.javadoc.skip=true`.
New test file:
`hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/io/TestBoundedLimitMemory.java`
(package `org.apache.hadoop.io`, JUnit 4 as in the existing tests). JVM options: the module's
surefire defaults; add nothing else. Output goes to
`hadoop-common-project/hadoop-common/target/surefire-reports/org.apache.hadoop.io.TestBoundedLimitMemory-output.txt`
(`maven.test.redirectTestOutputToFile` is true, `hadoop-project/pom.xml:39`).

> **Amendment A1 (stage-4 audit, 2026-11-25, before any reading).** On Jingsong's stage-4 node (`pc99`) `$WORK` is
> `/mydata/jingsong-s4/MAX_KEY_SIZE-write-limit-2-run1/src`, made by `jingsong/copy-source.sh` from the repository's
> `systems/hadoop/source/` (tag `rel/release-3.4.2`). The `-am install` build is **not** run: the node's `~/.m2` already
> holds every 3.4.2 module (`environment.md` §3), and `install` would overwrite those shared artifacts; `mvn test` in the
> module compiles what it needs. JVM options are passed as `-Dmaven-surefire-plugin.argLine="-Xmx2048m
> -XX:+HeapDumpOnOutOfMemoryError -Difchk.tmp=<run-dir>/tmp"` (the module default of `hadoop-project/pom.xml:187` plus
> the scratch directory; `-DargLine` is ignored by this build, `:2469`). Surefire counts are read, not the exit code.
> The test is `harness/TestBoundedLimitMemory.java`, run by `harness/unit-run.sh`.

> **Amendment A9 (stage-4 audit, second attempt, 2026-11-25, before any reading).** The run moved from `pc99` (whose
> node lock was held, nothing ran) to **`pc91`** (`node0.jason92-326665`, `hadoop-base` built 2026-11-24): read `pc91`
> for `pc99` in A1 and A5; every path is otherwise the same. The argLine of A1 leaves out the module default's
> `${extraJavaTestArgs}` (`hadoop-project/pom.xml:172-187`: `-XX:+IgnoreUnrecognizedVMOptions` and JPMS `--add-opens`
> flags, which have no meaning on JDK 8); the heap and heap-dump options are the default's.

**B2b. Knobs.**

| Sub-test | Varied | Values | Why |
|---|---|---|---|
| U1 mechanism | `limit` at fixed `capacity` = 65,536 | 1,024; 32,768; 65,536 | below, middle, equal to TFile's `MAX_KEY_SIZE` |
| U2 heap vs limit | `limit` at fixed `capacity` = 1,048,576 | 1,024; 524,288; 1,048,576 | a capacity large enough that allocation is well above measurement noise |
| U3 positive control (capacity) | `capacity` with `limit = capacity` | 65,536; 1,048,576; 16,777,216 | shows the instrument sees allocations that do follow a size |
| U3b positive control (unbounded stream) | `java.io.ByteArrayOutputStream`, same writes | 200 × 1,024 B | memory that does follow bytes written |
| U4 TFile limit | key length through `prepareAppendKey(-1)` | 1 KiB; 64 KiB; 64 KiB + 1 KiB attempted | at, below and past `MAX_KEY_SIZE` |
| U5 TFile disk | records written (64 KiB key, 0-byte value) | 1; 10; 100 | disk follows record count, not the key limit |

All set in code (constructor arguments); `MAX_KEY_SIZE` itself is not a knob (hard-coded).

**B2c. Workload.** Writes of a fixed 1,000-byte chunk (U1, U2) or 1,024-byte chunk (U4) in a loop
until `EOFException`. U1: with limit L, the loop stops after `floor(L/1000)` writes (the next write
would make `currentPointer + 1000 > L`), so the limit is always reached and passed by one attempt.
U2: up to 1,048 writes of 1,000 B for L = 1,048,576. U4: 64 writes of 1,024 B fill the 65,536-byte
limit exactly; the 65th is rejected. U5: N appends of a 65,536-byte key and empty value with
`TFile.Writer(out, 64*1024, TFile.COMPRESSION_NONE, null, conf)` into a local file under
`target/test-dir`.

**B2d. Observables and instruments.**

- `alloc()` = `((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId())`,
  read before/after construction (`ctorAlloc`) and before/after the write loop (`writeAlloc`).
  Calibrate: the delta of two back-to-back `alloc()` calls (`baseline`) is subtracted. Each
  measurement is repeated 5 times after a warm-up of 20 unmeasured repetitions; report the median.
- Operand side: `stream.size()` and `stream.getLimit()` at the `EOFException`, number of successful
  writes, exception message.
- U4: exception class and message, the stack frame `BoundedByteArrayOutputStream.write` line 92.
- U5: `new File(path).length()` after `writer.close()`.
- Not observable directly: retained heap (only allocation is measured; retention is inferred from
  the array being a final reference in the object).

Test sketch (complete enough to type in):

```java
package org.apache.hadoop.io;

import java.io.*;
import java.lang.management.ManagementFactory;
import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.*;
import org.apache.hadoop.io.file.tfile.TFile;
import org.junit.Test;

public class TestBoundedLimitMemory {
  static final com.sun.management.ThreadMXBean T =
      (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
  static long alloc() { return T.getThreadAllocatedBytes(Thread.currentThread().getId()); }
  static final byte[] C1000 = new byte[1000], C1024 = new byte[1024];

  static long[] fill(int cap, int lim) throws IOException {   // U1/U2/U3
    long b0 = alloc(), b1 = alloc(), base = b1 - b0;
    long a0 = alloc(); BoundedByteArrayOutputStream s = new BoundedByteArrayOutputStream(cap, lim);
    long a1 = alloc(); int n = 0;
    try { while (true) { s.write(C1000, 0, 1000); n++; } } catch (EOFException e) { }
    long a2 = alloc();
    return new long[]{a1 - a0 - base, a2 - a1 - base, s.size(), s.getLimit(), n};
  }
  // @Test u1(): for lim in {1024,32768,65536}: print "U1 cap=65536 lim=.. size=.. writes=.."
  // @Test u2(): warm-up 20x fill(1<<20, lim); then 5x per lim in {1024,524288,1048576}; print medians
  // @Test u3(): same for cap in {65536,1<<20,1<<24}, lim=cap; and ByteArrayOutputStream with
  //             200 x write(C1024) -> print allocation delta
  // @Test u4(): TFile.Writer on FileSystem.getLocal(conf) file target/test-dir/u4-<k>.tfile;
  //             a0..a1 around the Writer constructor (ctorAlloc); DataOutputStream k = w.prepareAppendKey(-1);
  //             a2; loop write(C1024) up to 200 times catching EOFException; a3; print writes,
  //             exception message, a3-a2 (writeAlloc). Also: try w2.prepareAppendKey(65537) -> expect
  //             IndexOutOfBoundsException.
  // @Test u5(): for N in {1,10,100}: new Writer, N x w.append(new byte[65536], new byte[0]), close,
  //             print file length.
}
```

(For U4 each sub-case uses a fresh writer, because a key stream that hit the limit leaves the writer
unusable, A3 step 5.)

> **Amendment A2 (stage-4 audit, 2026-11-25, before any reading).** U4 uses the same warm-up as U2/U3 (20 unmeasured
> writers, then 5 measured; medians reported), as B2h requires ("only the medians after warm-up are compared"); the
> sketch had none for U4. U1 is one pass per limit (its readings are counts, not allocations). The stack frame of
> each `EOFException` is recorded as `class.method:line` of its top frame.

**B2e. Procedure.**

1. Build as in B2a.
2. Create the test file from the sketch.
3. `cd $WORK/hadoop-3.4.2 && mvn -pl hadoop-common-project/hadoop-common test -Dtest=TestBoundedLimitMemory`
4. Also run the existing tests as a sanity check:
   `mvn -pl hadoop-common-project/hadoop-common test -Dtest=TestBoundedByteArrayOutputStream,TestTFileStreams`
5. Collect the `U1`…`U5` lines from the surefire output file (B2a) into the readings table.
6. `rm -rf hadoop-common-project/hadoop-common/target/test-dir/u4-* .../u5-*` (or leave them inside
   the scratch copy; they are deleted with `$WORK`).

**B2f. Predictions.**

| Sub-test | Value | Prediction |
|---|---|---|
| U1 | lim = 1,024 / 32,768 / 65,536 | writes = 1 / 32 / 65; size at EOF = 1,000 / 32,000 / 65,000; message "Reach the limit of the buffer" |
| U2 | lim = 1,024 / 524,288 / 1,048,576 (cap 1 MiB) | `ctorAlloc` ≈ 1,048,576 + ~50 B header/object in all three, equal to each other within ±1 KiB; `writeAlloc` < 4 KiB in all three (only the exception object and stack trace) |
| U3 | cap = 64 KiB / 1 MiB / 16 MiB | `ctorAlloc` ≈ 65,6xx / 1,048,6xx / 16,777,2xx B (follows cap within ±1 KiB) |
| U3b | `ByteArrayOutputStream`, 204,800 B written | allocation ≥ 204,800 B (array doubling from 32 B makes it ≈ 2× the final 262,144-byte array) |
| U4 | key via `prepareAppendKey(-1)` | 64 writes succeed, 65th throws `EOFException` from line 92; `ctorAlloc` of `TFile.Writer` ≥ 131,104 B (two 64 KiB arrays); `writeAlloc` < 8 KiB; `prepareAppendKey(65537)` throws `IndexOutOfBoundsException` |
| U5 | N = 1 / 10 / 100 records of 64 KiB key | file length ≈ N × 65,5xx B + < 4 KiB metadata (≈ 66 KB / 656 KB / 6.6 MB), i.e. linear in N, unbounded by the 64 KiB limit |
| U5 (**A3**, 2026-11-25) | same | **Corrected arithmetic:** the TFile index keeps a copy of each data block's last key (`TFile.java:653-666`, `TFileIndexEntry` `:2310-2313`, written by `TFileIndex.write` `:2272-2289`) plus the first key, and with `minBlockSize` = 64 KiB every 64 KiB record closes its block (`finishDataBlock(false)`, `:504`). So file length ≈ (2N + 1) × 65,5xx B + < 4 KiB (≈ 197 KB / 1.38 MB / 13.2 MB). The relation is unchanged: linear in N, unbounded by the 64 KiB limit. "Linear" means the per-record slopes (len(10) − len(1)) / 9 and (len(100) − len(10)) / 90 agree within 5 % and len(100) ≥ 100 × 65,536 |

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| U2 `ctorAlloc` flat across limits, U3 `ctorAlloc` follows capacity, `writeAlloc` ≈ 0 | Claim confirmed: heap is fixed by capacity; the limit governs nothing in memory |
| U2 `ctorAlloc` or `writeAlloc` rises with `limit` at fixed capacity (e.g. ≥ 512 KiB difference between lim = 1,024 and lim = 1 MiB) | Claim refuted: usage follows the limit |
| `writeAlloc` grows with bytes written before the EOF (≳ size at EOF) | Claim refuted: the stream buffers dynamically and the check caps growth |
| U3/U3b deltas do not move (instrument blind) | Not confirmed: positive control failed; fix the instrument (e.g. run with `-XX:-UseTLAB` or check JDK vendor) before reading U2 |
| U1/U4 never throw (limit never reached) | Not confirmed: workload did not reach the limit; fix the loop |
| U5 file length capped near 64 KiB regardless of N | Claim refuted for disk |
| U5 linear in N | Disk follows data volume, not the key limit (confirms) |
| (**A4**, 2026-11-25) U1 or U4 fails at another index, with another exception, or the top frame is not `BoundedByteArrayOutputStream.write:92` | Not confirmed: the mechanism differs from A3; feedback to stage 3 |
| (**A4**) U2 `ctorAlloc` spread between 1 KiB and 512 KiB, or `writeAlloc` between 4 KiB and the size at EOF | Not confirmed: neither the confirm nor the refute row holds; record the readings |
| (**A4**) a `TestBoundedLimitMemory` method errors, or the existing tests (B2e step 4) fail | Invalid run: fix the instrument and restart the tier |

> **A4 (stage-4 audit, 2026-11-25, before any reading):** the three rows above were added so that every plausible
> outcome has a row. "Claim confirmed" (row 1) needs all of: U2 and U3 within B2f's bounds, U3b ≥ 204,800, U1 and U4 at
> the predicted indices with the frame `write:92`, and U5 linear (A3).

**B2h. Controls.** U3 and U3b are positive controls for the instrument (allocation that follows a
size). Baseline calibration of `alloc()` removes the cost of the probe. Warm-up removes JIT and class
loading allocations (first `TFile.Writer` construction loads classes; only the medians after warm-up
are compared). Running each sub-case on the same thread with no other test in the JVM (`-Dtest=`
one class) avoids cross-thread noise (the counter is per-thread anyway). The existing tests in step 4
confirm the checked-out code behaves as the in-tree tests expect.

### B3. Cluster tier

`MAX_KEY_SIZE` cannot be set on a running cluster; the cluster tier therefore varies the workload
and checks that the real resource on the TFile path (aggregated log bytes on HDFS, written by the
NodeManager through `TFile.Writer`, whose every key write passes line 91) follows the data and not the
64 KiB limit, that the check never fires, and that a real cap (HDFS space quota) does bind the same
workload. A secondary workload exercises the other production caller (memory-to-memory merge).

> **Amendment A10 (stage-4 audit, second attempt, 2026-11-25, before any reading).** Scope of this tier, stated so the
> gap is named: the keys that log aggregation writes through `TFile` are short strings (`VERSION`, `APPLICATION_ACL`,
> `APPLICATION_OWNER`, container IDs; tens of bytes, `AggregatedLogFormat.java:150`, `:505-541`), so on the cluster the
> quantity compared at line 91 never approaches 64 KiB and the disallow branch cannot fire there by design. "Past the
> limit" in this tier means the data volume through the TFile path (up to 2,048 × 64 KiB), not the key length. The
> cluster tier therefore tests the disk half of B1 only (disk on the TFile path follows the data and is not held near
> 64 KiB by this check); the evidence that the check fires and allocates nothing is the unit tier's (U1, U2, U4). The
> B3f predictions and B3g rows are unchanged.

**B3a. Environment and build.**

- One Linux host, pseudo-distributed: NameNode, DataNode, ResourceManager, NodeManager (JobHistory
  server optional, not needed). ≥ 8 GB RAM, ≥ 20 GB free local disk under `$S4` (e.g. `/mydata/<run>`).
- Build the distribution from a local copy of the tag:
  `cd $WORK/hadoop-3.4.2 && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`;
  unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `$S4/hadoop`; `export HADOOP_HOME=$S4/hadoop
  HADOOP_CONF_DIR=$S4/conf HADOOP_LOG_DIR=$S4/logs HADOOP_PID_DIR=$S4/pids`; copy
  `$HADOOP_HOME/etc/hadoop/*` to `$S4/conf`.
- `hadoop-env.sh`: `export JAVA_HOME=<jdk8>`, `export HADOOP_HEAPSIZE_MAX=1g`,
  `export HADOOP_LOG_DIR=$S4/logs`, `export HADOOP_PID_DIR=$S4/pids`.
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=$S4/tmp`.
- `hdfs-site.xml`: `dfs.replication=1`, `dfs.namenode.name.dir=$S4/nn`,
  `dfs.datanode.data.dir=$S4/dn`, `dfs.blocksize=1048576` (so the 32 MiB quota in the positive
  control is not swallowed by a 128 MiB block reservation).
- `yarn-site.xml`: `yarn.nodemanager.aux-services=mapreduce_shuffle`,
  `yarn.nodemanager.env-whitelist=JAVA_HOME,HADOOP_COMMON_HOME,HADOOP_HDFS_HOME,HADOOP_CONF_DIR,CLASSPATH_PREPEND_DISTCACHE,HADOOP_YARN_HOME,HADOOP_HOME,PATH,LANG,TZ,HADOOP_MAPRED_HOME`,
  `yarn.log-aggregation-enable=true`, `yarn.nodemanager.remote-app-log-dir=/tmp/logs`
  (format stays the default `TFile`; suffix becomes `logs-tfile`),
  `yarn.nodemanager.local-dirs=$S4/nm-local`, `yarn.nodemanager.log-dirs=$S4/nm-logs`,
  `yarn.nodemanager.resource.memory-mb=4096`, `yarn.scheduler.minimum-allocation-mb=256`,
  `yarn.nodemanager.vmem-check-enabled=false`.
- `mapred-site.xml`: `mapreduce.framework.name=yarn`,
  `mapreduce.application.classpath=$HADOOP_MAPRED_HOME/share/hadoop/mapreduce/*:$HADOOP_MAPRED_HOME/share/hadoop/mapreduce/lib/*`.
- Changes to these files need a daemon restart; the quota in B3e is applied live with
  `hdfs dfsadmin`.

> **Amendment A5 (stage-4 audit, 2026-11-25, before any reading).** On `pc99`: `$S4` =
> `/mydata/jingsong-s4/MAX_KEY_SIZE-write-limit-2-run1`; the distribution is **copied** from the node's built
> `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` (same tag, `environment.md` §3–4), not rebuilt.
> Daemons are started and stopped with `hdfs --daemon start|stop namenode|datanode` and `yarn --daemon start|stop
> resourcemanager|nodemanager`: `start-dfs.sh`/`start-yarn.sh` need SSH to `localhost`, which does not work on these
> nodes (`environment.md`). No SecondaryNameNode (B3e step 1's `jps` list therefore has four daemons).
> `yarn.nodemanager.delete.debug-delay-sec=600` is in `yarn-site.xml` from the start (B3d). `mapred-site.xml` also sets
> `yarn.app.mapreduce.am.env`, `mapreduce.map.env`, `mapreduce.reduce.env` = `HADOOP_MAPRED_HOME=$S4/hadoop` so the
> MapReduce AM finds its classes. The script is `harness/cluster-run.sh`.

**B3b. Knobs.**

| Knob | Values | How | Why |
|---|---|---|---|
| Container stdout volume `N` (distributed shell) | 1 MiB; 16 MiB; 64 MiB | `-shell_command` argument | spans 16× to 1,024× the 64 KiB limit |
| HDFS space quota on `/tmp/logs` (positive control) | none; 32 MiB | `hdfs dfsadmin -setSpaceQuota 32m /tmp/logs` / `-clrSpaceQuota` (live) | a cap known to bind aggregated-log disk |
| `mapreduce.reduce.merge.memtomem.enabled` (secondary workload) | true | `-D` on the job | the only path where the shuffle buffer's `write` (line 91) runs |

`MAX_KEY_SIZE` stays 65,536 (not settable).

**B3c. Workload.**

- **A (primary, TFile path):** distributed shell, 2 containers, each printing `N` bytes:
  ```
  yarn jar $HADOOP_HOME/share/hadoop/yarn/hadoop-yarn-applications-distributedshell-3.4.2.jar \
    -jar $HADOOP_HOME/share/hadoop/yarn/hadoop-yarn-applications-distributedshell-3.4.2.jar \
    -shell_command "head -c $N /dev/zero | tr '\\0' a" -num_containers 2 -container_memory 256
  ```
  Each container's `stdout` is `N` bytes; on app finish the NodeManager aggregates the AM's and both
  containers' logs into one TFile per node (`/tmp/logs/$USER/logs-tfile/<bucket>/<appId>/<host>_<port>`);
  each log is written as TFile value bytes, the key is the container ID string (≈ 40 B, through
  `DataOutputStream.writeUTF` → line 91). Arithmetic: for N = 64 MiB the aggregated file must hold
  ≥ 2 × 67,108,864 = 134,217,728 B, 2,048× the 64 KiB key limit. Duration: < 2 min per run.
- **A-control:** the same N = 64 MiB run with a 32 MiB space quota on `/tmp/logs`.

> **Amendment A6 (stage-4 audit, 2026-11-25, before any reading).** The shell command is `head -c $N /dev/zero` (no
> `tr`): the `'\\0'` quoting above passes through the DS client, the AM and `launch_container.sh` and is not exact. The
> content does not matter (compression is `none`). The read-back in B3d counts the NUL bytes of `yarn logs
> -applicationId <appId> -containerId <cid> -log_files stdout` (`| tr -cd '\000' | wc -c`), which excludes the header
> lines `yarn logs` adds; it is done for both worker containers (`…_01_000002`, `…_01_000003`). The aggregated
> directory in 3.4.2 is `/tmp/logs/$USER/bucket-logs-tfile/<bucket>/<appId>` (`LogAggregationUtils.java:160-165`);
> it is found by its appId.
- **B (secondary, shuffle path):** 20 input files of 1 MiB text,
  `hadoop jar $HADOOP_HOME/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.2.jar wordcount
  -D mapreduce.job.reduces=1 -D mapreduce.reduce.merge.memtomem.enabled=true
  -D mapreduce.reduce.merge.memtomem.threshold=5 /in /out-b`. 20 small map outputs all fit in memory
  (default reducer heap; each ≪ 25 % of 70 % of heap), and the mem-to-mem merger starts once 5 are
  held (`MergeManagerImpl.java:341-342`).

**B3d. Observables and instruments.**

- Aggregated bytes: `hdfs dfs -du -s /tmp/logs/$USER/logs-tfile/*/<appId>` after the app reaches
  FINISHED and `yarn application -status <appId>` shows `Log Aggregation Status : SUCCEEDED`
  (or FAILED in the control).
- Local raw logs for comparison: `du -sb $S4/nm-logs/<appId>` before aggregation completes (set
  `yarn.nodemanager.delete.debug-delay-sec=600` in `yarn-site.xml` to keep them).
- Check firing: `grep -c "Reach the limit of the buffer" $S4/logs/*nodemanager*.log` and in
  `yarn logs -applicationId <appId>` output; for workload B also
  `grep -E "Initiating Memory-to-Memory merge|Memory-to-Memory merge of the" ` in the reducer syslog
  (`yarn logs -applicationId <appId> -log_files syslog`).
- Readability: `yarn logs -applicationId <appId> -containerId <cid> -log_files stdout | wc -c`.
- NodeManager heap: `jstat -gc <NM pid> 1000` across the aggregation, for the record only.
- Not observable: the 2 × 64 KiB key buffers of a `LogWriter` inside the NodeManager heap (≪ the
  GC noise of a 1 GiB heap and short-lived); the claim about heap rests on the unit tier.

> **Amendment A11 (runbook defect 1, run 1, 2026-11-25; B3f/B3g unchanged).** The memory-to-memory merge lines
> (`MergeManagerImpl.java:411`, `:426`) are not in the reducer's `syslog`: the container log4j configuration sends the
> `org.apache.hadoop.mapreduce.task.reduce` loggers to a separate file, `syslog.shuffle`
> (`hadoop-yarn-server-nodemanager/src/main/resources/container-log4j.properties:16, 47-56`; `MRApps.java:662`). Read
> the merge lines and the "Reach the limit of the buffer" count for workload B from both `syslog` and `syslog.shuffle`
> (`yarn logs -applicationId <appId> -log_files syslog` and `... -log_files syslog.shuffle`). The cluster tier restarts
> from B3e step 1 on a fresh format.

**B3e. Procedure.**

1. Format and start: `hdfs namenode -format -nonInteractive`; `start-dfs.sh`; `start-yarn.sh`;
   `jps` shows NameNode, DataNode, SecondaryNameNode, ResourceManager, NodeManager.
2. `hdfs dfs -mkdir -p /tmp/logs /user/$USER && hdfs dfs -chmod 1777 /tmp/logs`.
3. Workload A for N = 1,048,576, 16,777,216, 67,108,864 (one run each). After each: wait for
   aggregation SUCCEEDED; record `hdfs dfs -du -s`, `du -sb` of local logs, `grep -c` of the limit
   message, and `yarn logs ... -log_files stdout | wc -c` for one worker container.
4. Positive control: `hdfs dfsadmin -setSpaceQuota 32m /tmp/logs`; rerun workload A with
   N = 67,108,864; record the same, plus `grep -E "DSQuotaExceeded|quota" $S4/logs/*nodemanager*.log`;
   then `hdfs dfsadmin -clrSpaceQuota /tmp/logs`.

   > **Amendment A7 (stage-4 audit, 2026-11-25, before any reading).** Before setting the quota, record the A runs
   > (step 3), then delete `/tmp/logs/$USER` (`hdfs dfs -rm -r -skipTrash`): with the ≈ 170 MB of the A runs still
   > under `/tmp/logs`, a 32 MiB quota would be exceeded before the control app wrote anything, and the control would
   > not show a cap binding at 32 MiB. Also record `hdfs dfs -count -q /tmp/logs` before and after, and the
   > NodeManager's `DSQuotaExceededException` line (it names the quota and the consumed bytes).
5. Workload B: `for i in $(seq -w 1 20); do head -c 1048576 /dev/urandom | base64 > $S4/in-$i.txt; done;
   hdfs dfs -mkdir /in && hdfs dfs -put $S4/in-*.txt /in`; run the job; record the merge lines and
   `grep -c "Reach the limit of the buffer"`; job must succeed.
6. Stop and clean up per B4.

**B3f. Predictions.**

| Run | Prediction |
|---|---|
| A, N = 1 MiB | aggregated size ≈ 2 × 1,048,576 B + AM logs + < 64 KiB TFile overhead ≈ 2.1–2.3 MB; limit message count 0; `stdout` read back = 1,048,576 B |
| A, N = 16 MiB | ≈ 33.6–34 MB; count 0; read back 16,777,216 B |
| A, N = 64 MiB | ≈ 134.3–135 MB; count 0; read back 67,108,864 B |
| Relation | aggregated size grows linearly with N (slope ≈ 2, the number of worker containers) and is never capped near 64 KiB |
| A-control (quota 32 MiB) | aggregated bytes ≤ 33,554,432; aggregation status FAILED (or partial); NM log shows `DSQuotaExceededException`; limit message count 0 |
| B | ≥ 1 "Initiating Memory-to-Memory merge" line; 0 "Reach the limit of the buffer"; job SUCCEEDED |

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Aggregated size linear in N, ≫ 64 KiB, limit message 0, control caps at ≤ 32 MiB | Claim confirmed: disk on the TFile path follows the data and is capped by a real limit (quota), not by line 91 |
| Aggregated size or read-back stdout held near 64 KiB per container, or "Reach the limit of the buffer" appears | Claim refuted: the check is truncating and so bounding what is written |
| Size linear in N but the quota control also does not cap | Not confirmed: the positive control failed (quota not applied, block reservation, wrong path) |
| Aggregation not SUCCEEDED in A runs / no TFile written | Not confirmed: the TFile path (and line 91) was not exercised; check `yarn.log-aggregation-enable` |
| B: no memory-to-memory merge lines | Not confirmed for the shuffle caller: line 91 not reached; lower `memtomem.threshold` or add input files |
| B: limit message appears / job fails with `EOFException` | The shuffle merge buffer was undersized: a bug, and evidence the check binds there (refutes for that caller) |

> **Amendment A8 (stage-4 audit, 2026-11-25, before any reading).** Numbers for row 1: "linear in N" means the slopes
> (agg(16 MiB) − agg(1 MiB)) / 15 MiB and (agg(64 MiB) − agg(16 MiB)) / 48 MiB both lie in [1.9, 2.1] (two worker
> containers); "≫ 64 KiB" means agg ≥ 2 × N for every N; the read-back of each worker's `stdout` equals N exactly; the
> control "caps" means aggregated bytes for the control app ≤ 33,554,432, its aggregation status is not SUCCEEDED, and
> at least one `DSQuotaExceededException` appears in the NodeManager log during the control. Workload B is a secondary
> check of the other caller: it neither confirms nor refutes the TFile claim on its own; its "no merge lines" row leaves
> the tier's verdict to workload A and the control. Gap named: that line 91 runs for each aggregated key
> (`LogKey.write` → `writeUTF` → `write(byte[],int,int)`, `AggregatedLogFormat.java:150`, `:505-541`) is inferred
> from the code path; no probe counts it on the cluster.

**B3h. Controls.** The HDFS space-quota run is the positive control (the same workload, a cap
known to bind). Comparing the aggregated size with local `du -sb` of the raw container logs rules out
loss elsewhere (compression is `none` by default, `YarnConfiguration.java:2828`). The read-back of
`stdout` checks the content is complete, not merely the file size. Running each N on a fresh
application and measuring per-app directories avoids counting earlier runs.

**B4. Risks and cleanup.**

- Unit tier: files only under the scratch copy's `target/`; no daemons. Delete `$WORK` when done if
  space is needed.
- Cluster tier: all data under `$S4` on local disk (`nn`, `dn`, `tmp`, `nm-local`, `nm-logs`,
  `logs`, `pids`); about 0.5 GB of HDFS data (aggregated logs ≈ 170 MB + inputs 27 MB). Ports in use:
  9000, 9870, 9864/9866/9867, 8088, 8030-8033, 8040/8042, 13562; check they are free first
  (`ss -ltn`), and do not run beside another pseudo-distributed cluster on the same ports.
- Stop: `stop-yarn.sh; stop-dfs.sh` (and `mapred --daemon stop historyserver` if started); `jps`
  must show none of the daemons; kill any leftover `DistributedShell`/`YarnChild` JVMs. Remove the
  quota if a run aborted (`hdfs dfsadmin -clrSpaceQuota /tmp/logs`) before stopping. Then
  `rm -rf $S4`.

## C. Sources read

- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/BoundedByteArrayOutputStream.java
- hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/io/TestBoundedByteArrayOutputStream.java
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/file/tfile/TFile.java (lines 50-160, 210-560, 1223-1300, 1595-1610)
- hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/io/file/tfile/TestTFileStreams.java (lines 205-350)
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/task/reduce/InMemoryMapOutput.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/task/reduce/InMemoryWriter.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/task/reduce/MergeManagerImpl.java (lines 93-100, 165-345, 370-450, 620-645)
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/IFileOutputStream.java (lines 37-98)
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MRJobConfig.java (grep: REDUCE_MEMTOMEM_ENABLED, REDUCE_MEMORY_TOTAL_BYTES)
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/resources/mapred-default.xml (shuffle keys)
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-common/src/main/java/org/apache/hadoop/yarn/logaggregation/AggregatedLogFormat.java (lines 110-145, 455-530)
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-common/src/main/java/org/apache/hadoop/yarn/logaggregation/filecontroller/LogAggregationFileController.java (lines 185-195, 340-356)
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-common/src/main/java/org/apache/hadoop/yarn/logaggregation/filecontroller/tfile/LogAggregationTFileController.java (lines 80-120)
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-common/src/main/java/org/apache/hadoop/yarn/logaggregation/LogAggregationUtils.java (grep: bucket dirs)
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-common/src/main/resources/yarn-default.xml (log-aggregation keys)
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-api/src/main/java/org/apache/hadoop/yarn/conf/YarnConfiguration.java (lines 2826-2828)
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-applicationhistoryservice/src/main/java/org/apache/hadoop/yarn/server/applicationhistoryservice/FileSystemApplicationHistoryStore.java (lines 735-765)
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-applications/hadoop-yarn-applications-distributedshell/src/main/java/org/apache/hadoop/yarn/applications/distributedshell/Client.java (option names)
- hadoop-project/pom.xml (line 39)
- BUILDING.txt (lines 1-12, 360-370)

## D. Stage-4 feedback

**D1. Stage-4 audit amendments (2026-11-25, before any reading).** A1 (node paths, no `install`, surefire options),
A2 (U4 warm-up, frame recorded), A3 (U5 arithmetic: the TFile index stores each block's last key), A4 (missing
B2g rows), A5 (node cluster setup, `--daemon`), A6 (DS command without `tr`, read-back counts NUL bytes, bucket path),
A7 (control: clear `/tmp/logs/$USER` before the quota), A8 (numbers for B3g row 1, workload B's role, the inferred
line-91 path). None changes B1's claim. A3 corrects a prediction for a reason that does not depend on any reading.

**D1a. Second attempt (2026-11-25, before any reading).** A9 (node `pc91` instead of `pc99`; the JPMS flags left out of
the argLine), A10 (the cluster tier's scope: keys stay tens of bytes, so the check cannot fire there; the tier tests
disk only). Neither changes B1's claim, a prediction or a conclusions row.

**D1b. Runbook defect 1 (run 1, 2026-11-25).** A11: workload B's merge lines are in `syslog.shuffle`, not `syslog`;
the cluster tier was restarted from B3e step 1. B3f/B3g unchanged.

**D2. Stage-4 result (2026-11-25, run 1 + self-check, node `pc91`; results file
`results/MAX_KEY_SIZE-write-limit-2--autonomous.md`).** Unit tier **Confirmed — does not cap** (B2g row 1 and the U5
"linear in N" row): at capacity 1 MiB the constructor allocated 1,048,624 B for `limit` = 1 KiB, 512 KiB and 1 MiB
alike (spread 0), the write loop allocated a flat 3,920 B (the `EOFException`) whether 1,000 or 1,048,000 bytes were
written; U3 followed capacity (65,584 / 1,048,624 / 16,777,232 B); the check fired at `write:92` at the predicted index
in U1 and U4; U5 TFile length 196,774 / 1,376,603 / 13,174,973 B for N = 1 / 10 / 100 (131,092 vs 131,093 B per record,
as A3). Cluster tier **Confirmed — does not cap** (B3g row 1, disk only per A10): aggregated TFile bytes 2,124,024 /
33,581,369 / 134,245,028 for N = 1 / 16 / 64 MiB (slopes 2.000004 and 2.000007), every worker's stdout read back
exactly, 0 "Reach the limit of the buffer"; the 32 MiB space quota held the control app's aggregated file at
33,554,432 B with aggregation FAILED and 12 `DSQuotaExceededException` lines. Workload B: 8 memory-to-memory merges,
job SUCCEEDED, 0 limit messages. Outcome class: **true negative**. Runbook defect 1 (A11) fixed and the cluster tier
restarted. Side finding: with 64 KiB keys and `minBlockSize` 64 KiB the TFile index holds a second copy of every key
(file ≈ 2 × the key bytes), per A3.
