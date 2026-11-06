# MAX_KEY_SIZE — verification solution  <!-- file: cases/MAX_KEY_SIZE-write-limit--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`BoundedByteArrayOutputStream.java:76`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/BoundedByteArrayOutputStream.java#L76) — `if (currentPointer >= limit)` in `write(int b)` |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-06 |
| Estimate | `negative` — the check bounds a write cursor inside a `byte[]` that is fully allocated at construction, so heap held by the stream is its capacity whatever `limit` is and however many bytes are written; the limit only decides when a write fails. |
| Ground | (1) The memory is allocated up front, at `new byte[capacity]` (`BoundedByteArrayOutputStream.java:56`), which is 2 × `MAX_KEY_SIZE` = 2 × 64 KiB per `TFile.Writer` (`TFile.java:289-290`). It never grows, so the check at line 76 cannot change usage. Without the check, the JVM's array bounds check would still stop a write past `capacity`. (2) The thing it bounds, one TFile key of at most 64 KiB, is not memory- or disk-significant. (3) No production path in the tree reaches line 76: every production key write uses `writeUTF` or `write(byte[],..)`, which go to line 91 (see A3/A4). |

Stem parts: constraint = `MAX_KEY_SIZE`, function = `write` (the method that directly encloses the given if statement, the single-byte overload), operand = `limit`.

## A. Constraint trace

