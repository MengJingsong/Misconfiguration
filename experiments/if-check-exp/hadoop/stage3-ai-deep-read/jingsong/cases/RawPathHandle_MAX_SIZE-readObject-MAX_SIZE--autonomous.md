# RawPathHandle_MAX_SIZE — verification solution  <!-- file: cases/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`RawPathHandle.java:107`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/RawPathHandle.java#L107), `if (len < 0 \|\| len > MAX_SIZE)` in `RawPathHandle.readObject` |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-06 |
| Estimate | `positive`: the check runs before `new byte[len]` (`RawPathHandle.java:107-110`), so a Java-deserialized `RawPathHandle` can never allocate a payload array larger than `MAX_SIZE` = 1,048,576 bytes of heap, whatever length the stream claims. The cap is narrow. It covers one object's deserialization buffer. Nothing in a stock Hadoop daemon Java-deserializes a `RawPathHandle`, and the cap does not cover the constructors or the total across many objects. |
| Ground | — |

Stem parts: constraint `RawPathHandle_MAX_SIZE` (the bare name `MAX_SIZE` is also declared in `org.apache.hadoop.ipc.RPC.RpcKind`, `RPC.java:93`, so the name is qualified with its class), function `readObject`, operand `MAX_SIZE`.

## A. Constraint trace

