# DUMP_WRITE_WATER_MARK — verification solution  <!-- file: cases/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`OpenFileCtx.java:278`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java#L278) — `if (nonSequentialWriteInMemory.get() < DUMP_WRITE_WATER_MARK) { return; }` in `OpenFileCtx.waitForDump()` (NFS gateway) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive` — with dumping enabled (the default), a WRITE that leaves an open file's buffered out-of-order data at or above `DUMP_WRITE_WATER_MARK` (1 MiB) is held until the Dumper thread has spilled that data to the local dump file, so the NFS gateway heap held by out-of-order write data stays under about 1 MiB per open file once each such WRITE returns. Caveats: the cap is per open file (not gateway-wide), it can be exceeded by one WRITE per waiting RPC thread, and the spilled data goes to `nfs.dump.dir` with no cap at all. |
| Ground | — |

Name parts: constraint `DUMP_WRITE_WATER_MARK` (a hard-coded constant); function `waitForDump`
(the method holding the given if statement, which is also the main enforcement point); operand
`DUMP_WRITE_WATER_MARK` (the limit-side operand at line 278).

## A. Constraint trace

**A1. The constraint.**
- Name: `DUMP_WRITE_WATER_MARK`. Kind: hard-coded constant (`private static long`, **not**
  `final`), declared at
  [`OpenFileCtx.java:73`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java#L73)
  (`private static long DUMP_WRITE_WATER_MARK = 1024 * 1024;`, comment at :72 "Pending writes water
  mark for dump, 1MB").
- Unit: bytes. Default 1,048,576 (1 MiB). There is no configuration key, no `*-default.xml` entry
  and no setter: nothing in the tree writes the field after class initialization (grep of
  `hadoop-hdfs-project` finds only :73, :278, :284, :294, :379, :383). It can only be changed by
  editing the source and rebuilding `hadoop-hdfs-nfs`, or by reflection inside a JVM (it is not
  `final`, so `Field.setLong` works and is not constant-folded).
- Only the documentation mentions it, as a prose number: `hdfs-default.xml:2281-2288`
  (`nfs.dump.dir`: "out-of-order writes are dumped after they are accumulated to exceed certain
  threshold (e.g., 1MB) in memory") and `HdfsNfsGateway.md:120-131`.
- Related keys that decide whether the constant has any effect (NfsConfigKeys.java):
  `nfs.file.dump` (:29-30, default `true`; no `hdfs-default.xml` entry), `nfs.dump.dir` (:31-32,
  default `/tmp/.hdfs-nfs`), `nfs.wtmax` (:36-37, 1 MiB, the largest single WRITE), 
  `nfs.max.open.files` (:41-42, 256 open-file contexts), `nfs.stream.timeout` (:44-46, 10 min,
  minimum 10 s). All are read from `hdfs-site.xml` by the NFS gateway at startup; changes need a
  gateway restart (`HdfsNfsGateway.md:129-131`).
- Read by: the HDFS NFS gateway daemon (`hdfs --daemon start nfs3`, class `Nfs3`), per open file
  (`OpenFileCtx` instance).

**A2. What it caps.** NFS gateway JVM heap held by **out-of-order (non-sequential) WRITE data of one
open file** that is still waiting for the data before it (a hole) to arrive. The usage-side
quantity is the per-file counter `nonSequentialWriteInMemory` (`OpenFileCtx.java:178-179`, an
`AtomicLong` created at :248): the sum of `count` of buffered WRITEs whose state is `ALLOW_DUMP`
and whose `byte[]` is still in memory. The code compares it with `DUMP_WRITE_WATER_MARK` at :278,
:284, :294 (writer side) and :379, :383 (Dumper side). Data above the mark is moved to local disk
(the per-file dump file `<nfs.dump.dir>/<fileId>`); the constant does not cap that disk use.

**A3. Mechanism.**
1. An NFS WRITE reaches `WriteManager.handleWrite` (`WriteManager.java:122`), which finds or creates
   the file's `OpenFileCtx` with dump path `nfs.dump.dir + "/" + fileId` (`WriteManager.java:182-185`;
   the CREATE path does the same at `RpcProgramNfs3.java:1013-1015`) and calls
   `receivedNewWrite` → `receivedNewWriteInternal` (`OpenFileCtx.java:426-467`, :642).
2. `addWritesToCache` (synchronized, :515-587) builds a `WriteCtx` holding the request's `byte[]`
   (`WRITE3Request.deserialize` copies the payload with `readFixedOpaque`, `WRITE3Request.java:36-42`).
   If the WRITE's offset is beyond `nextOffset` (a hole), its state is `ALLOW_DUMP` (:562-563) and
   the counter is raised by `count` (:570-573, `updateNonSequentialWriteInMemory`, :211-220); the
   entry goes into `pendingWrites` (:577). In-order WRITEs are `NO_DUMP` and not counted.
3. `checkAndStartWrite` (:623-640) returns false for an out-of-order WRITE, so
   `waitForDump()` is called (:657-659) **before** the WRITE reply is sent (:673-681).
4. `waitForDump` (:272-302): returns at once if dumping is disabled (`enabledDump` false, :273-276;
   `enabledDump = dumpFilePath != null`, :251). Otherwise the check
   [`OpenFileCtx.java:278`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java#L278):
   - counter `< DUMP_WRITE_WATER_MARK` → return; the WRITE is acknowledged with its data kept in
     heap.
   - counter `>= DUMP_WRITE_WATER_MARK` → under the context lock, re-check (:284), start the
     `Dumper` daemon thread on first use (:286-288) or `notifyAll` it (:290), then **block the RPC
     thread** in `this.wait()` while the counter is still `>=` the mark (:294-299). The WRITE reply
     is delayed until then.
5. `Dumper.run` (:376-406) calls `dump()` while the counter is `>=` the mark (:379-380). `dump()`
   (:306-373) creates the dump file once (`createNewFile`, :308-317) and a read handle (:334-336),
   then walks `pendingWrites` (largest offset first, comparator at :237-238) while the counter is
   `> 0` (:348-350); each `WriteCtx.dumpData` (`WriteCtx.java:150-183`) appends the `byte[]` to the
   dump file, sets `data = null`, state `DUMPED`, and the counter drops by `count` (:358-361). So a
   dump round empties the counter to 0 (every `ALLOW_DUMP` entry is spilled, not just the excess).
   Then, under the lock, counter `<` mark → `notifyAll` (wakes the waiting writer) and wait (:382-392).
6. When the hole is filled, the write-back task writes entries in order; a `DUMPED` entry is read
   back from the dump file into a fresh `byte[]` (`WriteCtx.getData`/`loadData`, `WriteCtx.java:215-242`);
   an `ALLOW_DUMP` entry written back lowers the counter (`OpenFileCtx.java:1152-1156`).
7. The dump file is deleted only in `cleanup()` (:1218, delete at :1262-1273), i.e. when the stream
   is closed by the stream monitor after `nfs.stream.timeout` (scan every 5 s,
   `OpenFileCtxCache.java:240-261`) or evicted (`OpenFileCtxCache.java:142`).

Outcome when the limit is reached: the writer is throttled (the WRITE is not acknowledged) until
heap-held out-of-order data is back below the mark; data moves from heap to the dump file.

Bypasses and overshoots:
- **Per-write overshoot.** The counter is raised before the check, so it peaks at up to
  `mark - 1 + count` (up to `nfs.wtmax` = 1 MiB more) before the dump.
- **Concurrent overshoot.** `wait()` releases the context lock, so other RPC threads writing the
  same file can still enter `addWritesToCache` and add more (each then waits): up to one extra WRITE
  per concurrent writer thread.
- **Per file only.** The counter is an instance field; with up to `nfs.max.open.files` = 256 open
  contexts the gateway-wide total is about 256 × (1 MiB + overshoot).
- **In-order pending data is not counted.** `NO_DUMP` entries waiting for write-back (:562) are
  never compared with the mark.
- **Dumping off.** With `dumpFilePath == null`, `waitForDump` returns at once (:273-276) and the
  counter is unbounded. Note: `nfs.file.dump=false` does **not** produce a null path in the trace:
  `RpcProgramNfs3` sets its own `writeDumpDir = null` and skips creating the directory
  (`RpcProgramNfs3.java:200-215`), but `WriteManager` re-reads `nfs.dump.dir` and always passes a
  non-null path (`WriteManager.java:182-185`), and the CREATE path passes the string
  `"null/<fileId>"` (`RpcProgramNfs3.java:1013-1014`). Dumping therefore stays enabled and only
  stops when creating the dump file fails.
- **Dump failure.** If creating or writing the dump file throws `IOException` (directory missing,
  disk full), `enabledDump` is set false and `dump()` returns (:318-330, :362-367); `run()` then
  exits its loop without `notifyAll` because the counter is still `>=` the mark (:383). From the
  trace, the writer waiting at :294-299 is then never woken (the write-back path at :1152-1156 does
  not notify), so the RPC thread for that client stays blocked rather than the heap growing. (A
  `Throwable` other than `IOException`, such as the `IllegalStateException` from :314-315, is
  caught at :396-403, which does `notifyAll` and marks the context inactive.)
- **Counter drift (race).** If two threads add the same range, the counter is raised (:572) but the
  second `WriteCtx` is not stored (:575-584), so those bytes are never subtracted; the counter can
  then stay at or above the mark with nothing left to dump.

**A4. Other consumers.**
- The dump files in `nfs.dump.dir` (default `/tmp/.hdfs-nfs`, cleared at gateway start,
  `RpcProgramNfs3.java:232-245`): unbounded, about the total out-of-order data per file, and kept
  until the stream is cleaned up (`OpenFileCtx.java:1262-1273`). The docs only advise sizing it
  (`HdfsNfsGateway.md:120-128`).
- Heap held by in-order pending writes (`NO_DUMP`), by `WriteCtx`/`OffsetRange` objects and map
  nodes for dumped entries (data null, but one object set per WRITE, not counted), by read-back
  buffers during write-back (`WriteCtx.java:229-242`), by the `DFSClient` output stream buffers
  (`dfsClient.append`, `WriteManager.java:153`), by Netty receive buffers, and by READ handling.
- Other open files, each with its own counter (A3).

**A5. Evidence beyond the source.**
- `hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml:2281-2288` (`nfs.dump.dir`
  description naming the ~1 MB threshold).
- `hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/HdfsNfsGateway.md:120-136` (dump directory
  sizing advice; restart needed), `:202-225` (portmap/nfs3 start/stop), `:280-282` (mount, wsize,
  `nfs.wtmax`); online: https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/HdfsNfsGateway.html
- HDFS-7259, cited in the source comment at `OpenFileCtx.java:82-98` (commit handling for large
  uploads; context only).
- Existing tests drive `OpenFileCtx` with mocked streams (`TestWrites.java:131-200`) but none
  touches the water mark.

## B. Verification solution

**B1. Claim under test.** With dumping enabled, after any out-of-order WRITE to one open file is
acknowledged, the NFS gateway holds less than `DUMP_WRITE_WATER_MARK` bytes of that file's
out-of-order data in heap (momentarily at most `mark - 1 + count`), the rest being in the dump
file; changing the constant moves this bound with it. The claim is wrong if buffered out-of-order
data (the counter in the unit tier, live `byte[]` heap in the cluster tier) grows past
`mark + count` for one file, or does not move when the constant is changed.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 8, Maven 3.3+. Copy the tree to local disk first (never build in the shared copy):
  `rsync -a <source>/ $RUN/src/`.
- Build once: `cd $RUN/src && mvn -pl hadoop-hdfs-project/hadoop-hdfs-nfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
- New test file (in the local copy only):
  `hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3/TestDumpWaterMark.java`,
  package `org.apache.hadoop.hdfs.nfs.nfs3` (needed to reach package-private `cleanup()`,
  `getPendingWritesForTest()` and `RpcProgramNfs3.metrics`).
- Run: `mvn -pl hadoop-hdfs-project/hadoop-hdfs-nfs test -Dtest=TestDumpWaterMark` (one method:
  `-Dtest=TestDumpWaterMark#<method>`). Default surefire JVM options are fine (the test holds at most
  about 16 MB of payload).

> **Amendment A1 (2026-11-25, stage-4 audit, before any reading; run on `pc82`).** Environment (`environment.md` §2–3): the local copy is made with
> `copy-source.sh $RUN/src` (`RUN=/mydata/jingsong-s4/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-run1`), not `rsync`;
> no `-am install` (it would reinstall modules into the shared `~/.m2`, which already holds every 3.4.2 module);
> the test runs offline from the copy: `mvn -B -o test -pl hadoop-hdfs-project/hadoop-hdfs-nfs -Dtest=TestDumpWaterMark
> "-Dmaven-surefire-plugin.argLine=-Xmx1g -Ddumpwm.tmp=$RUN/tmp/unit"` (surefire ignores `-DargLine`, case-notes lesson 1).
> No change to B2f/B2g.

**B2b. Knobs.**
- `W` = `DUMP_WRITE_WATER_MARK`, set by reflection before each case and restored after:
  `Field f = OpenFileCtx.class.getDeclaredField("DUMP_WRITE_WATER_MARK"); f.setAccessible(true); f.setLong(null, W);`
  Values: 262,144 (256 KiB), 1,048,576 (1 MiB, stock), 4,194,304 (4 MiB) — below, at and above
  stock, each a multiple of the write size so the arithmetic is exact.
- Dump mode (controls): `dumpFilePath = $tmp/ctx-<case>` (enabled, directory exists, file does
  not); `dumpFilePath = null` (disabled); `dumpFilePath = $tmp/no-such-dir/1` (enabled but file
  creation fails).

**B2c. Workload.**
- Per case: `NfsConfiguration conf = new NfsConfiguration();`
  `RpcProgramNfs3.metrics = Nfs3Metrics.create(conf, "dumpwm");` (once per JVM; needed by
  `OpenFileCtx.java:676`); `Nfs3FileAttributes attr = new Nfs3FileAttributes();` (size 0, so
  `nextOffset` = 0); `HdfsDataOutputStream fos = Mockito.mock(HdfsDataOutputStream.class);`
  `when(fos.getPos()).thenReturn(0L);` `DFSClient dfs = Mockito.mock(DFSClient.class);`
  `OpenFileCtx ctx = new OpenFileCtx(fos, attr, dumpFilePath, dfs, new ShellBasedIdMapping(conf), false, conf);`
  `AsyncDataService ads = new AsyncDataService();`
- N = 250 WRITEs of C = 65,536 bytes (filled with a known pattern), offsets `i*C` for
  `i = 1..250` (never offset 0, so the hole at [0, C) is never filled and every WRITE is
  `ALLOW_DUMP`), each
  `ctx.receivedNewWrite(dfs, new WRITE3Request(new FileHandle(1), i*C, C, WriteStableHow.UNSTABLE, ByteBuffer.wrap(buf_i)), null, xid_i, ads, iug)`
  with a null channel (`Nfs3Utils.writeChannel` ignores null, `Nfs3Utils.java:140-145`). Total
  250 × 65,536 = 16,384,000 bytes, 15.6 × the stock mark, so the mark is crossed 15 times at W =
  1 MiB.
- Run the WRITEs on a single-thread executor and wait for each with `Future.get(10, SECONDS)` so a
  blocked writer is detected, not hung.
- Optional concurrency case (W = 1 MiB): 4 threads, each writing a disjoint quarter of the same
  offsets at once, to observe the concurrent overshoot.

**B2d. Observables and instruments.**
- `M` = counter after each WRITE returns: reflection on field `nonSequentialWriteInMemory`
  (`AtomicLong.get()`).
- Peak of the counter: set `GenericTestUtils.setLogLevel(OpenFileCtx.LOG, org.slf4j.event.Level.DEBUG)`
  and capture with `GenericTestUtils.LogCapturer.captureLogs(OpenFileCtx.LOG)`; parse every
  `"Update nonSequentialWriteInMemory by (-?\d+) new value: (\d+)"` (`OpenFileCtx.java:213-214`);
  peak = max of new values. Also count `"Create dump file"` lines.
- `D` = dump file length, `new File(dumpFilePath).length()` after each WRITE.
- States: from `ctx.getPendingWritesForTest()`, counts and summed `getCount()` of `ALLOW_DUMP` and
  `DUMPED` entries (`WriteCtx.getDataState()`).
- For the failing-dump case: the writer thread's state (`Thread.getState()`, expected WAITING with
  `OpenFileCtx.waitForDump` on the stack) and the log line "Got failure when creating dump stream".
- Not observed directly: the JVM heap itself (the tier measures the counter; the `ALLOW_DUMP`
  sum is the cross-check that the counter matches the `byte[]` actually held).

> **Amendment A2 (2026-11-25, stage-4 audit, before any reading; run on `pc82`).** Instruments added (no change to B2f/B2g): after every WRITE also `HB` = summed
> capacity of the payload `ByteBuffer`s still referenced by `WriteCtx.data` (reflection; the heap the entries actually pin),
> and a second peak reading from an `AtomicLong` subclass swapped into `nonSequentialWriteInMemory` right after
> construction that records the maximum of every `addAndGet` (same semantics; cross-checks the log peak). The captured
> `OpenFileCtx` log of each case is saved to `$RUN/tmp/unit/<case>-openfilectx.log`.
> *Correction to A2 (2026-11-25 10:06 MST, before any reading; runbook defect 1 in the results):* the `AtomicLong`-subclass
> peak instrument does not compile (`AtomicLong.addAndGet` is `final` on JDK 8; the first unit attempt stopped at
> `testCompile`, no test ran). It is removed; the peak comes from the DEBUG log as B2d says. The unit tier restarts.

**B2e. Procedure.**
1. Build (B2a); write `TestDumpWaterMark` with one `@Test` per case below and an `@After` that
   restores W = 1,048,576, calls `ctx.cleanup()` and `ads.shutdown()`.
2. Cases: `wm256k`, `wm1m`, `wm4m` (dump enabled); `dumpDisabled` (null path, W = 1 MiB);
   `dumpDirMissing` (W = 1 MiB; stop at the first WRITE whose `Future.get` times out, record M, D,
   thread state, then interrupt and clean up); optional `concurrent4` (W = 1 MiB).

> **Amendment A3 (2026-11-25, stage-4 audit, before any reading; run on `pc82`).** Runbook defect fixed: "interrupt" cannot free the blocked writer, because
> `waitForDump` catches and ignores `InterruptedException` inside its `while (counter >= mark) wait()` loop
> (`OpenFileCtx.java:294-299`), and after the dump failure nothing else lowers the counter or notifies. The harness frees it
> by setting the counter to 0 and calling `notifyAll()` while holding the context's monitor, then calls `cleanup()`. This
> happens after M, D, the thread state and the stack have been recorded, so B2f/B2g are unchanged.
3. After every WRITE record (i, M, D, ALLOW_DUMP sum, DUMPED count); at the end record the peak
   from the log and the number of "Create dump file" lines; print one CSV per case.
4. After `cleanup()` in the enabled cases check the dump file no longer exists.
5. `mvn -pl hadoop-hdfs-project/hadoop-hdfs-nfs test -Dtest=TestDumpWaterMark`; keep
   `target/surefire-reports/` output.

**B2f. Predictions.** With m = W / C writes per dump round, after WRITE i returns M = (i mod m) × C,
and a dump round empties M to 0 (A3 step 5).

| Case | m | M after every WRITE | Peak (log) | Final M (i = 250) | Final D | Dump rounds |
|---|---|---|---|---|---|---|
| wm256k | 4 | always < 262,144 (0…196,608) | 262,144 | 131,072 (250 mod 4 = 2) | 16,252,928 (248 × C) | 62 |
| wm1m | 16 | always < 1,048,576 (0…983,040) | 1,048,576 | 655,360 (250 mod 16 = 10) | 15,728,640 (240 × C) | 15 |
| wm4m | 64 | always < 4,194,304 (0…4,128,768) | 4,194,304 | 3,801,088 (250 mod 64 = 58) | 12,582,912 (192 × C) | 3 |
| dumpDisabled | — | i × C, grows without bound | 16,384,000 | 16,384,000 | no file | 0 |
| dumpDirMissing | 16 | WRITEs 1-15 return (M ≤ 983,040); WRITE 16 does not return within 10 s | 1,048,576 | stuck at 1,048,576 | no file | 0 (failure logged) |
| concurrent4 (optional) | 16 | < 1,048,576 when each WRITE returns | ≤ 1,048,576 + 3 × C = 1,245,184 | — | — | — |

In every enabled case: M + D = i × C after each WRITE, M equals the `ALLOW_DUMP` sum, the
`DUMPED` count equals D / C, and exactly one "Create dump file" line.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| M < W after every WRITE, peak = W, final M and D as in the table, for all three W | Claim confirmed: the mark bounds heap-held out-of-order data and follows the constant |
| M ≥ W after a WRITE has returned, or peak > W + C − 1 in the single-writer cases | Claim refuted: the check does not hold the writer until the dump finishes |
| M, peak and D the same for 256 KiB, 1 MiB and 4 MiB | Claim refuted: the constant is not what sets the bound (or reflection did not take: check `f.getLong(null)`) |
| M + D ≠ i × C, or M ≠ `ALLOW_DUMP` sum | Accounting does not match the data held; the trace is wrong about the operand |
| Dump rounds leave M > 0 (partial spill) | Dump behaviour differs from A3 step 5; the bound still holds if M < W, but predictions for final M/D are off |
| `dumpDisabled` M grows to 16,384,000 | Expected control: without the dump path the counter is unbounded, so the bound comes from the dump mechanism |
| `dumpDisabled` M stays < 1 MiB | Some other mechanism bounds it; the claim's attribution is wrong |
| `dumpDirMissing` WRITE 16 returns and M keeps growing | Dump failure falls back to unbounded buffering instead of blocking; A3's failure-path trace is wrong (the cap is then bypassed, not enforced) |
| `dumpDirMissing` WRITE 16 blocks, thread WAITING in `waitForDump` | A3 failure-path trace confirmed (throttling becomes a stall) |
| concurrent4 peak > 1,245,184 | More overshoot than one WRITE per waiting thread; the bound is looser than claimed |

**B2h. Controls.**
- `dumpDisabled` shows the same workload moves the counter without bound when the mechanism is
  off (positive control for "usage would grow").
- Three W values: the bound must track the knob, ruling out a bound from somewhere else (for
  example `nfs.wtmax` or the map).
- Reading the field back after `setLong` and checking `peak == W` confirms the knob reached the
  code.
- The `ALLOW_DUMP` sum and the dump file length are independent of the counter, so a counter that
  drifts from the data is caught.
- No hole-filling WRITE is sent and `fos` is a mock, so write-back (which also lowers the counter,
  :1152-1156) cannot explain a drop; any drop is the Dumper's.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux host with root (`sudo`) for portmap and the NFS mount; JDK 8; Python 3.7+;
  `nfs-common` (mount.nfs) installed. Local disk `$RUN` with ≥ 5 GiB free (not shared storage).
- Build from the local copy: `cd $RUN/src && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`;
  unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `$RUN/hadoop`; `HADOOP_HOME=$RUN/hadoop`,
  `HADOOP_CONF_DIR=$RUN/conf` (copy of `$HADOOP_HOME/etc/hadoop`).
- Patched jars for the knob (the constant is not configurable): in **separate** copies of the
  source (`$RUN/src-64m`, `$RUN/src-inf`), edit line 73 of
  `hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java`
  to `private static long DUMP_WRITE_WATER_MARK = 64L * 1024 * 1024;` and `= Long.MAX_VALUE;`
  respectively, then `mvn -pl hadoop-hdfs-project/hadoop-hdfs-nfs -am package -DskipTests -Dmaven.javadoc.skip=true`
  and keep `hadoop-hdfs-project/hadoop-hdfs-nfs/target/hadoop-hdfs-nfs-3.4.2.jar` as
  `$RUN/jars/nfs-64m.jar` / `nfs-inf.jar`; save the stock jar from
  `$HADOOP_HOME/share/hadoop/hdfs/hadoop-hdfs-nfs-3.4.2.jar` as `$RUN/jars/nfs-stock.jar`.
  Check each with `javap -c -p -classpath <jar> org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx | grep -A4 'static {}'`
  (expect 1048576, 67108864, 9223372036854775807).

> **Amendment A4 (2026-11-25, stage-4 audit, before any reading; run on `pc82`).** Environment: no full `-Pdist` build; the cluster uses a copy of the node's built
> distribution (`cp -a /mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2 $RUN/hadoop`, `environment.md` §4).
> The patched jars are built in the one per-case copy `$RUN/src` (edit line 73, `mvn -B -o package -pl
> hadoop-hdfs-project/hadoop-hdfs-nfs -Dmaven.test.skip=true`, keep the jar, `git checkout` the file; nothing is installed into
> `~/.m2`), instead of separate source copies. The jar check is `javap -c -p -constants ... | grep -B1
> 'putstatic.*DUMP_WRITE_WATER_MARK'`: the first constant in `static {}` is the logger's class literal, so `grep -A4 'static {}'`
> does not show the mark. Daemons start with `hdfs --daemon start …` (ssh to localhost does not work on these nodes).
> No change to B3f/B3g.
- Daemons: NameNode + DataNode (pseudo-distributed), Hadoop portmap (root), NFS gateway (`nfs3`,
  as the HDFS user `$U`). No YARN.
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=$RUN/tmp`,
  `hadoop.proxyuser.$U.hosts=*`, `hadoop.proxyuser.$U.groups=*`.
- `hdfs-site.xml`: `dfs.replication=1`, `dfs.namenode.name.dir=$RUN/nn`,
  `dfs.datanode.data.dir=$RUN/dn`, `nfs.dump.dir=$RUN/dump`, `nfs.exports.allowed.hosts=localhost rw`
  (or `* rw`), `nfs.stream.timeout=60000`, `nfs.wtmax=1048576` (default).
- `hadoop-env.sh`: `export HADOOP_LOG_DIR=$RUN/logs`, `export HADOOP_PID_DIR=$RUN/pids`,
  `export HDFS_NFS3_OPTS="-Xmx512m -Xms512m"` (arms A, B), `-Xmx384m -Xms384m` (arms A′, C).
- `log4j.properties` (in `$HADOOP_CONF_DIR`): add
  `log4j.logger.org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx=DEBUG` (gives the counter values,
  `OpenFileCtx.java:213-214`, and the "Create dump file" line).
- Mount point `/mnt/hdfs-nfs-$U` on local disk.

**B3b. Knobs.**
- W via the jar in `$HADOOP_HOME/share/hadoop/hdfs/`: stock 1 MiB, patched 64 MiB, patched
  `Long.MAX_VALUE` (never dumps: the effective "no cap"). A jar change needs a gateway restart
  (`hdfs --daemon stop nfs3`, swap, `hdfs --daemon start nfs3`); NameNode/DataNode keep running
  (the jar is only on the gateway's path at runtime; if replacing it under the running NN/DN is a
  concern, stop them too).
- Gateway heap (`HDFS_NFS3_OPTS -Xmx`), fixed per arm as above.
- Optional arm D: stock jar with `nfs.file.dump=false` in `hdfs-site.xml` (restart).

**B3c. Workload.** Out-of-order writes from the Linux kernel NFS client, made deterministic with
O_DIRECT (no page-cache reordering; each `pwrite` is sent as its own WRITE and waits for the reply).
Script `$RUN/bin/ooo_write.py` (keep scripts outside the data directories):
```python
import os, sys, mmap, time
path, C, N, hold = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
buf = mmap.mmap(-1, C); buf.write(os.urandom(C))           # page-aligned buffer
fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_DIRECT, 0o644)
t0 = time.time()
for i in range(N, 0, -1):                                 # offsets N*C down to C: all out of order
    assert os.pwrite(fd, buf, i * C) == C
