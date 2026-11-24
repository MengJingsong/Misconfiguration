# dfs.client.write.byte-array-manager.count-limit — verification solution  <!-- file: cases/dfs.client.write.byte-array-manager.count-limit-recycle-maxAllocated--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`ByteArrayManager.java:209`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/util/ByteArrayManager.java#L209) — `if (freeQueue.size() < maxAllocated - numAllocated)` in `ByteArrayManager.FixedLengthManager#recycle(byte[])` (unit kind: row) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive` — when the byte-array manager is enabled, `count-limit` (copied into `FixedLengthManager.maxAllocated`) bounds, per power-of-two array length, how many packet buffers the HDFS client keeps pooled in its heap (`freeQueue.size() ≤ maxAllocated − numAllocated ≤ count-limit`), and `allocate()` blocks writers once `count-limit` managed buffers are out, so client heap held by DFSOutputStream packet buffers of that length follows `count-limit × length`. Caveats: off by default (`enabled=false` → no manager, no cap), the cap is per length, and the in-use count can drift low (A3), so it is a pool cap first and an approximate in-use cap second. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- Name: `dfs.client.write.byte-array-manager.count-limit` (configuration key). Declared as
  `HdfsClientConfigKeys.Write.ByteArrayManager.COUNT_LIMIT_KEY` at
  [`HdfsClientConfigKeys.java:424`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/HdfsClientConfigKeys.java#L424)
  (prefix `dfs.client.write.byte-array-manager.` from `HdfsClientConfigKeys.java:418`, itself
  `Write.PREFIX` = `dfs.client.write.` at `HdfsClientConfigKeys.java:406`); aliased as
  `DFSConfigKeys` constants at `DFSConfigKeys.java:1839-1842`.
- `hdfs-default.xml` entry: `hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml:4677-4682`,
  value `2048`, "The maximum number of arrays allowed for each array length."
- Unit: a count of byte arrays, **per array length** (each length is a power of two ≥ 32). The
  memory it implies is `count-limit × arrayLength` bytes per length.
- Default: `COUNT_LIMIT_DEFAULT = 2048` (`HdfsClientConfigKeys.java:425`); the `hdfs-default.xml`
  value is also 2048, so they agree.
- Gate and companions (named here, not the primary constraint):
  `dfs.client.write.byte-array-manager.enabled` (default `false`, `HdfsClientConfigKeys.java:420-421`,
  `hdfs-default.xml:4704`) — when false the manager does not exist and `count-limit` is never read;
  `dfs.client.write.byte-array-manager.count-threshold` (default 128, `HdfsClientConfigKeys.java:422-423`) —
  a length is only managed after more than this many allocations of that length within the reset
  window; `dfs.client.write.byte-array-manager.count-reset-time-period-ms` (default 10000,
  `HdfsClientConfigKeys.java:426-428`). The array length is driven by `dfs.client-write-packet-size`
  (default 65536, `HdfsClientConfigKeys.java:86-87`).
- How it is set: client-side configuration — the client's `hdfs-site.xml`, `-D` on a
  `GenericOptionsParser` tool, or `Configuration.setInt` in a client program. Read once when the
  `DfsClientConf` is built (`DfsClientConf.java:226`, `loadWriteByteArrayManagerConf` at
  `DfsClientConf.java:326-345`) and baked into the JVM-wide, name-keyed `ClientContext`
  (`ClientContext.java:181-182`, cache at `ClientContext.java:210-223`; context name from
  `dfs.client.context`, default `default`). A change therefore needs a **new client JVM** (or a
  different `dfs.client.context` name); no daemon restart and no refresh command apply — NameNode
  and DataNodes do not read it.
- Reader: the HDFS client (`DFSClient` → `DFSOutputStream` / `DFSStripedOutputStream`), i.e. any
  JVM that writes to HDFS: `hdfs dfs -put`, MapReduce tasks, HBase region servers, etc.

**A2. What it caps.** Client JVM **heap** held in packet buffers (`byte[]`) that `DFSOutputStream`
allocates for each outgoing data packet (`DFSOutputStream.java:136-152`). For each array length,
`FixedLengthManager` keeps `numAllocated` (managed arrays handed out and not yet recycled) and
`freeQueue` (recycled arrays retained for reuse). Two comparisons use `maxAllocated` (= `count-limit`):
- in-use: `numAllocated >= maxAllocated` blocks `allocate()` (`ByteArrayManager.java:166-177`);
- pooled (the target line): `freeQueue.size() < maxAllocated - numAllocated` decides whether a
  recycled array is retained (`ByteArrayManager.java:209`). The usage-side operand is
  `freeQueue.size()`; the limit-side operand is `maxAllocated` (minus current `numAllocated`).

Memory per length is therefore bounded by `count-limit × arrayLength` for the pool, and nominally
for pool + managed in-use together. With the default packet size the buffer is
`PKT_MAX_HEADER_LEN (33) + 126 × 516 = 65049` bytes, rounded up to 65536
(`DFSOutputStream.java:426-430`, `PacketHeader.java:61-64` with the 27-byte fixed-length header proto at `datatransfer.proto:236-243`, `ByteArrayManager.java:360-361`), so the
default 2048 means up to 128 MiB of pooled 64 KiB buffers per client JVM.

**A3. Mechanism.**
1. `DfsClientConf.loadWriteByteArrayManagerConf` returns `null` if `enabled` is false
   (`DfsClientConf.java:328-333`); otherwise `new ByteArrayManager.Conf(countThreshold, countLimit,
   countResetTimePeriodMs)` (`DfsClientConf.java:334-344`).
2. `ClientContext` calls `ByteArrayManager.newInstance(conf)` (`ClientContext.java:181-182`):
   `null` → `NewByteArrayWithoutLimit` (plain `new byte[size]`, `release` is a no-op,
   `ByteArrayManager.java:296-313`); otherwise `Impl`, whose `ManagerMap` is built with
   `conf.countLimit` (`ByteArrayManager.java:325-329`) and passes it to every
   `FixedLengthManager(arrayLength, countLimit)` (`ByteArrayManager.java:235-243`), stored as
   `maxAllocated` (`ByteArrayManager.java:148-151`).
3. Allocation: `DFSOutputStream.createPacket` → `byteArrayManager.newByteArray(33 + packetSize)`
   (`DFSOutputStream.java:140-143`). `Impl.newByteArray` rounds to a power of two (min 32), bumps
   the per-length counter, and creates the length's manager only once the count exceeds
   `countThreshold` (`ByteArrayManager.java:360-366`). With a manager: `allocate()` waits while
   `numAllocated >= maxAllocated` (`ByteArrayManager.java:166-177`), then increments
   `numAllocated` and reuses a pooled array if any, else `new byte[len]` (`ByteArrayManager.java:178-184`).
   Without a manager (below threshold): plain `new byte[powerOfTwo]` (`ByteArrayManager.java:372`).
4. Release: when a packet is acked the `ResponseProcessor` calls `one.releaseBuffer(byteArrayManager)`
   (`DataStreamer.java:1292`); on stream close/abort the queues are released (`DataStreamer.java:933-940`);
   a discarded packet on flush is released at `DFSOutputStream.java:679`. `DFSPacket.releaseBuffer`
   → `bam.release(buf)` (`DFSPacket.java:212-215`) → `Impl.release` looks up the manager for
   `array.length` **without creating one** and calls `recycle` (`ByteArrayManager.java:400-405`).
5. `recycle` (`ByteArrayManager.java:194-216`): `notify()` one waiting allocator, decrement
   `numAllocated`, clamp at 0 (`:202-207`), then the check at
   [`ByteArrayManager.java:209`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/util/ByteArrayManager.java#L209):
   - **true** (`freeQueue.size() < maxAllocated - numAllocated`): the array is offered to `freeQueue`
     and stays reachable from the `ClientContext` (which lives in a static cache for the JVM's
     life), i.e. retained heap;
   - **false**: the array is dropped and becomes garbage — this is the branch that holds the pool
     at or below `count-limit − numAllocated`.
   Return value is the pool size (`:215`), which is the observable used in B2.

Bypasses and overshoots:
- **Disabled by default.** With `enabled=false` there is no manager at all; client packet buffers
  are bounded only by `dfs.client.write.max-packets-in-flight` per stream (`DataStreamer.java:1004-1012`)
  times the number of open streams.
- **Below threshold.** The first `count-threshold` allocations of a length in each reset window are
  unmanaged `new byte[]` and are not counted in `numAllocated` (`ByteArrayManager.java:362-372`).
- **Count drift.** Unmanaged arrays released after the manager exists still go through `recycle`,
  decrement `numAllocated` (clamped at 0, `:203-207`, comment acknowledges it) and can be pooled.
  `numAllocated` then under-counts managed arrays still in use, so `allocate()` can hand out more
  than `count-limit` arrays at once (pool + in-use > `count-limit`). The pool itself stays
  `≤ count-limit` because `maxAllocated − numAllocated ≤ maxAllocated`.
- **Per length, not total.** Every distinct power-of-two length gets its own `count-limit`
  (`ByteArrayManager.java:235-243`); partial last packets, end-of-block packets (`createPacket(0,…)` →
  64-byte arrays, `DFSOutputStream.java:690`) and packets resized near block boundaries
  (`adjustChunkBoundary`) use other lengths. Total pooled heap is bounded by
  `count-limit × Σ lengths in use`, still finite (lengths ≤ `dfs.client-write-packet-size` rounded).
- **Heartbeat packets** use plain `new byte[PKT_MAX_HEADER_LEN]` (`DataStreamer.java:2132-2133`),
  outside the manager.
- **Never shrinks on idle.** Nothing removes arrays from `freeQueue` except `allocate()`; once the
  pool is filled it stays at that size for the JVM's life (the counter reset only affects
  manager creation).

**A4. Other consumers.** Client heap outside this constraint: the `FSOutputSummer` checksum/data
buffer per stream, `DFSPacket` objects themselves, the per-stream dataQueue/ackQueue bound
(`dfs.client.write.max-packets-in-flight`, default 80), read-side buffers (`BlockReaderRemote`,
short-circuit caches), RPC buffers, and the application's own heap. On the DataNode side,
`BlockReceiver`/`PacketReceiver` buffers are bounded by `dfs.data.transfer.max.packet.size`
(`HdfsClientConfigKeys.java:243-247`, `PacketReceiver.java:82-84,166`), not by this key.

**A5. Evidence beyond the source.**
- HDFS-7276 "Limit the number of byte arrays used by DFSOutputStream"
  (https://issues.apache.org/jira/browse/HDFS-7276), release note in
  `hadoop-common-project/hadoop-common/src/site/markdown/release/2.6.0/RELEASENOTES.2.6.0.md:132-146`
  ("The maximum number of arrays allowed for each array length. Default is 2048").
- HDFS-7358 "Clients may get stuck waiting when using ByteArrayManager"
  (https://issues.apache.org/jira/browse/HDFS-7358), `CHANGELOG.2.7.0.md:367`.
- Existing test `hadoop-hdfs-project/hadoop-hdfs-client/src/test/java/org/apache/hadoop/hdfs/util/TestByteArrayManager.java:109-207`
  (`testAllocateRecycle`, countLimit 8) asserts that the free queue tops out at `countLimit` and that
  "recycle one more; it should not increase the free queue size" (`:202-203`).
- Hadoop 3.4.2 `hdfs-default.xml` docs: https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/hdfs-default.xml

## B. Verification solution

**B1. Claim under test.** With `dfs.client.write.byte-array-manager.enabled=true`, the number of
packet buffers of one array length that the HDFS client retains in its pool never exceeds
`dfs.client.write.byte-array-manager.count-limit`, so the client heap retained by the pool after a
write burst is `≈ min(count-limit, peak buffers of that length) × arrayLength` and moves with
`count-limit`; with the manager disabled, nothing is retained.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 8, Maven 3.3+. Copy the tree to local disk
(`rsync -a <source>/ /mydata/<run>/hadoop-3.4.2/`) and work only in the copy. Build:
`mvn -pl hadoop-hdfs-project/hadoop-hdfs-client -am install -DskipTests -Dmaven.javadoc.skip=true`.
New test class (in the copy):
`hadoop-hdfs-project/hadoop-hdfs-client/src/test/java/org/apache/hadoop/hdfs/util/TestByteArrayManagerCountLimitPool.java`,
package `org.apache.hadoop.hdfs.util` (needed for package-private `Impl`, `getManagers()`,
`FixedLengthManager`), JUnit 4 (`org.junit.Test`, `org.junit.Assert`) as in `TestByteArrayManager`.
JVM options: `-Dmaven-surefire-plugin.argLine="-Xmx1g -XX:+UseSerialGC"` (the property is the
surefire argLine at `hadoop-project/pom.xml:187`); SerialGC makes post-`System.gc()` heap readings
stable.

> **A1 (stage-4 audit, 2026-11-24, before any reading) — B2a, B2e steps 1, 3, 6.** Node `pc99`, JDK `1.8.0` at
> `/usr/lib/jvm/java-8-openjdk-amd64`, Maven 3.6.3. Copy with `jingsong/copy-source.sh /mydata/jingsong-s4/<stem>-run1/src`
> (the repository's `systems/hadoop/source/`, tag `rel/release-3.4.2`). **No `install` build**: it would overwrite the shared
> `~/.m2` 3.4.2 artifacts; the node's full build already installed them, so step 3 runs directly in the copy:
> `mvn -B test -pl hadoop-hdfs-project/hadoop-hdfs-client -Dtest=TestByteArrayManagerCountLimitPool -Dmaven-surefire-plugin.argLine="-Xmx1g -XX:+UseSerialGC -Dbam.mode=<mode>"`
> with `<mode>` = `managed` (cases 1–3 and the wiring check), `disabled` (step 5: the case-1 workload on
> `newInstance(null)`), `mutation` (step 6: line 209 → `if (true) {` by `sed` in the copy, case 1 only, compiled into the
> copy's `target/classes`, never installed; reverted with `git checkout`, `git diff --stat` empty afterwards). Surefire
> exit codes are not read (Hadoop's surefire does not fail on test failures): the test class prints CSV lines and the
> surefire counts are read. The test's printed JVM arguments and GC names confirm the argLine reached the fork.

**B2b. Knobs.** `countLimit` L ∈ {1, 4, 16, 64, 1024} (passed as
`new ByteArrayManager.Conf(countThreshold, L, 10000)`; this is exactly what `DfsClientConf` builds
from the key). Also check that `DfsClientConf` wires the key: build
`new DfsClientConf(conf)` with `conf.setBoolean("dfs.client.write.byte-array-manager.enabled", true)`
and `conf.setInt("dfs.client.write.byte-array-manager.count-limit", 16)` and assert the resulting
manager's `FixedLengthManager.toString()` reports `/16`. L=1 is the extreme, 1024 makes the heap
delta large (64 MiB of 64 KiB arrays) and 16/64 are in between; 2048 is avoided only to keep the
test heap small (2048 × 64 KiB = 128 MiB would also fit). `countThreshold` = 0 for cases 1–2, 16 for
case 3.

> **A2 (stage-4 audit, 2026-11-24) — B2b wiring check, B2d heap reading, B2h repetitions.** Wiring check made exact:
> a `Configuration(false)` with `enabled=true`, `count-limit=16`, `count-threshold=0`, passed through
> `ClientContext.get("bam-wire-on", new DfsClientConf(conf), conf).getByteArrayManager()` (the client's own path,
> `ClientContext.java:181-182`); the manager must be `Impl` and, after one `newByteArray(65049)`, its 65536 manager string
> must be `[65536: 1/16, free=0]`; with `enabled` unset the class must be `NewByteArrayWithoutLimit`. Heap reading:
> one `byte[65536]` is 65,552 bytes on this JVM (16-byte header); an instrument known answer (one retained 64 KiB array,
> same GC routine) is printed first. Case 1 runs one unrecorded warm-up pass (L = 4), then **three repetitions** of
> L ∈ {1, 4, 16, 64, 1024}, each with a fresh manager; the extra arrays are allocated one by one just before their
> release. One surefire JVM per mode.

**B2c. Workload.** Array request size 65049 (the default packet buffer, rounds to 65536).
- Case 1 (pool cap, managed arrays): `bam = ByteArrayManager.newInstance(new Conf(0, L, 10000))`;
  allocate exactly L arrays from the test thread (never blocks: `numAllocated` goes 0→L), release all
  L, then release X = L + 10 extra `new byte[65536]` arrays.
  Arithmetic: during the L releases, after k releases `numAllocated = L−k` and pool `= k−1 < k`, so
  each is pooled → pool L; each extra release sees `L < L − 0` false → dropped. Without the line-209
  check the pool would reach `2L + 10`.
- Case 2 (in-use cap): after case 1, allocate L arrays (all from the pool), then start one more
  allocator thread; it must be in `WAITING` until one array is released.
- Case 3 (unmanaged arrays released into the manager): `new Conf(16, 4, 60000)`; allocate 20 arrays
  (first 16 unmanaged, #17 creates the manager, #17–20 managed, `numAllocated=4`); release the 16
  unmanaged first, then the 4 managed. Pool must end at 4 (not 20), because each release after the
  4th sees `4 < 4 − 0` false. Record `toString()` after each release: `numAllocated` reaches 0 after
  the 4th unmanaged release while the 4 managed arrays are still held (the drift in A3).

**B2d. Observables and instruments.**
- The check's operand: the return value of `bam.release(array)` (= `freeQueue.size()`,
  `ByteArrayManager.java:215`) after every release, and
  `((ByteArrayManager.Impl) bam).getManagers().get(65536, false).toString()`
  (`"[65536: numAllocated/maxAllocated, free=n]"`, `ByteArrayManager.java:219-222`).
- Retained heap: `ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed()` after
  `System.gc()` three times with 200 ms sleeps, taken (a) right after creating `bam`, (b) after
  case 1 with all test-local references to arrays nulled (only the pool keeps them). Δ = (b) − (a).
- Thread state of the extra allocator (`Thread.getState()`) for case 2.
- Not directly observable: which particular arrays are pooled (irrelevant); heap noise below
  ~1 MiB, so for L ≤ 16 only the pool size (not Δ) is decisive.

> **A8 (stage-4 run-1 defect fix, 2026-11-24, unit tier restarted) — B2d retained-heap instrument.** Run 1's first
> unit attempt matched B2g/A4 row U5 (**Invalid**): the instrument known answer read −4,487,112 B and the disabled control's
> |Δ| reached 5,726,512 B, with offsets in steps of ≈ 2,863,000 B (the eden pool's `used` grows in whole thread-local
> allocation buffers, so a reading taken after `System.gc()` carries 0, 1 or 2 fresh TLABs). Fix: "heap used" in B2d is
> the sum of the **non-eden heap pools** (Serial: `Survivor Space` + `Tenured Gen`, `MemoryPoolMXBean`) after the same
> `System.gc()` ×3 routine; the `MemoryMXBean` total is still printed for comparison. Claim, predictions (A3) and
> conclusions (A4, including its Invalid conditions) are unchanged; the unit tier restarts from its beginning
> (results §3, defect D1).

> **A9 (stage-4 run-1 defect fix, 2026-11-24, unit tier restarted again) — B2d/B2e: one JVM per heap reading.** The
> second unit attempt (with A8) also matched row U5 (**Invalid**): the managed-mode instrument known answer read
> −1,626,144 B, and readings taken later in the same surefire JVM carried part of an earlier iteration's arrays (for example
> heapA = 6,266,096 B before L = 1024 rep 2 against ≈ 2.07 MB elsewhere). This is the shared-JVM carry-over named in the
> closed-case notes (method lesson 1). Fix: the surefire test (still run by `mvn test` as in A1) starts **one child JVM per
> reading**, using the same `java`, the same classpath, `-Xmx1g -XX:+UseSerialGC` and the same `bam.mode`: one child for the
> known answer and one per (L, repetition) of case 1. Each child does one unrecorded warm-up pass (L = 4) before its
> reading. Cases 2 and 3 and the wiring check stay in the surefire JVM (they read no heap). Claim, predictions (A3) and
> conclusions (A4) are unchanged. The unit tier restarts from its beginning (results §3, defect D2).

**B2e. Procedure.**
1. Copy tree, build as in B2a.
2. Write the test class with one `@Test` per case, case 1 looped over L ∈ {1,4,16,64,1024} with a
   fresh `bam` each time; print one line per L: `L, poolAfterManagedReleases, maxPoolDuringExtraReleases, heapDeltaBytes`.
3. Run `mvn -pl hadoop-hdfs-project/hadoop-hdfs-client test -Dtest=TestByteArrayManagerCountLimitPool -Dmaven-surefire-plugin.argLine="-Xmx1g -XX:+UseSerialGC"`.
4. Collect output from `hadoop-hdfs-project/hadoop-hdfs-client/target/surefire-reports/`.
5. Positive control run: same test with `ByteArrayManager.newInstance(null)` (the disabled path):
   every `release` returns 0 and heap Δ ≈ 0.
6. Optional mutation control (in the copy only): change line 209 to `if (true)`, rebuild the module,
   rerun case 1; pool must climb to `2L + 10`. Revert.

**B2f. Predictions.**
| L | pool after L managed releases | max pool during L+10 extra releases | heap Δ (approx.) |
|---|---|---|---|
| 1 | 1 | 1 | ≈ 64 KiB (in noise) |
| 4 | 4 | 4 | ≈ 256 KiB (in noise) |
| 16 | 16 | 16 | ≈ 1 MiB |
| 64 | 64 | 64 | ≈ 4 MiB |
| 1024 | 1024 | 1024 | ≈ 64 MiB (± a few MiB) |
- Case 2: the (L+1)-th allocator is `WAITING` while L are out, `TERMINATED` within 100 ms of one release.
- Case 3: pool ends at 4; `numAllocated` reaches 0 while 4 managed arrays are still held (drift).
- Disabled control: release returns 0 always; Δ ≈ 0.
- Mutation control: pool `= 2L + 10` (e.g. 2058 for L=1024 → Δ ≈ 128 MiB).

> **A3 (stage-4 audit, 2026-11-24) — B2f in numbers.** Pool values are exact (deterministic code). Heap Δ, in every
> repetition: L = 64: 3,145,728 ≤ Δ ≤ 6,292,480 (L × 65,536 − 1 MiB … L × 65,552 + 2 MiB); L = 1024:
> 66,060,288 ≤ Δ ≤ 69,222,400; L ∈ {1, 4, 16}: recorded, not decisive (≤ L × 65,552 + 2 MiB expected). Disabled
> control: every `release` returns 0, |Δ| ≤ 1,048,576 for every L. Mutation control: pool after the managed releases = L,
> final pool = 2L + 10 for every L, and at L = 1024 Δ ≥ 133,824,512. Case 2: the extra allocator is `WAITING` 500 ms after
> it starts and `TERMINATED` within 1 s of the release (100 ms in B2f is replaced: thread scheduling, not the claim).
> Case 3: pool ≤ 4 after every release and = 4 at the end; `numAllocated` = 0 after the 4th unmanaged release.
> Wiring: per A2.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| Pool = L after managed releases and stays L through the extra releases; Δ ≈ L × 64 KiB for L=64, 1024 | Claim holds at the mechanism level: pool and retained heap follow `count-limit`. |
| Pool exceeds L at any point (with line 209 unmodified) | Claim wrong: the check does not cap the pool. |
| Δ does not grow with L (e.g. 64 MiB at L=1024 not seen) while pool = L | Pool count capped but arrays not actually retained (or GC reading wrong) — check instrument; claim about heap not confirmed. |
| Mutation control pool = 2L+10 | Confirms line 209 is the operative cap. |
| Mutation control pool = L | Something else caps the pool; line 209 is not the mechanism. |
| Extra allocator not blocked in case 2 | In-use cap (line 166) not working; the pool claim may still hold. |
| Disabled control retains heap | Measurement artefact; Δ readings unreliable. |

> **A4 (stage-4 audit, 2026-11-24) — B2g verdict words and missing rows.** Claim tested = B1. Rows, in order:
> (U1) **Confirmed — caps**: every A3 pool and Δ reading holds in all three repetitions, case 3 holds, the wiring check
> holds, the disabled control holds and the mutation control reaches 2L + 10. (U2) **Refuted — does not cap**: the pool
> exceeds L (or 4 in case 3) at any point with line 209 unmodified. (U3) **Not confirmed**: pools hold but a decisive Δ
> (L = 64 or 1024) is outside its A3 bounds in any repetition (heap claim not confirmed). (U4) **Not confirmed**: the
> mutation control's pool stays at L (line 209 is not the operative cap). (U5) **Invalid**: the disabled control returns
> non-zero or |Δ| > 1 MiB, the wiring check fails, the known answer is outside 65,536 ± 64 KiB, or the argLine (1 GiB heap,
> Serial GC) did not reach the fork. Case 2 not blocking is recorded as a finding about `allocate()` and does not change
> rows U1–U4.

**B2h. Controls.** Disabled-manager run (no pool, same workload); mutation of line 209 (shows the
check, not `allocate()`, bounds the pool); fresh `bam` per L (no carry-over); heap readings after
forced GC with SerialGC and test-local references nulled; repeat each L three times.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, pseudo-distributed HDFS (1 NameNode, 1 DataNode)
from a distribution built from the copy:
`mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`, untar
`hadoop-dist/target/hadoop-3.4.2.tar.gz` to `/mydata/<run>/hadoop-3.4.2`. JDK 8.
`HADOOP_LOG_DIR=/mydata/<run>/logs`, `HADOOP_PID_DIR=/mydata/<run>/pids`,
`HADOOP_HEAPSIZE_MAX=1g` for the daemons.
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000` (pick a free port), `hadoop.tmp.dir=/mydata/<run>/tmp`.
- `hdfs-site.xml` (daemons): `dfs.replication=1`, `dfs.namenode.name.dir=/mydata/<run>/nn`,
  `dfs.datanode.data.dir=/mydata/<run>/dn` (local disk with ≥ 10 GiB free),
  `dfs.blocksize=268435456` (256 MiB, so no block boundary inside a 64 MiB file).
- Client: a small program `org.apache.hadoop.hdfs.util.BamProbe` (package chosen so it can read the
  manager state as a cross-check; the class is on the client classpath via `HADOOP_CLASSPATH`),
  compiled with `javac -cp $(hadoop classpath) BamProbe.java`. It:
  1. builds a `Configuration` and sets from its args: `dfs.client.write.byte-array-manager.enabled`,
     `…count-limit`, `…count-threshold`, `dfs.client-write-packet-size=1048576`,
     `dfs.client.write.max-packets-in-flight=4`;
  2. opens one `FileSystem` (one `DFSClient`, one `ClientContext`);
  3. starts T threads behind a `CyclicBarrier`; each creates `/bam/<run>/f<i>`, writes S bytes in 64 KiB
     `write()` calls, closes;
  4. after all join: sleeps 2 s, `System.gc()` ×3, prints heap used (MemoryMXBean), and
     `((Impl) dfs.getClient().getClientContext().getByteArrayManager()).getManagers().get(1048576,false)`
     `.toString()` (or "no manager");
  5. sleeps 60 s (window for external `jcmd`), then exits.
  Run with `HADOOP_CLIENT_OPTS="-Xmx1g -XX:+UseSerialGC" HADOOP_CLASSPATH=<dir> hadoop org.apache.hadoop.hdfs.util.BamProbe <args>`
  (`hadoop CLASSNAME` runs a class with the client classpath).
- Array length: with packet size 1048576, chunks = ⌊(1048576−33)/516⌋ = 2032, buffer =
  33 + 2032×516 = 1048545 → rounded to **1048576 (1 MiB)**, distinctive and large, so each pooled
  array is exactly 1 MiB (+16 B header).

> **A5 (stage-4 audit, 2026-11-24) — B3a, B3e steps 1, 2, 5.** The distribution is the node's full build of the same
> source and tag, `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2`, copied to
> `/mydata/jingsong-s4/<stem>-run1/hadoop` (no second dist build). SSH to `localhost` has no key, so `start-dfs.sh` /
> `stop-dfs.sh` are replaced by `hdfs --daemon start|stop namenode|datanode`; no SecondaryNameNode. Non-default ports (the
> node is shared): `fs.defaultFS=hdfs://localhost:19300`, NN http 19370 / https 19371, DN 19366 / http 19364 / ipc 19367.
> `HADOOP_CONF_DIR`, logs, PIDs, `hadoop.tmp.dir`, `nn`, `dn` under the run folder; `HADOOP_HEAPSIZE_MAX=1g` for the
> daemons only; `hdfs dfsadmin -safemode wait` before the first write. The probe is compiled with JDK 8 `javac` against
> `hadoop classpath` and run as in B3a (`HADOOP_CLIENT_OPTS="-Xmx1g -XX:+UseSerialGC"`), with a 900 s timeout per run.
> Repetitions are interleaved (rep 1 of every run, then rep 2, then rep 3).

**B3b. Knobs.** Client-side only (program args → `Configuration`; no daemon restart, a new client
JVM per run):
- `count-limit` L ∈ {8, 16, 32} (all below T=64 so the cap binds) and L = 4096 (above any reachable
  peak: positive control where the cap does not bind).
- `count-threshold` 0 for the main series; one extra run with threshold 32, L=8 (unmanaged arrays
  released into the pool, A3).
- `enabled=false` baseline (no manager).

**B3c. Workload.** T = 64 concurrent writers, S = 64 MiB each (4 GiB total; a full packet carries 2032 × 512 = 1040384 data bytes, so 65 data
packets per file, all with 1 MiB buffers because `writeChunk` always requests the full `packetSize`,
`DFSOutputStream.java:493-495`, plus one 64-byte end-of-block packet at close). Each open stream holds at least its `currentPacket` buffer while writing and
up to `max-packets-in-flight + 1 = 5` queued packets (`DataStreamer.java:1010-1011`), so the demand
for 1 MiB buffers is between 64 and 64 × 6 = 384 concurrently. With L < 64 the manager saturates
(`numAllocated = L`, writers block at `ByteArrayManager.java:172`) and every array ever created is
one of ≤ L (pool + in-use ≤ L, threshold 0); at the end all are recycled, pool = L. With L = 4096
the pool equals the peak number of distinct 1 MiB arrays (≥ 64, ≤ 384). Duration: a few minutes.
Disk: 4 GiB per run on `/mydata`; delete between runs (`hdfs dfs -rm -r -skipTrash /bam`).

**B3d. Observables and instruments.**
- Actual resource: client JVM heap retained after the burst —
  `jcmd <pid> GC.class_histogram | grep '\[B'` (total bytes of `byte[]`, the command triggers a full GC),
  sampled 3 times 10 s apart during the 60 s window; plus the program's own MemoryMXBean reading;
  `jcmd <pid> GC.heap_info` for context. Retained pool ≈ `[B` bytes(run) − `[B` bytes(disabled baseline).
- Cross-check (mechanism): the printed `"[1048576: n/L, free=k]"` string.
- Workload sanity: `hdfs dfs -du -s /bam/<run>` = 64 × 64 MiB; writer wall time.
- Not directly observable: peak in-use count during the burst (only inferred: pool at the end for
  the uncapped control is the peak); per-array identity.

**B3e. Procedure.**
1. Build the distribution from the local copy; untar to `/mydata/<run>/`; write configs (B3a).
2. `hdfs namenode -format -nonInteractive`; `start-dfs.sh`; `jps` shows NameNode, DataNode
   (SecondaryNameNode optional); `hdfs dfsadmin -report` shows ≥ 10 GiB remaining.
3. Compile `BamProbe` against `$(hadoop classpath)`.
4. For each run R in [disabled; L=8,16,32,4096 at threshold 0; L=8 at threshold 32], three repetitions:
   a. `hdfs dfs -rm -r -skipTrash /bam` (ignore "not found");
   b. start `BamProbe` in background with R's args, note its pid (`jps -l | grep BamProbe`);
   c. when it prints the post-GC line, take three `jcmd <pid> GC.class_histogram | grep '\[B'` samples;
   d. wait for exit; record printed heap, manager string, `[B` bytes.
5. `stop-dfs.sh`; `jps` must show nothing from this run; remove `/mydata/<run>/{nn,dn,tmp}` if done.

**B3f. Predictions.** Let B = `[B` bytes in the disabled baseline (expected: a few MiB).
| Run | manager string | `[B` bytes − B |
|---|---|---|
| disabled | "no manager" | 0 (± 2 MiB) |
| L=8, thr 0 | `[1048576: 0/8, free=8]` | ≈ 8 MiB |
| L=16, thr 0 | `[1048576: 0/16, free=16]` | ≈ 16 MiB |
| L=32, thr 0 | `[1048576: 0/32, free=32]` | ≈ 32 MiB |
| L=4096, thr 0 (control) | `free=k` with 64 ≤ k ≤ 384 | ≈ k MiB, ≥ 64 MiB |
| L=8, thr 32 | `free=8` (not up to 40) | ≈ 8 MiB |
Relation: retained bytes grow linearly with L, slope ≈ 1 MiB per unit of L, while L < 64; the uncapped
control is at least twice the L=32 value. Writers complete in all runs (no deadlock, HDFS-7358).
The only other managed length in this workload is 64 bytes (end-of-block packets, `createPacket(0,…)`),
which adds at most L × 64 B — negligible; so the `[B` delta should be L MiB within ±2 MiB.

> **A6 (stage-4 audit, 2026-11-24) — B3d/B3f in numbers.** A run's reading = the median of its three `[B` byte totals
> (`jcmd <pid> GC.class_histogram`, 10 s apart, starting when the probe prints its post-GC line). B = the median of the
> three disabled repetitions' readings; delta = reading − B. One pooled 1 MiB array = 1,048,592 bytes. In every
> repetition: L = 8 (threshold 0 and threshold 32): manager string `[1048576: 0/8, free=8]`, 6,291,584 ≤ delta ≤ 10,485,888;
> L = 16: `[1048576: 0/16, free=16]`, 14,680,320 ≤ delta ≤ 18,874,624; L = 32: `[1048576: 0/32, free=32]`,
> 31,457,792 ≤ delta ≤ 35,652,096; L = 4096: `free=k` with 64 ≤ k ≤ 384 and |delta − k × 1,048,592| ≤ 2 MiB; disabled:
> "no manager" and each repetition within B ± 2 MiB. Workload, every run: all 64 writers finish (probe exit 0) and
> `hdfs dfs -du -s /bam/<run>` = 4,294,967,296.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| `free` = L and `[B` delta ≈ L MiB (±2 MiB) for L = 8, 16, 32; control ≥ 64 MiB; disabled ≈ 0 | Claim confirmed: retained client heap follows `count-limit`. |
| `free` > L, or `[B` delta clearly > L MiB + 2 MiB for a capped run | Claim wrong: the limit does not cap the retained pool (or another length/consumer dominates — check histogram by running `jmap -histo:live` and a heap dump). |
| Delta flat across L = 8…32 and equal to control | Limit not applied (check that `enabled=true` reached the `ClientContext`; a reused context name would keep an old conf). |
| Control < 64 MiB | Writers did not overlap, so the capped runs may not have reached the cap either — not confirmed; rerun with more writers (T = 128) or a start barrier plus a larger S. |
| Threshold-32 run `free` > 8 | Line 209 does not bound unmanaged releases — claim wrong. |
| Writers hang | HDFS-7358-type stall; record thread dump (`jcmd <pid> Thread.print`); claim about memory still readable but note liveness issue. |

> **A7 (stage-4 audit, 2026-11-24) — B3g verdict words.** Claim tested = B1. (C1) **Confirmed — caps**: every A6 reading
> holds. (C2) **Refuted — does not cap**: `free` > L in any capped run (threshold 32 included), or the deltas of L = 8, 16, 32
> are flat and equal to the control while the manager strings show the intended `/L`. (C3) **Not confirmed**: the control's
> `free` < 64 or its delta < 64 MiB − 2 MiB (cap not reached); a capped run has `free` = L but delta outside its band
> (another consumer or retention; record `jmap -histo:live`); writers hang (thread dump). (C4) **Invalid**: an enabled run
> prints "no manager" or a limit other than L, the disabled run prints a manager, a `-du` mismatch, or the probe heap is not
> 1 GiB.

**B3h. Controls.** Disabled baseline with identical workload (subtracts all non-pool `byte[]`);
uncapped L=4096 as positive control showing the workload does create more than 32 buffers; fresh
client JVM per run (no `ClientContext` carry-over); `dfs -du` to show every run wrote the same data;
three repetitions; the manager string ties the heap reading to the mechanism.

**B4. Risks and cleanup.** Build and data only under `/mydata/<run>/` on local disk, never in the
shared tree or shared storage. Up to 4 GiB in HDFS per run plus NN metadata; remove `/bam` between
runs and `rm -rf /mydata/<run>/{nn,dn,tmp,logs}` at the end. Client JVM ≤ 1 GiB heap, daemons
≤ 1 GiB each — check `free -g` first. Ports: change NN RPC (9000) and the default HTTP/DataNode
ports if another instance runs on the host (`dfs.namenode.http-address`, `dfs.datanode.address`,
`dfs.datanode.http.address`, `dfs.datanode.ipc.address`). Stop with `stop-dfs.sh`, kill any
leftover `BamProbe`, and confirm with `jps` that no NameNode, DataNode, SecondaryNameNode or BamProbe
of this run remains. Unit tier: surefire JVM exits by itself; delete the copied test class if the copy
is reused.

## C. Sources read

hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/util/ByteArrayManager.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/HdfsClientConfigKeys.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/impl/DfsClientConf.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/ClientContext.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DFSOutputStream.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DataStreamer.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DFSPacket.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DFSStripedOutputStream.java (grep only)
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DFSClient.java (grep only)
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DistributedFileSystem.java (grep only)
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/datatransfer/PacketHeader.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/datatransfer/PacketReceiver.java (grep only)
hadoop-hdfs-project/hadoop-hdfs-client/src/main/proto/datatransfer.proto
hadoop-hdfs-project/hadoop-hdfs-client/src/test/java/org/apache/hadoop/hdfs/util/TestByteArrayManager.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java (grep only)
hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
hadoop-common-project/hadoop-common/src/site/markdown/release/2.6.0/RELEASENOTES.2.6.0.md
hadoop-common-project/hadoop-common/src/site/markdown/release/2.7.0/CHANGELOG.2.7.0.md
hadoop-project/pom.xml (surefire argLine)
https://issues.apache.org/jira/browse/HDFS-7276
https://issues.apache.org/jira/browse/HDFS-7358

## D. Stage-4 feedback

none yet