**A1. The constraint.** `MAX_SIZE` in `org.apache.hadoop.fs.RawPathHandle`. Kind: a hard-coded constant, `public static final int MAX_SIZE = 1 << 20;`, declared at [`RawPathHandle.java:40`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/RawPathHandle.java#L40). Unit: bytes. Value: 1,048,576 (1 MiB). There is no configuration key, no `*-default.xml` entry and no JVM property, so nothing has to win between a Java default and an XML value. It cannot be set at runtime. Changing it means editing the source and rebuilding `hadoop-common`. It is read by whichever JVM Java-deserializes a `RawPathHandle` (`java.io.ObjectInputStream` → `RawPathHandle.readObject`). In 3.4.2 that is client or application code (for example a framework that ships `PathHandle`s between JVMs with Java serialization, or Hadoop's `JavaSerialization`). No stock Hadoop daemon path does this (see A3/A4).

**A2. What it caps.** JVM heap in the deserializing process. The quantity compared is `len`, the payload length the serialized stream declares (`in.readInt()`, `RawPathHandle.java:106`). If the check passes, exactly `len` bytes are allocated as a `byte[]` (`RawPathHandle.java:110`) and kept as the handle's `fd` (`RawPathHandle.java:112`). So for each deserialized handle, payload heap is at most 1 MiB plus array/object headers.

**A3. Mechanism.**
1. `writeObject` (`RawPathHandle.java:91-101`) writes `defaultWriteObject()` (no non-transient instance fields, since `fd` is `transient`, `RawPathHandle.java:42`), then `fd.remaining()` as an int, then the payload bytes. **There is no size check on the write side.** A handle built from a `ByteBuffer` of any size serializes successfully.
2. `readObject` (`RawPathHandle.java:103-113`) reads `len = in.readInt()` (`:106`).
3. The check, [`RawPathHandle.java:107`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/RawPathHandle.java#L107): `if (len < 0 || len > MAX_SIZE)`.
   - If true (limit exceeded or negative): `throw new IOException("Illegal buffer length " + len)` (`:108`). **No array is allocated.** The exception propagates out of `ObjectInputStream.readObject`, and the caller gets no object.
   - If false: `byte[] x = new byte[len]` (`:110`), then `in.readFully(x)` (`:111`), then `fd = ByteBuffer.wrap(x)` (`:112`).
4. Overshoot and bypass paths:
   - The allocation happens before `readFully`. A stream that claims `len = MAX_SIZE` but is truncated still costs 1 MiB before the `EOFException`. The cap is on the claimed length, so it still holds.
   - The cap is per object. A stream with N handles can hold N × 1 MiB. Nothing bounds the total.
   - The constructors `RawPathHandle(ByteBuffer)` (`:48-52`, keeps a read-only view and copies nothing) and `RawPathHandle(PathHandle)` (`:58-65`, `ByteBuffer.allocate(hb.remaining())` with no bound) never consult `MAX_SIZE`.
   - The asymmetry: a handle larger than 1 MiB can be written but not read back.
   - `readObjectNoData` (`:115-117`) throws `InvalidObjectException`, so the class cannot be deserialized without data.

**A4. Other consumers.**
- Production users of `RawPathHandle` in 3.4.2 are the HDFS PROVIDED-storage DataNode code. It builds handles through the unbounded `ByteBuffer` constructor from alias-map nonces: `FinalizedProvidedReplica.java:56` and `ProvidedVolumeImpl.java:186`. Those nonces come from, for example, Base64 fields in the text alias map (`TextFileRegionAliasMap.java:360-366`). These handles are never Java-deserialized, so `MAX_SIZE` does not bound them.
- The contract tests wrap `FileSystem.getPathHandle` bytes the same way (`AbstractContractPathHandleTest.java:247`).
- Other heap users in a deserializing JVM (the `ObjectInputStream` block buffer, handle tables, other objects in the same stream) are outside this constraint.
- `PathHandle extends Serializable` (`PathHandle.java:34`), which is why Java deserialization is a supported path at all.

**A5. Evidence beyond the source.**
- Filesystem specification for `PathHandle`/`getPathHandle`: `hadoop-common/src/site/markdown/filesystem/filesystem.md:852-870` (https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-common/filesystem/filesystem.html).
- The PathHandle API came in with the HDFS-7878 / HDFS-12882 / HADOOP-15106 / HADOOP-15117 series (Hadoop 3.1.0 changelog, `CHANGELOG.3.1.0.md:124-138,625`), for example https://issues.apache.org/jira/browse/HDFS-12882.
- No test in the tree exercises `MAX_SIZE` (grep shows no reference outside `RawPathHandle.java`).

## B. Verification solution

**B1. Claim under test.** Java-deserializing a `RawPathHandle` allocates a payload `byte[]` of exactly the declared length when `0 ≤ len ≤ 1,048,576`. For any declared length outside that range it allocates no payload array and throws `IOException("Illegal buffer length <len>")`, so per-call heap allocation stays well under the declared length (and under 1 MiB) even when the stream claims up to 2^31−1 bytes.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 8 (HotSpot, which is needed for `com.sun.management.ThreadMXBean`), Maven 3.3+.
- Copy the tree to local disk: `rsync -a ~/hadoop-3.4.2/ /mydata/<you>/hadoop-s4/` (never build in the shared copy).
- Build: `cd /mydata/<you>/hadoop-s4 && mvn -pl hadoop-common-project/hadoop-common -am install -DskipTests -Dmaven.javadoc.skip=true`.
- New test in the copy: `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/fs/TestRawPathHandleMaxSize.java` (JUnit 4, as the module uses).
- JVM options: run with a small heap so an unchecked huge allocation would fail loudly. Use `-Dmaven-surefire-plugin.argLine="-Xmx256m"`, which overrides the default `-Xmx2048m` from `hadoop-project/pom.xml:187`.

> **Amendment A1 (2026-11-06, stage-4 audit, before any reading) — node paths, build and JVM options.** On the stage-4 node (`pc39`, Jingsong's
> `environment.md`) the working tree is `/mydata/jingsong-s4/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE-run1/src`, made with
> `jingsong/copy-source.sh` (not `~/hadoop-3.4.2`, not `/mydata/<you>/hadoop-s4`). No `install` build is needed: the 3.4.2 artifacts
> are in `~/.m2`, and `mvn test` in `hadoop-common-project/hadoop-common` compiles that module's own main and test sources from the copy.
> JDK 8 is `/usr/lib/jvm/java-8-openjdk-amd64` (export `JAVA_HOME`). Surefire options are passed as
> `-Dmaven-surefire-plugin.argLine="-Xmx256m -XX:+UseSerialGC"` (the module's surefire `argLine` is
> `${maven-surefire-plugin.argLine} -DminiClusterDedicatedDirs=true`, `hadoop-common/pom.xml:1035`; `-DargLine` is ignored). This replaces
> the default `-Xmx2048m -XX:+HeapDumpOnOutOfMemoryError` (`hadoop-project/pom.xml:187`), so the control's `OutOfMemoryError` writes no
> heap dump. The build returns 0 on failing tests: read the surefire counts. Harness: `jingsong/harness/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous/`
> (`TestRawPathHandleMaxSize.java`, `unit-run.sh`, `analyze.py`).

**B2b. Knobs.** `MAX_SIZE` is a constant and cannot be changed without a code change, so the varied value is the **declared length `len`** in the stream. Use these values:

| ID | `len` | How the stream is made |
|---|---|---|
| L0 | 0 | |
| L1 | 1,024 | |
| L2 | 1,048,575 (MAX_SIZE−1) | |
| L3 | 1,048,576 (= MAX_SIZE) | |
| L4 | 1,048,577 (MAX_SIZE+1) | |
| L5 | 16,777,216 (16 MiB) | |
| L6 | 2,147,483,647 (Integer.MAX_VALUE) | |
| L7 | −1 | |

Streams:
- L0–L5: a genuine `ObjectOutputStream` serialization of `new RawPathHandle(ByteBuffer.wrap(new byte[len]))` filled with a pattern (`i & 0xff`). The write side has no check, so L4/L5 serialize fine.
- L6/L7: serialize a handle with sentinel length 0x00012345 (74,565 bytes, all zero payload). Find the first occurrence of the four bytes `00 01 23 45` in the stream (the `writeInt` value, which precedes the payload). Overwrite it with `7F FF FF FF` (L6) or `FF FF FF FF` (L7). Assert that the sentinel occurs exactly once before patching.

Optional (an optional knob, a second build): set `MAX_SIZE = 1 << 16` in a separate copy and re-run L0–L6. The boundary should move to 65,536, which shows the constant (not something else) sets the boundary.

> **Amendment A2 (2026-11-06, stage-4 audit, before any reading) — the knob is varied (three builds), and one same-shape over-limit row.** `MAX_SIZE` can be varied by
> editing line 40 in the run copy; `mvn test` recompiles it. The optional `1<<16` build becomes required, and a third value is added, so the
> constant takes three values including the default. Arms, run in this order in the same copy, each with `-Difchk.arm=<arm> -Difchk.max=<M>`:
>
> | Arm | Line 40 | M | RawPathHandle rows (`g` = genuine serialization of a handle of that length, `p` = sentinel stream patched to that length) |
> |---|---|---|---|
> | D (default) | `1 << 20` (as shipped) | 1,048,576 | L0 g 0, L1 g 1,024, L2 g M−1, L3 g M, L4 g M+1, L5 g 16,777,216, L6 p 2,147,483,647, L7 p −1, **L8 p 67,108,864 (new)** |
> | K16 | `1 << 16` | 65,536 | g 0, g 1,024, g M−1, g M, g M+1, g 1,048,576, p 2,147,483,647, p −1 |
> | K24 | `1 << 24` | 16,777,216 | g 0, g 1,024, g M−1, g M, g M+1, p 67,108,864, p 2,147,483,647, p −1 |
>
> The arm D JavaSerialization rows (J3 = L3, J4 = L4) and the positive control (A6) run in arm D only. The patch is
> `sed -i 's/MAX_SIZE = 1 << 20;/MAX_SIZE = 1 << <k>;/'` on `RawPathHandle.java`, checked with `git diff` (one line), and undone with
> `git checkout -- <file>` after the arm; the test logs `RawPathHandle.MAX_SIZE` read by reflection and stops if it is not M. L8 (a
> truncated stream claiming 64 MiB) is the same stream shape as control row C8, so the checked and unchecked readers are compared on
> identical input.

**B2c. Workload.** For each length, deserialize the bytes with `new ObjectInputStream(new ByteArrayInputStream(bytes)).readObject()`. Repeat it 20 times after 5 warm-up runs. Also run L3 and L4 once through Hadoop's own serializer: create a `Configuration` with `io.serializations=org.apache.hadoop.io.serializer.JavaSerialization`, get `SerializationFactory.getDeserializer(RawPathHandle.class)`, and use `JavaSerialization.java:47-63`, which has no stream header. Write the bytes with the matching `getSerializer`. Arithmetic: L3 allocates exactly 2^20 bytes (limit reached). L4 is 1 byte past it, L5 16× past, L6 2048× past.

**B2d. Observables and instruments.**
- (1) Outcome: returned object vs. exception type and message.
- (2) For success: `h.bytes().remaining()` and content equality with the source pattern.
- (3) Bytes allocated by the deserializing thread. Cast `ManagementFactory.getThreadMXBean()` to `com.sun.management.ThreadMXBean` and read `getThreadAllocatedBytes(Thread.currentThread().getId())` immediately before and after `readObject()`, inside a try/finally so the exception path is also measured. Take the median of 20 runs.
- (4) Baseline: the same delta for deserializing L0 (fixed `ObjectInputStream` overhead, about some KB). Report Δ − baseline.
- (5) Any `OutOfMemoryError`.
- The `len` operand itself cannot be read from outside the method. It is known by construction from the stream, and for L4–L7 the exception message echoes it.

> **Amendment A3 (2026-11-06, stage-4 audit, before any reading) — instrument and measurement definitions.** For each row the stream bytes are built once. Each of the
> 5 warm-up and 20 measured iterations makes `new ObjectInputStream(new ByteArrayInputStream(bytes))` (for J rows, the JavaSerialization
> deserializer's `open`) **outside** the window; the window is `getThreadAllocatedBytes(currentThread)` immediately before and after
> `readObject()` (or `deserialize(null)`), closed in `finally`. Δ = after − before. The row's baseline b is the median Δ of the arm's
> len = 0 row (arm D's for J rows). Recorded per row: outcome (object / exception class and message), whether all 25 iterations gave the
> same outcome, `remaining()` and a content check (genuine rows: byte i = `i & 0xff`), median/min/max Δ, and med−b, max−b. Instrument
> check, first in each arm: `isThreadAllocatedMemorySupported()` and `isThreadAllocatedMemoryEnabled()` true; a known answer, Δ around
> `new byte[1,048,576]` (kept live) ∈ [1,048,576, 1,048,576 + 4,096]; `Runtime.maxMemory()` ≤ 256 MiB and JVM input arguments contain
> `-Xmx256m`. Output: one CSV line per row, prefix `IFCHK`, in the surefire output file.

**B2e. Procedure.**
1. rsync and build (B2a).
2. Write `TestRawPathHandleMaxSize` with one `@Test` per length plus `testJavaSerializationPath` and `testPositiveControlUncheckedAlloc` (B2h). Log a line `len=<len> outcome=<..> allocDelta=<bytes>` for each.
3. Run `cd hadoop-common-project/hadoop-common && mvn test -Dtest=TestRawPathHandleMaxSize -Dmaven-surefire-plugin.argLine="-Xmx256m"`.
4. Collect the log lines from `target/surefire-reports/org.apache.hadoop.fs.TestRawPathHandleMaxSize-output.txt`.
5. (Optional) Repeat in the second copy with `MAX_SIZE = 1 << 16`.

**B2f. Predictions.**

| ID | Outcome | Allocation |
|---|---|---|
| L0 | object, `remaining()==0` | baseline |
| L1 | object, 1,024 bytes, content equal | Δ − baseline ≈ 1,040 (1,024 + 16-byte array header), i.e. within [1,024, 1,024+4 KiB] |
| L2 | success | Δ − baseline ∈ [1,048,575, 1,048,575 + 4 KiB] |
| L3 | success, `remaining()==1,048,576` | Δ − baseline ∈ [1,048,576, 1,048,576 + 4 KiB] |
| L4 | `IOException` "Illegal buffer length 1048577" | Δ − baseline < 64 KiB |
| L5 | `IOException` "Illegal buffer length 16777216" | Δ − baseline < 64 KiB |
| L6 | `IOException` "Illegal buffer length 2147483647" | Δ − baseline < 64 KiB, no `OutOfMemoryError` under `-Xmx256m` |
| L7 | `IOException` "Illegal buffer length -1" | Δ − baseline < 64 KiB |

The JavaSerialization path gives the same results for L3/L4. Max allocation over all rejected cases is less than 1 MiB. With the optional `1<<16` build, 65,536 succeeds and 65,537 fails.

> **Amendment A4 (2026-11-06, stage-4 audit, before any reading) — predictions in numbers, all arms.** For every RawPathHandle row of every arm (and J3/J4), with M the
> arm's value: if 0 ≤ len ≤ M, all 25 iterations return an object with `remaining()` = len, content equal, and med−b ∈ [len, len + 4,096];
> otherwise all 25 throw `IOException` with message exactly `Illegal buffer length <len>`, med−b < 65,536, max−b < 1,048,576, and no
> `OutOfMemoryError`. Hence the largest accepted len (the per-call allocation ceiling) is M in each arm: 65,536 (K16), 1,048,576 (D),
> 16,777,216 (K24); 1,048,576 is rejected in K16 and accepted in D; 67,108,864 is rejected in D and K24. Control rows: A6.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| L0–L3 succeed with Δ ≈ len; L4–L7 throw with Δ ≪ 1 MiB | Claim confirmed: `MAX_SIZE` caps the per-handle deserialization buffer |
| L4 or L5 succeeds, or Δ for L4/L5 ≥ len | Claim wrong: the check is not enforced or not before the allocation |
| L6 gives `OutOfMemoryError` instead of `IOException` | Claim wrong: an allocation happened before or beside the check |
| L3 fails | Boundary is off by one versus the source (`>` vs `>=`). The claim about where the boundary lies is wrong |
| Optional `1<<16` build: boundary moves to 65,536 | Confirms the constant is the controlling value |
| Positive control (B2h) does not OOM | Control failed: the heap is not small enough to show the difference. Lower `-Xmx` and re-run before concluding |

> **Amendment A5 (2026-11-06, stage-4 audit, before any reading) — a verdict for every row, missing rows.** Read with A4/A6. Claim tested: B1 (per-call allocation is
> capped at `MAX_SIZE`, and the disallow branch allocates no payload).
>
> | Observation | Verdict / effect |
> |---|---|
> | Every A4 reading holds in all three arms and J3/J4; the A6 controls move | **Confirmed — caps** (ceiling = M follows the knob; disallow branch observed by its message) |
> | As row 1, but a rejected row's med−b is in [65,536, 1,048,576) while the arm's rejected rows stay within 65,536 of each other (flat across len) | **Confirmed — caps**, flagged (overhead, not a payload) |
> | As row 1, but an accepted row's med−b is in (len + 4,096, len + 65,536] | **Confirmed — caps**, flagged |
> | A len > M returns an object, or a rejected row has med−b ≥ min(len/2, 1,048,576), or an `OutOfMemoryError` on a RawPathHandle row | **Refuted — does not cap** (on the path seen; if only one arm or only the J path, *caps only on some paths*) |
> | len = M rejected, or len = M+1 accepted, in any arm; otherwise as row 1 | **Refuted** (boundary location) — effect caps, off by one |
> | Arm D as row 1, but the largest accepted len does not equal M in K16 or K24 | **Not confirmed** — effect undetermined (something other than the constant sets the boundary) |
> | An accepted row with med−b < len, the instrument check fails, or an A6 control does not move | **Invalid run** (instrument); fix and re-run the tier |
> | Sentinel not found exactly once, outcomes differ within a row, `MAX_SIZE` not M, or an unexpected exception or test error | **Invalid run** / runbook defect |

**B2h. Controls.**
- Baseline subtraction (L0) removes fixed `ObjectInputStream` cost.
- Positive control `testPositiveControlUncheckedAlloc`: a test-local `Serializable` class whose `readObject` mirrors `RawPathHandle.readObject` minus the check (`int len = in.readInt(); byte[] x = new byte[len]; in.readFully(x);`). Feed it the same L5 and L6 stream shapes. L5 should show Δ ≥ 16 MiB (then `EOFException` for a truncated stream). L6 should throw `OutOfMemoryError` ("Requested array size exceeds VM limit" or "Java heap space") under `-Xmx256m`. This shows the workload would move usage without the cap.
- Content check on success rules out a reused or empty buffer.
- Using the genuine serializer for L0–L5 rules out a malformed stream causing the rejection. The message must echo the exact len.
- Thread-allocated bytes are per thread, so other JVM threads do not pollute them.

> **Amendment A6 (2026-11-06, stage-4 audit, before any reading) — the positive control in numbers.** `UncheckedHandle` (test-local, `Serializable`, its own
> `serialVersionUID`) writes `writeInt(len)` + payload and reads `readInt`, `new byte[len]`, `readFully` with no check. Rows, arm D:
> C5 g 16,777,216 (25 iterations: object, med−b ≥ 16,777,216); C8 p 67,108,864 (25 iterations: `EOFException`, med−b ≥ 67,108,864);
> C9 p 536,870,912 (3 iterations: `OutOfMemoryError: Java heap space` under `-Xmx256m`); C6 p 2,147,483,647 (3 iterations:
> `OutOfMemoryError`, "Requested array size exceeds VM limit" or "Java heap space"). C8 against L8 (same claimed length, same stream
> shape) is the direct with/without-check comparison: C8 med−b ≥ 1,000 × L8 med−b (or L8 med−b ≤ 0). B2h's "L5 ... then
> `EOFException` for a truncated stream" is read as C5 (genuine, succeeds) plus C8 (truncated).

### B3. Cluster tier

n/a: no Hadoop daemon or client command in 3.4.2 Java-deserializes a `RawPathHandle`. The only production uses build it through the unbounded constructor inside the DataNode (`FinalizedProvidedReplica.java:56`, `ProvidedVolumeImpl.java:186`), and HDFS handles cross RPC as protobuf `bytes()`, not Java serialization. So no `hdfs dfs`/`yarn jar` workload reaches line 107, and the constant cannot be pushed to a boundary through configuration.

What to do instead to answer the same question with a real distribution:

**B3a. Environment and build.**
- Build the distribution from the local copy: `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`, then unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `/mydata/<you>/hadoop-base`.
- No daemons are needed.
- Put the B2 test logic in a small `main` class (`RawPathHandleProbe`) compiled against `share/hadoop/common/hadoop-common-3.4.2.jar` into `probe.jar`.
- Set `HADOOP_LOG_DIR=/mydata/<you>/logs`.

**B3b. Knobs.** Declared length L3, L4, L6 as in B2b, passed as argument. `HADOOP_HEAPSIZE_MAX=128m` (in the environment of the `hadoop` launcher).

**B3c. Workload.**
- `RawPathHandleProbe write <len> <file>` writes a stream file to `/mydata/<you>/probe/` (patched for L6).
- `hadoop jar probe.jar RawPathHandleProbe read <file>` deserializes it 1,000 times in a loop and keeps every successful handle in a list. 1,000 × 1 MiB ≈ 1 GiB would exceed 128m, so run the list-keeping variant only for L1 (1,000 × 1 KiB) and use the non-keeping loop for L3/L4/L6.
- Duration: under a minute each.

**B3d. Observables and instruments.**
- Outcome lines printed by the probe.
- GC log: `HADOOP_OPTS="-Xloggc:/mydata/<you>/logs/gc-<len>.log -XX:+PrintGCDetails"`. Read the cumulative allocation from the probe's `ThreadMXBean` total.
- `jstat -gc <pid> 1000` while running.
- Process RSS from `/proc/<pid>/status` (VmHWM).

**B3e. Procedure.**
1. Build and unpack.
2. Build `probe.jar` outside the source tree.
3. For each len: write the stream, then run `HADOOP_HEAPSIZE_MAX=128m hadoop jar ... read`, capturing output, the GC log and VmHWM.
4. Check with `jps` that no probe JVM remains.

**B3f. Predictions.**

| len | Outcome | Allocation |
|---|---|---|
| L3 | 1,000 successes | ≈ 1,000 × 1 MiB ≈ 1 GiB total, young-GC churn |
| L4 | 1,000 `IOException`s | total allocation ≪ 1,000 × 1 MiB (< 64 MiB) |
| L6 | 1,000 `IOException`s | no `OutOfMemoryError`, VmHWM about equal to L4's |

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| L4/L6 allocation ≪ L3's and no OOM | Cap holds in the distribution jar |
| L6 OOM or L4 allocation ≈ L3's | Claim wrong |
| Positive control: an unchecked probe class with L6 OOMs at 128m | Workload can move usage; needed before trusting a flat L6 |

**B3h. Controls.** Same as B2h. The distribution jar (not test classes) is on the classpath, which confirms the shipped build has the check.

> **Amendment A7 (2026-11-06, stage-4 audit, before any reading) — the n/a stands for daemons; the stated alternative is run as the cluster tier.** Re-checked at
> `rel/release-3.4.2`: the only non-test users of `RawPathHandle` are `FinalizedProvidedReplica.java:55-56` and
> `ProvidedVolumeImpl.java:186-187`, both through the unchecked `ByteBuffer` constructor; nothing in a daemon Java-deserializes it. So the
> cluster tier is B3a–B3h on the built distribution, with these specifics:
> - **Environment.** `cp -a /mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2 <run>/hadoop` (no build, no daemons, no
>   ports); `HADOOP_LOG_DIR`, `HADOOP_PID_DIR` and `-Djava.io.tmpdir` under `<run>`. `RawPathHandleProbe.java` (harness; includes the
>   unchecked control class `UncheckedProbeHandle`) is compiled with `javac` against `<run>/hadoop/share/hadoop/common/hadoop-common-3.4.2.jar`
>   into `<run>/probe/probe.jar`.
> - **Commands.** Write: `hadoop jar probe.jar RawPathHandleProbe write <raw|ctl> <g|p> <len> <file>` (`HADOOP_HEAPSIZE_MAX=512m`, not
>   measured). Read: `HADOOP_HEAPSIZE_MAX=128m HADOOP_OPTS="-Xloggc:<run>/logs/cluster/gc-<id>.log -XX:+PrintGCDetails -XX:+PrintGCDateStamps -Djava.io.tmpdir=<run>/tmp" hadoop jar probe.jar RawPathHandleProbe read <raw|ctl> <file> 1000 <keep|drop>`.
>   The probe reads the file once, then per iteration makes an `ObjectInputStream` and calls `readObject`; it reports the main thread's
>   allocated bytes over the whole loop (`total`, includes stream creation), outcome counts and distinct messages, stops at the first
>   `OutOfMemoryError` (iteration recorded), and prints `maxMemory`, JVM input arguments, the code source of `RawPathHandle`, and `VmHWM`
>   from `/proc/self/status`.
> - **Rows.** R1 raw g 1,024 keep; R3 raw g 1,048,576; R4 raw g 1,048,577; R5 raw g 16,777,216; R6 raw p 2,147,483,647 (all `drop`
>   except R1). Controls: X5 ctl g 16,777,216; X9 ctl p 536,870,912; X6 ctl p 2,147,483,647.
> - **Predictions (replace B3f's "≈", "≪", "about equal").** R1: 1,000 objects, total ∈ [1,000 × 1,024, 1,000 × (1,024 + 65,536)].
>   R3: 1,000 objects, total ∈ [1,000 × 1,048,576, 1,000 × (1,048,576 + 65,536)]. R4, R5, R6: 1,000 `IOException`s with message
>   `Illegal buffer length <len>`, total < 67,108,864, no `OutOfMemoryError`; VmHWM(R6) ≤ VmHWM(R4) + 32 MiB. X5: 1,000 objects, total ≥
>   1,000 × 16,777,216. X9 and X6: `OutOfMemoryError` at iteration 1. Every read: code source is the distribution's
>   `hadoop-common-3.4.2.jar`, `maxMemory` ≤ 128 MiB.
> - **Verdicts (B3g).** All predictions hold → **Confirmed — caps**. R4/R5/R6 return an object, or their total ≥ 1,000 × min(len/2, 1 MiB),
>   or an `OutOfMemoryError` on an R row → **Refuted — does not cap**. R3 rejected or R4 accepted → **Refuted** (boundary), caps.
>   R rows as predicted but a total misses its bound by less than a factor 2, flat across R4–R6 → **Confirmed — caps**, flagged. A control
>   that does not move (X5 total < 1,000 × 16 MiB, no OOM in X9), a wrong code source or heap → **Invalid run**. The knob is varied in
>   the unit tier only (the distribution jar is the shipped constant).

**B4. Risks and cleanup.**
- Disk: test outputs and stream files are under a few MiB. Keep all build and probe files on `/mydata/<you>/`, never on shared storage or in the shared source tree.
- No ports and no daemons are used.
- After running, `jps` should show no `RawPathHandleProbe` or surefire JVM. Kill any leftover with `kill <pid>`.
- Delete `/mydata/<you>/probe/` when done.
- `-Xmx256m`/`128m` keeps memory use small on a shared host.

## C. Sources read

- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/RawPathHandle.java
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/PathHandle.java (grep)
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/serializer/JavaSerialization.java:35-80
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/ipc/RPC.java:93 (grep)
- hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/fs/contract/AbstractContractPathHandleTest.java:230-260
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/FinalizedProvidedReplica.java:40-70
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/ProvidedVolumeImpl.java:170-200
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/common/blockaliasmap/impl/TextFileRegionAliasMap.java (grep for nonce)
- hadoop-common-project/hadoop-common/src/site/markdown/filesystem/filesystem.md (grep, 852-870)
- hadoop-common-project/hadoop-common/src/site/markdown/release/3.1.0/CHANGELOG.3.1.0.md (grep)
- hadoop-project/pom.xml:187,2469 (surefire argLine)
- https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-common/filesystem/filesystem.html
- https://issues.apache.org/jira/browse/HDFS-12882

## D. Stage-4 feedback

**D1. Audit amendments (2026-11-06, stage 4, before any harness run or reading).** Results file:
[`../../../stage4-runtime-verification/jingsong/results/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous.md`](../../../stage4-runtime-verification/jingsong/results/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous.md).
A1 (B2a) node paths, no install build, surefire options through `maven-surefire-plugin.argLine`; A2 (B2b) the knob varied in three
builds (`1<<16`, `1<<20`, `1<<24`) and a same-shape row L8; A3 (B2d) measurement window, baseline, instrument check, CSV; A4 (B2f)
predictions in numbers for all arms; A5 (B2g) a verdict for every row; A6 (B2h) the positive control in numbers; A7 (B3) the n/a
re-checked for daemons and the stated alternative made runnable as the cluster tier, with numbers. Filed sha256 `e99136da…76974127`;
the sha256 after A1–A7 is recorded in the results file §1.

**D2. Run 1 (2026-11-06, stage 4, node `pc39`).** Results file as in D1. **Unit: Confirmed — caps** (B2g/A5 row 1): in three builds
(`MAX_SIZE` = 64 KiB, 1 MiB, 16 MiB) the largest accepted declared length equals `MAX_SIZE`, accepted reads allocate the declared
length, rejected reads (M+1, 16 MiB, 64 MiB, 2^31−1, −1) throw `IOException("Illegal buffer length <len>")` and allocate about 2.2 KB;
the unchecked twin allocates 64 MiB on the same truncated input and OOMs on 512 MiB and 2^31−1 claims. **Cluster (A7): Confirmed —
caps**: the shipped `hadoop-common-3.4.2.jar` at `-Xmx128m`, 1,000 reads per row, 1.05 GB for 1 MiB handles against about 5 MB in total
for 1 MiB+1, 16 MiB and 2^31−1 claims, no OOM. Outcome class: **true positive**. No section amended by the result; no run 2.