print("HOLD after %d writes, %.1fs" % (N, time.time() - t0), flush=True)
time.sleep(hold)                                          # measure here; hole [0,C) still open
assert os.pwrite(fd, buf, 0) == C                         # fill the hole: write-back starts
os.close(fd)
print("DONE", flush=True)
```
- C = 65,536 bytes (one WRITE per `pwrite` with `wsize=1048576`).
- Arms A and B: N = 1,500 (98,304,000 bytes = 93.75 MiB out of order), hold 120 s.
  - A (W = 1 MiB, m = 16): 1,500 = 93 × 16 + 12 → 12 × C = 786,432 bytes in heap, 1,488 × C =
    97,517,568 bytes dumped at the hold.
  - B (W = 64 MiB, m = 1,024): 1,500 = 1 × 1,024 + 476 → 476 × C = 31,195,136 bytes (29.75 MiB)
    in heap, 1,024 × C = 67,108,864 bytes dumped.
- Arms A′ and C (heap governance): N = 8,192 (536,870,912 bytes = 512 MiB out of order), gateway
  `-Xmx384m`, hold 60 s. A′ stock jar; C `Long.MAX_VALUE` jar. 512 MiB of buffered `byte[]` cannot
  fit in a 384 MiB heap.

> **Amendment A5 (2026-11-25, stage-4 audit, before any reading; run on `pc82`).** Runbook defect fixed: **hold 40 s in every arm** (A, B, A′, C; D is stopped by its
> time limit). B3a sets `nfs.stream.timeout=60000`, and the stream monitor (scan every 5 s) closes a context whose last access is
> older than the timeout (`OpenFileCtx.java:190-192` `checkStreamTimeout`, `:939-956` `streamCleanup`;
> `OpenFileCtxCache.java:148-183` `scan`); `cleanup()` then fails every pending write with `NFS3ERR_IO` and deletes the dump
> file (`OpenFileCtx.java:1218-1273`). A 120 s (or 60 s) idle hold would therefore destroy the state being measured and make
> the hole-filling WRITE and the `(N+1) × C` length meaningless. 40 s < 60 s keeps the context open; the B3f values do not
> depend on the hold length. **Stop conditions** (missing in the runbook): the client runs under `timeout -s KILL` of 900 s
> (A, B), 1500 s (A′), 600 s (C) and 120 s (D); in C, a client that never prints `HOLD` within its limit is recorded as "WRITEs
> fail or time out", and the `[B` histogram is taken at the end if the gateway is still alive.
- Optional arm D: stock jar, `nfs.file.dump=false`, N = 64, soft mount with `timeo=100,retrans=2`.
- Duration: each arm is seconds to minutes of writing (one round trip per 64 KiB) plus the hold.

**B3d. Observables and instruments.**
- Live heap held in `byte[]`: `jcmd $PID GC.class_histogram | awk '$4=="[B"{print $3}'` (forces a
  full GC, live objects only), where `PID=$(jps | awk '/Nfs3/{print $1}')`. Baseline `H0` after the
  mount and before writing; `H1` at the hold. Also `jcmd $PID GC.heap_info` at the same moments.
- Continuous heap: `jstat -gc $PID 1000 > $RUN/out/jstat-<arm>.txt` (old-gen used `OU`) during the
  run (arms A′, C).
- Counter (operand) in the real daemon: from `$HADOOP_LOG_DIR/hadoop-$U-nfs3-*.log`, the max of
  `new value: (\d+)` on lines with a positive `by`, the value at the hold (last line before the
  `HOLD` time), and the count of "Create dump file" lines.
- Disk: `du -sb $RUN/dump` and `ls -l $RUN/dump` at the hold, after `DONE`, and after
  `nfs.stream.timeout` + 10 s.
- HDFS result: `hdfs dfs -stat %b /nfstest/<file>` after `DONE` (expected (N+1) × C) and
  `hdfs dfs -checksum` optional.

> **Amendment A6 (2026-11-25, stage-4 audit, before any reading; run on `pc82`).** Observable clarified (prediction unchanged): while the gateway still holds the
> HDFS output stream open, the NameNode reports the length without the last block under construction
> (`FSDirStatAndListingOp.java:449-451`, `computeFileSizeNotIncludingLastUcBlock`), so the `(N+1) × C` length is read after the
> stream monitor has closed the stream (the "after `nfs.stream.timeout` + 10 s" moment of B3e step 6); the reading right after
> `DONE` is also recorded.
- Client: script output (time to finish N writes; errors).
- OOM: `grep -c OutOfMemoryError $HADOOP_LOG_DIR/*nfs3*.{log,out}`; whether the `Nfs3` process is
  still in `jps`.
- Not observable directly: the exact moment of the momentary peak in heap (only via the log
  counter), and which heap bytes belong to which `WriteCtx` (the `[B` delta is a proxy that also
  includes other buffers; hence the baseline and the 64 MiB arm).

**B3e. Procedure.**
1. Build (B3a); format NN: `hdfs namenode -format -nonInteractive`; `hdfs --daemon start namenode`;
   `hdfs --daemon start datanode`; `hdfs dfs -mkdir /nfstest && hdfs dfs -chmod 777 /nfstest`.
2. Portmap and gateway per `HdfsNfsGateway.md:204-220`: `sudo systemctl stop rpcbind rpcbind.socket`
   (if present; note it to restore later); `sudo -E $HADOOP_HOME/bin/hdfs --daemon start portmap`;
   install the arm's jar; `hdfs --daemon start nfs3`. Check `rpcinfo -p localhost` lists
   mountd and nfs 3, and `showmount -e localhost` lists `/`.

> **Amendment A7 (2026-11-25, stage-4 audit, before any reading; run on `pc82`).** Environment: `pc82` runs the system `rpcbind` (active before the run). The
> gateway is first started as `$U` against it; only if `nfs 3 tcp 2049` does not appear in `rpcinfo -p localhost` within 60 s is
> step 2 followed as written (stop `rpcbind.socket rpcbind`, Hadoop `portmap` as root), and `rpcbind` is restarted at cleanup.
> Mount point `/mnt/hdfs-nfs-$U` (created with `sudo`, removed at cleanup). No change to B3f/B3g.
3. `sudo mkdir -p /mnt/hdfs-nfs-$U && sudo mount -t nfs -o vers=3,proto=tcp,nolock,noacl,soft,timeo=600,retrans=2,wsize=1048576 localhost:/ /mnt/hdfs-nfs-$U`.
4. Baseline: `H0`, `du -sb $RUN/dump` (expect 0), start `jstat`.
5. Run `python3 $RUN/bin/ooo_write.py /mnt/hdfs-nfs-$U/nfstest/<arm>-$(date +%s) 65536 <N> <hold>`
   as `$U`. When it prints `HOLD`: take `H1`, `GC.heap_info`, `du -sb $RUN/dump`, and note the time.
6. After `DONE`: `du -sb $RUN/dump`, `hdfs dfs -stat %b`; wait `nfs.stream.timeout` + 10 s
   (70 s) and `du -sb $RUN/dump` again.
7. Extract the counter lines from the gateway log for the arm (copy the log to `$RUN/out/`).
8. `sudo umount /mnt/hdfs-nfs-$U`; `hdfs --daemon stop nfs3`; swap jar / heap for the next arm;
   repeat steps 2 (nfs3 only)-8. Order: A, B, A′, C, then optional D.
9. Arm D: stock jar, `nfs.file.dump=false`, mount with `timeo=100,retrans=2`; run N = 64 with a
   60 s wall-clock limit (`timeout 120 python3 ...`); record the gateway's working directory
   (`readlink /proc/$PID/cwd`, since the CREATE-path dump file is the relative path
   `null/<fileId>`), the log lines "Create dump file"/"Got failure when creating dump stream", and
   the client's result.
10. Cleanup (B4).

**B3f. Predictions.** (Δ = H1 − H0, the live `byte[]` growth at the hold; allow a few MiB of noise
from other buffers.)

| Arm | W | Counter at hold (log) | Log peak | Δ live `byte[]` | Dump dir at hold | Other |
|---|---|---|---|---|---|---|
| A | 1 MiB | 786,432 | 1,048,576 | ≈ 0.75 MiB (well under 4 MiB) | 97,517,568 B (one file) | 93 dump rounds; WRITEs all succeed |
| B | 64 MiB | 31,195,136 | 67,108,864 | ≈ 29.75 MiB (B − A ≈ 29 MiB) | 67,108,864 B | 1 dump round |
| A′ | 1 MiB, -Xmx384m | 0 (8,192 mod 16 = 0) | 1,048,576 | ≈ 0 | 536,870,912 B | no OOM; `OU` flat; file in HDFS = 8,193 × C |
| C | ∞, -Xmx384m | grows by C per WRITE | until failure | grows ≈ 64 KiB per WRITE toward the heap limit | 0 B (no dump file) | `OutOfMemoryError` in the gateway log, or GC thrash, before about 6,000 WRITEs (≈ 384 MiB / 64 KiB); client WRITEs fail or time out |
| D (optional) | 1 MiB, `nfs.file.dump=false` | stuck at 1,048,576 | 1,048,576 | ≈ 1 MiB | none (creation fails unless `<cwd>/null/` exists) | the 16th `pwrite` does not complete (soft-mount timeout / EIO); "Got failure when creating dump stream" logged |

In A, B and A′, after `DONE` the dump file stays until the stream is cleaned up, and is gone
after `nfs.stream.timeout` + scan interval (≤ 65 s); the HDFS file length is (N+1) × C.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| A: log peak = 1,048,576, counter at hold 786,432, Δ ≈ 0.75 MiB, dump ≈ 97.5 MB; B: peak 67,108,864, Δ ≈ 29.75 MiB | Claim confirmed in the real daemon: the constant bounds heap-held out-of-order data and moves it |
| A′ survives with flat old gen while C runs out of heap on the same workload | Confirms the constant is what keeps actual gateway heap from following the out-of-order volume |
| A: Δ well above ~4 MiB, or log counter > 1,048,576 + 65,536 for a single client | Claim refuted: buffered data exceeds the mark |
| A and B give the same Δ and counter | Claim refuted (or jar swap failed: check `javap` and the log peak) |
| C does not grow and does not OOM | Data is not held in heap as traced, or the O_DIRECT writes did not arrive out of order (check the log: entries should be `ALLOW_DUMP`, positive "by" counts); claim not confirmed |
| Log shows no positive "Update nonSequentialWriteInMemory" lines | The workload did not produce out-of-order WRITEs (kernel behaviour); result inconclusive, change the workload (B4 alternative) |
| Dump dir 0 in A/A′ | Dumping did not happen; the cap is not enforced in this setup |
| D: writes keep succeeding and the counter grows past 1 MiB | `nfs.file.dump=false` does disable the cap (contradicts A3's reading of the path); D: the 16th write hangs → A3's failure-path trace confirmed |

**B3h. Controls.**
- Arm C is the positive control: same workload, cap removed, heap is expected to follow the
  out-of-order volume.
- Arm B shows the measured bound moves with the constant, so it is not set by heap size,
  `nfs.wtmax` or the client.
- The log counter (operand) and the `byte[]` heap delta are measured independently; the dump-dir
  size gives a third, disk-side check (counter + dump = N × C at the hold).
- Baseline `H0` after mounting and before writing removes the gateway's idle heap; the full GC in
  `GC.class_histogram` removes garbage.
- The same host, mount options and script for every arm; only the jar (and heap in A′/C) changes.
- `javap` check of each jar, and the log peak, confirm which W the daemon ran with.

**B4. Risks and cleanup.**
- Disk: up to ~512 MiB in `$RUN/dump` (A′) and ~512 MiB in HDFS under `$RUN/dn`; the dump dir is on
  `$RUN`, never the default `/tmp/.hdfs-nfs`. Dump-dir exhaustion stalls writers (A3), so check
  free space first.
- Ports: portmap 111, nfs 2049, mountd 4242, NFS HTTP 50079, NN 9000/9870, DN 9864-9867. Stopping
  the system `rpcbind` affects other NFS users on the host; restore it afterwards
  (`sudo systemctl start rpcbind.socket rpcbind`).
- Hangs: arm D (and C near OOM) can leave an NFS RPC blocked; the `soft` mount with timeouts keeps
  client processes killable. If a mount is stuck: `sudo umount -f -l /mnt/hdfs-nfs-$U`.
- Memory: gateway heap fixed at 384-512 MiB; NN/DN default heaps; well within a normal host.
- Cleanup: `sudo umount /mnt/hdfs-nfs-$U`; `hdfs --daemon stop nfs3`;
  `sudo -E $HADOOP_HOME/bin/hdfs --daemon stop portmap`; `hdfs --daemon stop datanode`;
  `hdfs --daemon stop namenode`; restore system rpcbind; `jps` (and `sudo jps`) shows no `Nfs3`,
  `Portmap`, `NameNode`, `DataNode`; `rm -rf $RUN/dump $RUN/nn $RUN/dn $RUN/tmp` after copying
  logs to `$RUN/out/`. Unit tier: the test's `@After` cleans the dump files; delete `$tmp`.
- If the kernel client does not deliver the O_DIRECT writes as separate out-of-order WRITEs
  (B3g row "no positive Update lines"), the alternative workload is a small Java client in the
  test classpath that sends WRITE3 RPCs in reverse order over TCP with AUTH_SYS credentials,
  modelled on `hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/TestOutOfOrderWrite.java`
  (which itself uses AUTH_NONE and the CREATE procedure number for its WRITE calls, :76-87, so it
  needs fixing before use).

## C. Sources read

hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java
hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/WriteCtx.java
hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/WriteManager.java
hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/RpcProgramNfs3.java
hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtxCache.java
hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/AsyncDataService.java
hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/Nfs3Utils.java
hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/Nfs3Metrics.java
hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/Nfs3.java
hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/conf/NfsConfigKeys.java
hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/conf/NfsConfiguration.java (grep)
hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3/TestWrites.java
hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/TestOutOfOrderWrite.java
hadoop-hdfs-project/hadoop-hdfs-nfs/pom.xml (grep)
hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml (nfs.dump.dir)
hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/HdfsNfsGateway.md
hadoop-hdfs-project/hadoop-hdfs/src/main/bin/hdfs (nfs3, portmap subcommands)
hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/nfs3/request/WRITE3Request.java
hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/nfs3/Nfs3FileAttributes.java
hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/nfs3/Nfs3Base.java
hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/oncrpc/SimpleTcpServer.java (grep)
hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/test/GenericTestUtils.java (setLogLevel, LogCapturer)
https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/HdfsNfsGateway.html (same content as the in-tree HdfsNfsGateway.md; cited, not fetched)

## D. Stage-4 feedback

**2026-11-25 — run 1 on `pc82` (results: `results/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK--autonomous.md`,
drafted at `~/writeup-hadoop/out/o14/results.md`; not committed).** Unit tier **Confirmed** (B2g row 1; both controls as
predicted), cluster tier **Confirmed** (B3g rows 1 and 2; arm D's 16th WRITE hangs) — effect **caps**; outcome class **true
positive**. Frozen version sha256 `cf7d8ac5…ba25aa` (amendments A1–A7 + A2 correction, all before any reading; B2f/B2g/B3f/B3g
unchanged).

- Unit: counters, dump lengths and `ALLOW_DUMP`/`DUMPED` accounting equal B2f on all 750 rows of the three W values (0
  mismatches); peaks 262,144 / 1,048,576 / 4,194,304; `dumpDisabled` grows to 16,384,000; `dumpDirMissing` write 16 is held in
  `waitForDump` (`OpenFileCtx.java:296`) after "Got failure when creating dump stream"; `concurrent4` peak exactly W + 3·C.
- Cluster: A counter at hold 786,432, 93 rounds, dump 97,517,568 B; B 31,195,136, 1 round, 67,108,864 B; live `[B` B − A =
  30,400,200 B (predicted 30,408,704); A′ (384 MiB heap) 512 rounds, 536,870,912 B spilled, flat old gen, no OOM; C
  (`Long.MAX_VALUE`) `OutOfMemoryError` after 4,341 WRITEs (284,491,776 B counted), client `EIO`; D (`nfs.file.dump=false`)
  "Create dump file: null/16391" fails and the 16th WRITE never returns.
- Runbook defects (fixed by A3, A5): the `dumpDirMissing` writer cannot be interrupted; the 120 s / 60 s holds exceed
  `nfs.stream.timeout=60000`, which would close the context and fail the pending writes. The single-point `[B` deltas of B3f
  were 3.2–3.4 MiB low in A and B (a gateway-start baseline offset); the B − A difference is the robust reading — stage 3 may
  prefer stating B3g row 1 in terms of B − A and a tolerance.