**A1. The constraint.**
- The constraint is the hard-coded constant `MAX_KEY_SIZE`, declared at
  [`TFile.java:155`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/file/tfile/TFile.java#L155) (`hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/file/tfile/TFile.java`) as `private static final int MAX_KEY_SIZE = 64 * 1024; // 64KB`. It is the only declaration of that name in the tree, so no class qualifier is needed.
- Unit: bytes. Default: 65536. It has no `*-default.xml` entry and no configuration key. It cannot be set at runtime; changing it means recompiling `hadoop-common`.
- It reaches the check like this. `TFile.Writer.<init>` builds `new BoundedByteArrayOutputStream(MAX_KEY_SIZE)` twice (`TFile.java:289-290`). That calls `this(capacity, capacity)` → `new byte[capacity]` (`BoundedByteArrayOutputStream.java:45-56`). Then `resetBuffer` sets `this.limit = offset + limit` (`:63-71`).
- Other sources of the per-instance `limit`:
  - `reset(int newlim)` (`:103-108`). `TFile.Writer.KeyRegister` calls it with the caller's declared key length when `prepareAppendKey(len >= 0)` is used (`TFile.java:422-430`), so `limit` can be lower than `MAX_KEY_SIZE`.
  - `reset()` restores `limit = buffer.length - startOffset` (`:112-115`).
  - The class has a second production user, MapReduce `InMemoryMapOutput`, where capacity = limit = the map-output size reserved by `MergeManagerImpl` (`InMemoryMapOutput.java:60`). Writes there never reach line 76 (see A3), so it is not used for naming.
- Which process reads it: any JVM that creates a `TFile.Writer`. In the daemons that is the NodeManager (log aggregation, `AggregatedLogFormat.java:491-494`) and the ApplicationHistoryServer's `FileSystemApplicationHistoryStore` (`FileSystemApplicationHistoryStore.java:738`).

**A2. What it caps.**
- The check compares `currentPointer` (the next write index into the preallocated buffer) with `limit` (the end offset). The usage-side operand is `currentPointer`; `size()` exposes it as `currentPointer - startOffset` (`:140-142`).
- What it bounds is the length of one TFile key held in the key buffer: at most `MAX_KEY_SIZE` = 64 KiB, or the declared key length.
- The heap behind it is fixed when the object is built (`byte[MAX_KEY_SIZE]`, twice per Writer). It does not depend on `currentPointer` or `limit`. So the constraint caps no memory or disk that would otherwise grow; it is a key-length format/validity limit. TFile's own javadoc says "Keys are restricted to 64KB" (`TFile.java:57`).

**A3. Mechanism.**
1. Construction allocates `byte[capacity]` and sets `limit` (`BoundedByteArrayOutputStream.java:55-71`). `resetBuffer` rejects `capacity < limit` (`:65-66`), so `limit <= capacity` always holds.
2. Single-byte write: [`if (currentPointer >= limit)`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/BoundedByteArrayOutputStream.java#L76) → `throw new EOFException("Reaching the limit of the buffer.")` (`:77`). Otherwise it stores the byte and increments the cursor (`:79`). The buffer is never reallocated.
3. Bulk write: the twin check `if (currentPointer + len > limit)` (`:91-92`) throws `EOFException`. Otherwise `System.arraycopy` (`:95`).
4. When the limit is reached, the write fails with `EOFException` and nothing is stored. In TFile the exception goes up through `KeyRegister` (a `DataOutputStream` over `currentKeyBufferOS`, `TFile.java:418-431`) to the caller. The Writer's `errorCount` is never decremented for that key, so the Writer is left in an error state.
5. How line 76 is reached: only by single-byte writes made directly on the `BoundedByteArrayOutputStream`. That means `DataOutputStream.write(int)`, `writeByte`, `writeShort`, `writeChar`, `writeInt` and `writeLong` on a `KeyRegister` returned by `TFile.Writer.prepareAppendKey(int)` (`TFile.java:527-536`).
6. Paths that do not reach line 76:
   - `writeUTF` builds a byte array and calls `write(byte[],int,int)` (JDK 8 `DataOutputStream.writeUTF`), so it lands on line 91. Production key writers use `writeUTF` only: `AggregatedLogFormat.LogKey.write` (`AggregatedLogFormat.java:149-150`) and `HistoryDataKey.write` (`FileSystemApplicationHistoryStore.java:787-789`). `TFile.Writer.append(byte[]..)` uses a bulk write.
   - MapReduce `InMemoryWriter` wraps the stream in `IFileOutputStream`, whose `write(int)` turns into `write(barray,0,1)` (`IFileOutputStream.java:96-98`). That also lands on line 91.
7. Overshoot or bypass: none of the check itself. `limit` can never exceed `capacity`, so if the check were removed, an `ArrayIndexOutOfBoundsException` at `:79` would stop the same write. The check changes the exception type, not the memory bound.

**A4. Other consumers.**
- Within TFile:
  - `TFile.Reader.Scanner` allocates its own `keyBuffer = new byte[MAX_KEY_SIZE]` per scanner (`TFile.java:1291`), outside this check.
  - BCFile/compression buffers and the FS output buffer, `tfile.fs.output.buffer.size` (default 256 KiB, `TFile.java:151-152`).
  - Value chunk buffering, `tfile.io.chunk.size`.
  - The in-memory block index.
  All of these are larger than the two key buffers.
- In MapReduce shuffle, the large consumer is `InMemoryMapOutput`'s `byte[size]` (`InMemoryMapOutput.java:60-61`). It is governed by MergeManagerImpl's reservation, not by this check.

**A5. Evidence beyond the source.**
- TFile design JIRA: HADOOP-3315, https://issues.apache.org/jira/browse/HADOOP-3315 (cited in `TFile.java:127-128`; not fetched).
- Existing tests: `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/io/TestBoundedByteArrayOutputStream.java` (exception past limit) and `.../io/file/tfile/TestTFileStreams.java` (`testFailureKeyTooLong`, which uses a bulk write, i.e. line 91).
- JDK 8 `java.io.DataOutputStream` javadoc/source (`writeUTF` writes via `write(byte[],int,int)`; `writeInt` via four `write(int)` calls).

## B. Verification solution

**B1. Claim under test.**
1. The heap held by a `BoundedByteArrayOutputStream`, including the two key buffers of a `TFile.Writer`, equals its capacity at construction and does not follow `limit`.
2. Writes up to and past `limit` through `write(int)` allocate no extra heap. The check only stops the cursor at `limit` and throws `EOFException`.

Refuted if the bytes allocated or retained by the stream grow with the bytes written or with `limit`.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 8 (HotSpot, for `com.sun.management.ThreadMXBean`), Maven 3.3+.
- Copy the tree to local disk: `rsync -a ~/hadoop-3.4.2/ /mydata/s4/hadoop-src/`. Do not touch the shared copy.
- Build:
  ```
  cd /mydata/s4/hadoop-src
  mvn -pl hadoop-common-project/hadoop-common -am install -DskipTests -Dmaven.javadoc.skip=true
  ```
- New test file in the copy: `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/io/TestBoundedLimitHeap.java`, package `org.apache.hadoop.io`. It needs the test classpath only, nothing native.
- Surefire JVM options: `-Xmx512m -XX:+UseSerialGC`. Pass them via `-DargLine="-Xmx512m -XX:+UseSerialGC"`.

> **Amendment A1 (2026-11-06, stage-4 audit, before any reading) — node paths and JVM options.** On the stage-4 node
> (`pc41`, Jingsong's `environment.md`): the copy is made with `copy-source.sh /mydata/jingsong-s4/MAX_KEY_SIZE-write-limit-run1/src`
> (not `rsync` from `~/hadoop-3.4.2`, which does not exist); no `install` build is needed, because the node's `~/.m2` holds all
> `3.4.2` artifacts (`environment.md` §3); the tests run from the module directory
> `src/hadoop-common-project/hadoop-common` with `mvn -B test …`. `-DargLine` is ignored by this build: `hadoop-project/pom.xml:2469`
> sets `<argLine>${maven-surefire-plugin.argLine}</argLine>` (default `-Xmx2048m …`, `:187`), so the options are passed as
> `-Dmaven-surefire-plugin.argLine="-Xmx512m -XX:+UseSerialGC -Difchk.tmp=<run-dir>/tmp"`. Every `/mydata/s4/tmp` below means
> `/mydata/jingsong-s4/MAX_KEY_SIZE-write-limit-run1/tmp` (the `ifchk.tmp` property). JDK: `/usr/lib/jvm/java-8-openjdk-amd64`.
> The build ignores test failures (`mvn test` returns 0), so a run reads the surefire counts, not the exit code.

**B2b. Knobs.**
- Capacity `C` ∈ {65536 (= `MAX_KEY_SIZE`), 1 MiB, 16 MiB}. This is the only value that sets the allocation; the range spans the TFile value up to clearly measurable sizes. It is set by the constructor argument.
- Limit `L` ∈ {1024, C/2, C}, set with `reset(L)`. This is the operand at line 76.
- TFile path: declared key length `k` ∈ {−1 (limit = 65536), 100} via `prepareAppendKey(k)`.

**B2c. Workload.**
- For each (C, L), write bytes one at a time with `stream.write(0x5A)` in a loop of `W = 2·L` iterations, catching `EOFException`. The first `L` writes fill the buffer exactly (cursor 0..L−1). Write `L+1` is the first where `currentPointer >= limit`.
- Repeat `reset(L)` + loop 100 times, so that per-pass allocation is measured over 100 × L bytes written.
- TFile path:
  1. Create `TFile.Writer(fs.create(path), 256*1024, "none", "memcmp", conf)` on `LocalFileSystem`, under `/mydata/s4/tmp/tfile-<n>`.
  2. `DataOutputStream k = w.prepareAppendKey(-1)`.
  3. Call `k.writeByte(0x41)` 65537 times. Expect `EOFException` at call 65537 (65536 bytes fit).
  4. Repeat with `prepareAppendKey(100)` and 101 `writeByte` calls (fails at 101).
  5. Repeat with a fresh Writer and `k.writeInt(i)` 16385 times. Fails on the first byte of int 16385 (16384 × 4 = 65536).
  Use a new Writer for each failing case, because after an exception the Writer is in an error state.

> **Amendment A2 (2026-11-06, stage-4 audit, before any reading) — bounded past-limit writes, pass structure.** `W = 2·L` makes
> every one of the last `L` writes throw: for L = 16 MiB that is 16 Mi `EOFException`s per pass and 1.6 × 10⁹ over 100 passes
> (hours, and GiBs of exception allocation whose subtraction error would exceed the 1 KiB bound of B2f). The loop is therefore
> **`W = L + E` writes with `E = 1024`**: the first `L` fill the buffer, the next 1024 each hit line 76 and throw; the limit is
> reached and passed in every pass. Per (C, L): build the stream with `new BoundedByteArrayOutputStream(C)` (allocation measured,
> `allocCtor`), then one warm-up pass (discarded), then **100 measured passes** of `reset(L)` + the W-write loop; `allocWrites` is
> read once around the 100 passes and reported **per pass** (÷ 100); `exceptions` is the count over the 100 passes (expected
> 102400). In addition, per (C, L), **100 passes of only the L in-limit writes** (`reset(L)` + L writes, no exception) give
> `allocIn` per pass, a reading that needs no exception subtraction. "Every (C, L)" means the 9 pairs C ∈ {65536, 1048576,
> 16777216} × L ∈ {1024, C/2, C}, run in that order (C outer). The TFile key steps are unchanged; their files go under the
> `ifchk.tmp` directory (A1).

**B2d. Observables and instruments.**
- `stream.size()`: the cursor, i.e. the usage-side operand.
- `stream.getBuffer().length` and the identity of `getBuffer()`, checked before and after. It must be the same object.
- The index of the write that threw `EOFException`.
- Allocation by the test thread during (i) construction and (ii) the write loop, from `((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId())`. Read it immediately before and after each phase. Each `EOFException` (with stack trace) allocates a few KiB, so subtract the count × per-exception cost. Measure that cost separately by constructing 1000 `EOFException`s.
- Retained heap: `Runtime.totalMemory()-freeMemory()` after `System.gc()` ×3 before construction, after construction, and after the write loop, with the stream still strongly reachable.
- Not observable directly: the exact object header size. Allow ±64 bytes per array.

> **Amendment A3 (2026-11-06, stage-4 audit, before any reading) — instrument definitions.** (a) The per-exception cost
> `excCost` is measured per (C, L), right after the measured passes, as the allocation of 1000 calls of a one-frame helper that
> does `throw new EOFException("Reaching the limit of the buffer.")`, caught in the same test method that runs the write loop, so
> the stack depth (hence the backtrace size) equals that of a throw from `write(int)`. The residual is
> `allocWrites_per_pass − E × excCost`. (b) The instrument's zero: two back-to-back `getThreadAllocatedBytes` reads, recorded as
> `allocZero`. (c) The test first asserts `isThreadAllocatedMemorySupported()` and `isThreadAllocatedMemoryEnabled()` (enabling it
> if needed); a −1 reading stops the test. (d) `retainedDelta` is `used(after construction) − used(before)`, and `retainedLoop` is
> `used(after the 100 passes) − used(after construction)`, each `used` read after `System.gc()` × 3 with the stream strongly reachable.
> Retained heap resolves only to about ±1 MiB, so it can separate C from 0 only at C = 16 MiB; at C = 64 KiB and 1 MiB the
> allocation reading carries the comparison. (e) CSV row (one per (C, L), prefix `IFCHK,direct`):
> `C,L,W,sizeAtFail,failIndex,allocCtor,allocWritesPerPass,allocInPerPass,exceptions,excCost,residualPerPass,allocZero,retainedDelta,retainedLoop,bufIdentitySame,bufLength`.

**B2e. Procedure.**
1. Write `TestBoundedLimitHeap` with three methods:
   - `testDirect`: loops over C × L and prints one CSV row per pass: `C,L,W,sizeAtFail,failIndex,allocCtor,allocWrites,exceptions,retainedDelta,bufIdentitySame`.
   - `testTFileKey`: the three TFile cases above. It also records allocation across `new TFile.Writer(...)`.
   - `testControl`: see B2h.
2. Run:
   ```
   mvn -pl hadoop-common-project/hadoop-common test -Dtest=TestBoundedLimitHeap -DargLine="-Xmx512m -XX:+UseSerialGC"
   ```
   Then also the existing tests, `-Dtest=TestBoundedByteArrayOutputStream,TestTFileStreams`.
3. Collect the CSV from `target/surefire-reports/*-output.txt`.
4. Delete `/mydata/s4/tmp/tfile-*`.

**B2f. Predictions (stated before any run).**
- For every (C, L): `failIndex = L+1`, `sizeAtFail = L`, and `getBuffer()` is the same array with `length = C`.
- `allocCtor` ≈ C + 16..24 bytes (one array header) plus a few dozen bytes for the object. It is independent of L.
- `allocWrites` minus exception cost < 1 KiB per pass, for all L from 1024 to 16 MiB. It is flat in L and in W.
- `retainedDelta` after construction ≈ C (e.g. ≈ 16 MiB for C = 16 MiB, ±1 MiB GC noise), and it does not change across the write loop.
- TFile:
  - The `writeByte` loop fails at byte 65537 with `size()` = 65536.
  - `prepareAppendKey(100)` fails at byte 101.
  - The `writeInt` loop fails on int 16385.
  - Allocation across the key-write loop < 1 KiB plus exceptions.
  - Allocation across `new TFile.Writer` ≥ 2 × 65536 bytes (the two key buffers), plus BCFile/FS buffers (about 256 KiB for `tfile.fs.output.buffer.size`).
- The claim is wrong if `allocWrites` grows roughly linearly with L or W, if `retainedDelta` rises during writes, or if the buffer identity changes.

> **Amendment A4 (2026-11-06, stage-4 audit, before any reading) — numbers for "≈", "flat" and "grows".** With A2/A3:
> - Per (C, L): `failIndex = L + 1`, `sizeAtFail = L`, `exceptions = 102400`, `bufIdentitySame = true`, `bufLength = C`.
> - `C ≤ allocCtor ≤ C + 256` bytes.
> - **Flat (prediction met):** `allocInPerPass < 1024` and `residualPerPass < 1024` in every row.
> - **Grows with L (claim refuted):** in the C = 16 MiB rows, `allocInPerPass` or `residualPerPass` at L = 16 MiB exceeds the
>   value at L = 1024 by more than 1 % of the 16 MiB − 1024 extra bytes written (> 167 762 bytes per pass), or any row has
>   `allocInPerPass ≥ 1 %` of L with L ≥ 512 KiB; or `retainedLoop > 1 MiB` in any row; or `bufIdentitySame = false`.
> - Neither (some row ≥ 1024 bytes per pass but no growth as defined): the bound is missed while usage stays flat in L — see B2g.
> - `retainedDelta`: within C ± 1 MiB in every row (resolvable from 0 only at C = 16 MiB, A3d); `|retainedLoop| ≤ 1 MiB`.
> - TFile: `writeByte` fails at call 65537 with `size()` = 65536 (the Writer's private `currentKeyBufferOS` is read by reflection,
>   since TFile does not expose it); `prepareAppendKey(100)` fails at call 101; `writeInt` fails on int 16385;
>   allocation across each key-write loop minus one `excCost` < 1024 bytes; allocation across `new TFile.Writer` ≥ 131072 bytes.
> - Positive control (B2h, amended): see A5.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `allocWrites` ≈ 0 for all L, `retainedDelta` ≈ C regardless of L, failure at L+1; control grows ≈ W | Claim confirmed: usage does not follow the limit; the check is a cursor guard in fixed memory |
| `allocWrites` or retained heap grows with L or W | Claim refuted: usage follows the constraint |
| `retainedDelta` follows C but not L | Expected: memory follows capacity (the allocation), not the check's operand |
| Failure at an index other than L+1, or no `EOFException` | Mechanism traced wrongly; re-read A3 before drawing conclusions |
| Positive control does not grow, or the instrument returns −1/unsupported | Not confirmed: instrument broken (non-HotSpot JVM or allocation measurement disabled) |
| Limit never reached (no exception in any pass) | Not confirmed: workload wrong |

> **Amendment A6 (2026-11-06, stage-4 audit, before any reading) — verdicts for every row, missing rows.** The rows above read
> with the thresholds of A4/A5. Row 1 is **Confirmed** (does not cap) only when, in addition, every per-(C, L) and TFile reading of
> A4 holds and the A5 control grows. Row 2 is **Refuted** (caps: usage follows the constraint) by A4's "grows" test. Row 3 is part of
> row 1, not a separate verdict. Row 4 ("failure at an index other than L+1 …") is **Not confirmed** (mechanism traced wrongly).
> Added rows:
>
> | Observation | Meaning |
> |---|---|
> | Some row's `allocInPerPass` or `residualPerPass` ≥ 1024 bytes but A4's "grows" test not met, or a TFile key-loop allocation minus one `excCost` between 1024 and 65535 bytes, all else as row 1 | **Confirmed** with the missed bound recorded as a flag: usage does not follow L; the excess is per-pass overhead |
> | TFile: failure at a call other than 65537 / 101 / int 16385, or no `EOFException` | **Not confirmed**: the TFile key path does not reach line 76 as traced |
> | TFile: allocation across a key-write loop minus one `excCost` ≥ 64 KiB (grows with the key bytes written) | **Refuted**: TFile key writes allocate with the bytes written |
> | TFile: allocation across `new TFile.Writer` < 131072 | **Not confirmed**: the two key buffers are not allocated as traced |
> | Existing `TestBoundedByteArrayOutputStream` or `TestTFileStreams` fail, or a test of `TestBoundedLimitHeap` errors | **Invalid run**: environment or harness fault; fix and restart the tier |

**B2h. Controls.**
- Positive control: the same single-byte loop of W bytes into `java.io.ByteArrayOutputStream(32)` and into `org.apache.hadoop.io.DataOutputBuffer`. Allocation should grow with W (≈ 2·W with doubling growth), which shows the instrument detects heap that follows bytes written.
- Exception-cost baseline: measured separately and subtracted, so that exception allocation is not read as buffer growth.
- Warm-up: run one pass first and discard it, so JIT/class-loading allocation is excluded.
- Single thread with SerialGC, so thread-local allocation counts are not mixed with other threads.

> **Amendment A5 (2026-11-06, stage-4 audit, before any reading) — the positive control in numbers.** For each of the 9 (C, L)
> pairs, `testControl` writes the same `W = L + 1024` single bytes (`write(0x5A)`) into a fresh `java.io.ByteArrayOutputStream(32)`
> and, separately, a fresh `org.apache.hadoop.io.DataOutputBuffer()` (its `write(int)`), one warm-up pass then 10 measured passes,
> allocation per pass from the same instrument. CSV prefix `IFCHK,control`: `stream,W,allocPerPass,ratio` (ratio =
> allocPerPass / W). **The control grows** when every row has `W ≤ allocPerPass ≤ 4·W + 1024` and the row at the largest W
> (16 MiB + 1024) is more than 1000 × the row at the smallest W (2048). It is the known-binding comparison for this file: the
> same instrument shows heap that follows the bytes written. A second one comes free from the direct test: `allocCtor` and
> `retainedDelta` follow the capacity C (B2g row 3), so the instrument also resolves a size that does set the allocation.

### B3. Cluster tier

n/a: the constraint is a compile-time constant with no configuration key, so it cannot be pushed to the boundary in a deployed cluster without editing source. More importantly, no daemon code path in 3.4.2 reaches line 76:
- The NodeManager's log aggregation (`AggregatedLogFormat.java:505-541`) and the ApplicationHistoryServer (`FileSystemApplicationHistoryStore.java:756-757`) write keys with `writeUTF`, which goes to line 91.
- MapReduce's in-memory merge goes through `IFileOutputStream.write(int)` → bulk write (line 91).
- The memory involved is a fixed 128 KiB per open `TFile.Writer`, far below what daemon heap sampling (`jstat`, `/jmx`) can resolve against background churn.

What to do instead to answer the same question at daemon level: the unit tier's `testTFileKey` already drives the same `TFile.Writer` class that the NodeManager uses, on a real `LocalFileSystem`.

If stage 4 still wants a cluster-side sanity check, use a pseudo-distributed YARN with `yarn.log-aggregation-enable=true` (`yarn-site.xml`, restart NM). Run `yarn jar hadoop-mapreduce-examples-3.4.2.jar pi 2 10` five times in a row, and take `jmap -histo:live <NM pid> | grep '\[B'` before and after each aggregation. The prediction is no `byte[]` population that grows with the number of aggregated apps beyond transient 64 KiB pairs. This is a weak check and is not required.

> **Amendment A7 (2026-11-06, stage-4 audit, before any reading) — the n/a stands; the optional check is not run.** Re-checked at
> `rel/release-3.4.2`: the only production `prepareAppendKey` callers are `AggregatedLogFormat.java:505, 514, 524, 541` and
> `FileSystemApplicationHistoryStore.java:756`; their keys are written with `writeUTF` (`AggregatedLogFormat.java:150`,
> `FileSystemApplicationHistoryStore.java:788-789`), i.e. line 91, and `IFileOutputStream.write(int)` turns into a bulk write
> (`IFileOutputStream.java:96-98`). A daemon run would therefore not execute line 76 at all, so the optional `jmap` check cannot
> tell anything about this check's effect; it is not run. The cluster tier is `n/a`, and the case is classed from the unit tier.

**B4. Risks and cleanup.**
- The unit tier writes only to `/mydata/s4/tmp` (a few MiB). Maven artifacts go into `~/.m2`.
- The build must be done in a local copy, never the shared tree.
- No ports or daemons. After the run, `jps` should show only `Jps` (and any Maven/surefire forks gone). Kill stray `surefire` JVMs if a test hangs.
- For the optional cluster check: `stop-yarn.sh`, `stop-dfs.sh`, `jps` empty. Remove `hadoop.tmp.dir`, the NM local/log dirs and the remote log dir under `/mydata/s4`.

## C. Sources read

hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/BoundedByteArrayOutputStream.java
hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/io/TestBoundedByteArrayOutputStream.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/file/tfile/TFile.java (lines 57, 80-155, 270-300, 400-560, 1280-1300)
hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/io/file/tfile/TestTFileStreams.java (lines 60-110, 180-260)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/task/reduce/InMemoryWriter.java
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/task/reduce/InMemoryMapOutput.java
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/task/reduce/MergeManagerImpl.java (lines 380-420)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/IFileOutputStream.java (write methods)
hadoop-yarn-project/hadoop-yarn/hadoop-yarn-common/src/main/java/org/apache/hadoop/yarn/logaggregation/AggregatedLogFormat.java (lines 140-160, 480-560)
hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-applicationhistoryservice/src/main/java/org/apache/hadoop/yarn/server/applicationhistoryservice/FileSystemApplicationHistoryStore.java (lines 738-790)
https://issues.apache.org/jira/browse/HADOOP-3315 (cited, not fetched)
JDK 8 java.io.DataOutputStream documentation (writeUTF / writeInt behaviour)

## D. Stage-4 feedback

**D1. Audit amendments (2026-11-06, stage 4, before any harness run or reading).** Results file:
[`../../../stage4-runtime-verification/jingsong/results/MAX_KEY_SIZE-write-limit--autonomous.md`](../../../stage4-runtime-verification/jingsong/results/MAX_KEY_SIZE-write-limit--autonomous.md).
A1 (B2a) node paths, no install build, surefire options through `maven-surefire-plugin.argLine`; A2 (B2c) `W = L + 1024`, 100
measured passes after one warm-up, an in-limit-only loop; A3 (B2d) exception cost at the same stack depth, instrument zero and
support check, retained-heap definitions, CSV columns; A4 (B2f) numbers for "≈", "flat" and "grows"; A5 (B2h) the positive control
in numbers; A6 (B2g) a verdict for every row and the missing rows (missed bound but flat, TFile rows, existing-test failure);
A7 (B3) the n/a re-checked, optional cluster check not run. Filed sha256 `4f3911cd…8d62224`; the sha256 after A1–A7 is recorded in
the results file §1.

**D2. Stage-4 result (2026-11-06, run 1, unit tier; cluster n/a).** Unit **Confirmed** — does not cap (B2g row 1), with one flag;
outcome class **true negative**. Writes up to the limit allocated 0.00 bytes per pass and past-limit writes only the
`EOFException`s (520 bytes each) at every L from 1 KiB to 16 MiB; failure at write L + 1 in every pass; TFile key writes failed at
65537 / 101 / int 16385 with no allocation beyond the exception; the positive control (`ByteArrayOutputStream`, `DataOutputBuffer`)
grew ×16070 with W. Flag: the retained-heap reading `retainedDelta` missed C ± 1 MiB in 1 of 9 rows (−6872 at C = L = 16 MiB),
traced to the measurement (the previous row's stream still counted before construction), not to the stream. Cluster tier not run
(n/a, A7). No runbook defects. Results:
[`../../../stage4-runtime-verification/jingsong/results/MAX_KEY_SIZE-write-limit--autonomous.md`](../../../stage4-runtime-verification/jingsong/results/MAX_KEY_SIZE-write-limit--autonomous.md).
Left for stage 3: R2 (A3 step 4's `errorCount` remark; the Writer simply stays in state `IN_KEY`).
