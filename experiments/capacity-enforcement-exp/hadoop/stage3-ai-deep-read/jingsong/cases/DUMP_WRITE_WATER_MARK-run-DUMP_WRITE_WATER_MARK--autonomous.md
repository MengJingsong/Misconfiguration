# DUMP_WRITE_WATER_MARK — verification solution  <!-- file: cases/DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`OpenFileCtx.java:379`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java#L379): `if (nonSequentialWriteInMemory.get() >= DUMP_WRITE_WATER_MARK)` in `OpenFileCtx.Dumper.run()`. The paired admission check is in `OpenFileCtx.waitForDump()` (`OpenFileCtx.java:278`, `:284`, `:294`). |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive`. The constant is a per-open-file high-water mark on the NFS gateway heap that holds out-of-order WRITE data. When the count reaches it, the Dumper spills that data to a local file (`nfs.dump.dir`). The writing RPC thread is held until the in-memory count falls below the mark again. So heap held for out-of-order data per file stays at or below 1 MiB plus one request. Limits on that: it is per file, not per gateway. The cap is lost when dumping is disabled or fails. It moves usage to local disk, which has no cap of its own. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `DUMP_WRITE_WATER_MARK`.
- **Kind:** hard-coded constant (a `private static long`, not `final`), with no configuration key, no setter and no system property.
- **Declaration:** [`OpenFileCtx.java:73`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java#L73) `private static long DUMP_WRITE_WATER_MARK = 1024 * 1024;`, with the comment "Pending writes water mark for dump, 1MB" (`OpenFileCtx.java:72`). It has no `*-default.xml` entry. The `nfs.dump.dir` description mentions it only in prose: "dumped after they are accumulated to exceed certain threshold (e.g., 1MB) in memory" (`hadoop-hdfs/src/main/resources/hdfs-default.xml:2281-2289`; same wording in `HdfsNfsGateway.md:121-131`).
- **Unit:** bytes. **Default:** 1,048,576.
- **How to change it:** at runtime only by reflection (it is not `final`, so `Field.setLong` works on JDK 8/11); otherwise by editing the source and rebuilding.
- **Reader:** the HDFS NFSv3 gateway process (`hdfs nfs3`, class `org.apache.hadoop.hdfs.nfs.nfs3.Nfs3`). It reads the static on every comparison, so a reflective change applies at once.
- **Related keys that switch the mechanism on or off (not the limit itself):**
  - `nfs.file.dump` (`NfsConfigKeys.DFS_NFS_FILE_DUMP_KEY`, default `true`, `NfsConfigKeys.java:29-30`).
  - `nfs.dump.dir` (`DFS_NFS_FILE_DUMP_DIR_KEY`, default `/tmp/.hdfs-nfs`, `NfsConfigKeys.java:31-32`, `hdfs-default.xml:2281-2282`).
  - Both go in `hdfs-site.xml` and need a gateway restart (`HdfsNfsGateway.md:121-131`).
  - Request size is bounded by `nfs.wtmax` (default 1 MiB, `NfsConfigKeys.java:36-37`).

**A2. What it caps.** It caps the NFS gateway's **JVM heap** held by buffered out-of-order (non-sequential) WRITE payloads, **per open file** (per `OpenFileCtx`).
- **Compared quantity:** `nonSequentialWriteInMemory` (`OpenFileCtx.java:178-179`), an `AtomicLong` of bytes in `WriteCtx` objects whose state is `ALLOW_DUMP`.
  - It goes up by `count` when a write arrives at an offset beyond the current `nextOffset` (`OpenFileCtx.java:562-573`).
  - It goes down when such a write is dumped to disk (`OpenFileCtx.java:358-361`) or written back to HDFS (`OpenFileCtx.java:1151-1157`).
- **Where the data moves:** to local disk in `nfs.dump.dir/<fileId>`. The size of that file is not capped by anything.

**A3. Mechanism.**
1. **Arrival.** An NFS WRITE reaches `RpcProgramNfs3.write` → `WriteManager.handleWrite` → `OpenFileCtx.receivedNewWrite` (`OpenFileCtx.java:426`) → `receivedNewWriteInternal` (`:642`). `addWritesToCache` (`:515-587`, synchronized) builds a `WriteCtx` holding the request's `ByteBuffer`.
   - If `offset == nextOffset` the write is `NO_DUMP` and is not counted.
   - Otherwise it is `ALLOW_DUMP` and the counter is increased by `count` (`:562-573`).
2. **Admission check, writer side.** If the write is not sequential (`checkAndStartWrite` returns false, `:623-640`), the RPC thread calls `waitForDump()` (`:659`).
   - With dumping disabled (`enabledDump == false`, i.e. a `null` dump path) it returns immediately (`:273-276`).
   - If the counter is `< DUMP_WRITE_WATER_MARK` it returns (`:278-280`).
   - Otherwise, under the context's monitor, it starts the `Dumper` daemon thread on first use or `notifyAll()`s it (`:284-291`). It then **waits while the counter is `>= DUMP_WRITE_WATER_MARK`** (`:294-299`).
   - The reply to the client (`:661-681`) is therefore delayed until the data is on disk. This is back-pressure: the handler runs on the Netty worker for that connection (`SimpleTcpServer.java:67-68`), so that connection stalls during a dump.
3. **The check at the entry pointer, dumper side.** `Dumper.run()` loops while `activeState && enabledDump` (`:377`). [`OpenFileCtx.java:379`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java#L379) `if (nonSequentialWriteInMemory.get() >= DUMP_WRITE_WATER_MARK) { dump(); }`.
   - **True:** `dump()` (`:306-373`) creates the dump file on first use (`:308-331`, `createNewFile` must succeed) and opens a read-only `RandomAccessFile` (`:334-343`). It then iterates over **all** pending writes (largest offset first, comparator `:237-238`) while the counter is `> 0` (`:348-350`).
     - Each `ALLOW_DUMP` write is appended to the file. `WriteCtx.dumpData` (`WriteCtx.java:150-183`) writes `count` bytes, sets `data = null` (frees the heap buffer) and changes state to `DUMPED` (`WriteCtx.java:173-178`).
     - The counter is reduced by the dumped size (`OpenFileCtx.java:358-361`).
     - So one dump round drains the counter to about 0, not just below the mark.
   - **False, or after the dump:** under the monitor, if the counter is `< DUMP_WRITE_WATER_MARK` it `notifyAll()`s the waiting writers and `wait()`s for the next request (`:382-392`).
4. **Write-back.** When the hole at `nextOffset` is filled, the write-back task takes entries in order (`offerNextToWrite`, `:965`). For a `DUMPED` entry, `WriteCtx.getData()` reads the bytes back from the dump file into a new `byte[count]` (`WriteCtx.java:214-242`), one entry at a time.
   - The dump file is not truncated during write-back. It is closed and deleted only in `cleanup()` (`OpenFileCtx.java:1262-1274`), when the stream is closed (stream timeout, `nfs.stream.timeout`, default 10 min, `NfsConfigKeys.java:44-46`; or eviction).
5. **Bound that follows.** Single writer per file: on return from `waitForDump` the counter is `< M`, so in-heap `ALLOW_DUMP` bytes are at most `M − 1 + count`, where `count ≤ nfs.wtmax`.
   - With `count` dividing `M`, the counter peaks at exactly `M` and is `≤ M − count` after each reply.
   - Concurrent writes to the same file (several connections or worker threads) can each add one request before blocking, so overshoot is up to one request per concurrent writer.

**Bypasses and overshoots:**
- **Dumping disabled.** `enabledDump = dumpFilePath != null` (`OpenFileCtx.java:251`); if false, `waitForDump` returns at once (`:273-276`) and the counter is unbounded.
  - In the daemon, `nfs.file.dump=false` only sets `RpcProgramNfs3.writeDumpDir = null` (`RpcProgramNfs3.java:202-215`). CREATE still passes the **string** `writeDumpDir + "/" + fileId`, i.e. `"null/<fileId>"` (`RpcProgramNfs3.java:1013-1015`).
  - The re-open path in `WriteManager.handleWrite` reads `nfs.dump.dir` directly and ignores `nfs.file.dump` (`WriteManager.java:182-185`).
  - So in the daemon `enabledDump` is effectively always true. The relative path, or a directory that was never created because `clearDirectory` was skipped, leads to the dump-failure case below.
- **Dump failure.** If `createNewFile`/`FileOutputStream`/`RandomAccessFile`/`dumpData` throws `IOException`, `dump()` sets `enabledDump = false` and returns (`:318-330`, `:337-341`, `:362-367`).
  - `run()` then sees the counter still `>= M`, does **not** `notifyAll()` (`:383`), and exits its loop (`:377`).
  - Reading the code, the writer already waiting at `:294-299` is never woken. Its `wait()` has no timeout and `InterruptedException` is ignored, and `cleanup()` does not notify (`:1218-1282`). That RPC thread, and so that connection, appears stuck.
  - Later writes from other threads pass `waitForDump` at `:273` and grow the counter without bound.
  - This is predicted from the source, not observed; the unit tier tests it.
- **A `Throwable` in the dumper** sets `activeState = false` after `notifyAll()` (`:396-404`). Later writes get `NFS3ERR_IO` (`:430-438`).

**A4. Other consumers.**
- **Heap held per gateway:** the cap is per `OpenFileCtx`. Up to `nfs.max.open.files` (default 256, `NfsConfigKeys.java:41-42`; `OpenFileCtxCache.java:53-54`) contexts can each hold up to about 1 MiB plus a request, i.e. at least about 256 MiB per gateway.
- **Heap outside the counter:**
  - Sequential (`NO_DUMP`) writes waiting for write-back are held in `pendingWrites` and never counted or dumped (`OpenFileCtx.java:562-563`).
  - Re-loaded dumped data during write-back (`WriteCtx.java:229-242`).
  - Netty receive buffers.
  - DFSClient packet queues for the HDFS output stream.
  - Read buffers (`nfs.rtmax`).
  - The `WriteCtx` objects themselves, which stay in `pendingWrites` after their data is dumped.
- **Disk:** the dump directory holds all dumped out-of-order bytes of every open stream until the stream is cleaned up, with no limit. The docs only advise sizing the directory (`HdfsNfsGateway.md:121-131`).
- **Accounting:** a repeated request that races past `checkRepeatedWriteRequest` is counted (`:570-573`) but not inserted (`:575-584`). Its bytes are then never subtracted. This is a possible counter inflation, by reading only.

**A5. Evidence beyond the source.**
- `hdfs-default.xml:2281-2289` and `HdfsNfsGateway.md:121-131` (the 1MB threshold and dump-dir sizing advice).
- `HdfsNfsGateway.md:202-280` (portmap/nfs3 start and mount commands).
- HDFS-7259 is cited in `OpenFileCtx.java:82-97` for commit semantics. It is related but not about the threshold: <https://issues.apache.org/jira/browse/HDFS-7259>.
- Tests: `TestWrites.java` builds `OpenFileCtx` with mocks (`:135-160`). `TestOutOfOrderWrite.java` sends out-of-order RPCs; it is a manual `main()`, not an assertion test. No test exercises the dump threshold.

## B. Verification solution

**B1. Claim under test.** For one open file on the NFS gateway, heap bytes held by out-of-order WRITE data (`nonSequentialWriteInMemory`, and the `byte[]` behind it) never exceed `DUMP_WRITE_WATER_MARK` plus one request. Once the mark is reached, the excess is moved to `nfs.dump.dir/<fileId>`, so heap use stays flat while the dump file grows with the workload. If the mark is raised above the workload, or dumping is off, held heap grows with the workload.

### B2. Unit tier

**B2a. Environment and build.**
- **JDK and Maven:** JDK 8, Maven ≥ 3.3.
- **Source copy:** copy the tree to local disk first: `rsync -a ~/hadoop-3.4.2/ $S4/src/`, where `$S4` is a local directory with ≥ 3 GiB free, e.g. `/mydata/<user>-s4/dumpwm`.
- **Build:** `cd $S4/src && mvn -pl hadoop-hdfs-project/hadoop-hdfs-nfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
- **Test:**
  - New file `$S4/src/hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3/TestDumpWaterMark.java`, code below. It must be in package `org.apache.hadoop.hdfs.nfs.nfs3` because `OpenFileCtx` and `WriteCtx` are package-private.
  - Run: `mvn -pl hadoop-hdfs-project/hadoop-hdfs-nfs test -Dtest=TestDumpWaterMark -Ddumpwm.dir=$S4/unit-dump`.
- **JVM options:** surefire already runs with `-Xmx2048m` (`hadoop-project/pom.xml:187`), enough for the 64 MiB no-cap runs.

```java
package org.apache.hadoop.hdfs.nfs.nfs3;

import static org.junit.Assert.assertTrue;
import java.io.File;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import org.apache.hadoop.fs.FileUtil;
import org.apache.hadoop.hdfs.DFSClient;
import org.apache.hadoop.hdfs.client.HdfsDataOutputStream;
import org.apache.hadoop.hdfs.nfs.conf.NfsConfiguration;
import org.apache.hadoop.nfs.nfs3.FileHandle;
import org.apache.hadoop.nfs.nfs3.Nfs3Constant.WriteStableHow;
import org.apache.hadoop.nfs.nfs3.Nfs3FileAttributes;
import org.apache.hadoop.nfs.nfs3.request.WRITE3Request;
import org.apache.hadoop.security.ShellBasedIdMapping;
import org.junit.Test;
import org.mockito.Mockito;

public class TestDumpWaterMark {
  static final int CHUNK = 64 * 1024;
  static final int NCHUNK = 1024;               // 64 MiB of out-of-order data
  static final long MIB = 1024L * 1024;

  static long heapAfterGc() throws InterruptedException {
    for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(200); }
    return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
  }

  /** dump=false -> null dump path; badDir=true -> dump path whose parent does not exist. */
  static void run(long m, boolean dump, boolean badDir, File dir) throws Exception {
    Field wm = OpenFileCtx.class.getDeclaredField("DUMP_WRITE_WATER_MARK");
    wm.setAccessible(true);
    long saved = wm.getLong(null);
    wm.setLong(null, m);
    NfsConfiguration conf = new NfsConfiguration();
    ShellBasedIdMapping iug = new ShellBasedIdMapping(conf);
    DFSClient dfs = Mockito.mock(DFSClient.class);
    HdfsDataOutputStream fos = Mockito.mock(HdfsDataOutputStream.class);
    Mockito.when(fos.getPos()).thenReturn(0L);
    File dumpFile = badDir ? new File(dir, "no-such-dir/f") : new File(dir, "dump-" + m + "-" + dump);
    OpenFileCtx ctx = new OpenFileCtx(fos, new Nfs3FileAttributes(),
        dump ? dumpFile.getAbsolutePath() : null, dfs, iug, false, conf);
    Field cf = OpenFileCtx.class.getDeclaredField("nonSequentialWriteInMemory");
    cf.setAccessible(true);
    AtomicLong counter = (AtomicLong) cf.get(ctx);
    AtomicLong maxSampled = new AtomicLong();
    AtomicBoolean stop = new AtomicBoolean();
    Thread sampler = new Thread(() -> {
      while (!stop.get()) { long v = counter.get(); if (v > maxSampled.get()) maxSampled.set(v); }
    });
    sampler.setDaemon(true);
    sampler.start();
    AsyncDataService ads = new AsyncDataService();
    ExecutorService ex = Executors.newCachedThreadPool(r -> {
      Thread t = new Thread(r); t.setDaemon(true); return t; });
    FileHandle fh = new FileHandle(16386L);
    long heap0 = heapAfterGc();
    long maxAfter = 0, maxInHeap = 0;
    int rounds = 0, stuck = 0;
    for (int k = NCHUNK; k >= 1; k--) {            // offsets 64 MiB .. 64 KiB; offset 0 never sent
      byte[] b = new byte[CHUNK];
      Arrays.fill(b, (byte) k);
      WRITE3Request req = new WRITE3Request(fh, (long) k * CHUNK, CHUNK,
          WriteStableHow.UNSTABLE, ByteBuffer.wrap(b));
      int xid = k;
      long before = counter.get();
      Future<?> f = ex.submit(() -> ctx.receivedNewWrite(dfs, req, null, xid, ads, iug));
      try { f.get(10, TimeUnit.SECONDS); } catch (TimeoutException te) { stuck++; }
      long after = counter.get();
      if (after < before + CHUNK) rounds++;        // a dump drained the counter
      maxAfter = Math.max(maxAfter, after);
      long inHeap = 0;
      for (WriteCtx w : ctx.getPendingWritesForTest().values()) {
        if (w.getDataState() != WriteCtx.DataState.DUMPED) inHeap += w.getCount();
      }
      maxInHeap = Math.max(maxInHeap, inHeap);
    }
    long heap1 = heapAfterGc();
    stop.set(true);
    long dumpLen = dumpFile.exists() ? dumpFile.length() : -1;
    System.out.println(String.format("DUMPWM M=%d dump=%b badDir=%b maxAfterReturn=%d maxSampled=%d "
        + "maxInHeap=%d final=%d rounds=%d stuck=%d dumpFileLen=%d heapDelta=%d",
        m, dump, badDir, maxAfter, maxSampled.get(), maxInHeap, counter.get(), rounds, stuck,
        dumpLen, heap1 - heap0));
    ctx.cleanup();
    ads.shutdown();
    ex.shutdownNow();
    wm.setLong(null, saved);
  }

  @Test
  public void sweep() throws Exception {
    if (RpcProgramNfs3.metrics == null) {
      RpcProgramNfs3.metrics = Nfs3Metrics.create(new NfsConfiguration(), "dumpwm");
    }
    File dir = new File(System.getProperty("dumpwm.dir", "target/dumpwm"));
    FileUtil.fullyDelete(dir);
    assertTrue(dir.mkdirs());
    for (long m : new long[] {256 * 1024L, MIB, 4 * MIB, 16 * MIB, 128 * MIB}) {
      run(m, true, false, dir);
    }
    run(MIB, false, false, dir);   // U6: dumping disabled (null path) -> no cap
    run(MIB, true, true, dir);     // U7: dump file cannot be created -> bypass / stuck writer
  }
}
```

**B2b. Knobs.** `DUMP_WRITE_WATER_MARK` (`M`), set by reflection before each `OpenFileCtx` is driven (static, read at every comparison).

| Run | M (bytes) | Why |
|---|---|---|
| U1 | 262,144 | Below the default |
| U2 | 1,048,576 | Default |
| U3 | 4,194,304 | Above the default |
| U4 | 16,777,216 | Above the default |
| U5 | 134,217,728 | Above the 64 MiB workload, so it never binds (control) |
| U6 | 1,048,576, dump path `null` | The mechanism is off (positive control: usage follows the workload) |
| U7 | 1,048,576, dump path with a missing parent | The failure-bypass path in A3 |

All of U1–U4 divide the 64 MiB total and are multiples of the chunk size, so the arithmetic below is exact.

**B2c. Workload.**
- 1,024 WRITE requests of 64 KiB (65,536 B) each, at descending offsets `k·65536` for `k = 1024 … 1`. Offset 0 is never sent, so `nextOffset` stays 0 and every request is `ALLOW_DUMP`.
- Total out-of-order data is 67,108,864 B = 64 MiB, which is 256 × U1, 64 × U2, 16 × U3, 4 × U4 and 0.5 × U5.
- Calls run single-threaded through a helper thread with a 10 s timeout, so a blocked writer (U7) is counted, not hung.
- The mocked `HdfsDataOutputStream` is never written: write-back needs a write at offset 0.

**B2d. Observables and instruments.**
- **The check's operand:** `nonSequentialWriteInMemory`, read via reflection.
  - after every call returns (`maxAfterReturn`);
  - continuously by a spin sampler thread (`maxSampled`, a lower bound on the true peak);
  - its final value.
- **Independent cross-check of heap-held data:** the sum of `getCount()` over `pendingWrites` entries not in state `DUMPED` (`maxInHeap`).
- **Number of dump rounds:** calls after which the counter rose by less than one chunk.
- **Dump file length:** `File.length()` before `cleanup()`.
- **Retained heap growth:** `heapDelta`, heap used after `System.gc()` ×3, end minus start (coarse).
- **Stuck writers:** calls not returning within 10 s.
- **Not observable directly:** the exact instant of each peak (the sampler may miss it); actual `byte[]` retention per object (`heapDelta` is an approximation).

**B2e. Procedure.**
1. Copy the source and build as in B2a.
2. Create `TestDumpWaterMark.java` in the copy.
3. Run `mvn -pl hadoop-hdfs-project/hadoop-hdfs-nfs test -Dtest=TestDumpWaterMark -Ddumpwm.dir=$S4/unit-dump`. Expect roughly 1–2 min: U7 adds one 10 s timeout.
4. Collect the `DUMPWM` lines with `grep DUMPWM hadoop-hdfs-project/hadoop-hdfs-nfs/target/surefire-reports/*TestDumpWaterMark-output.txt`, or from the console.
5. `rm -rf $S4/unit-dump`.

**B2f. Predictions** (stated before any run; `C` = 65,536).

| Run | maxAfterReturn | maxSampled / peak | maxInHeap | final | rounds | stuck | dumpFileLen | heapDelta |
|---|---|---|---|---|---|---|---|---|
| U1 M=256 KiB | 196,608 (= M − C) | ≤ 262,144 | ≤ 262,144 | 0 | 256 | 0 | 67,108,864 | < 8 MiB |
| U2 M=1 MiB | 983,040 | ≤ 1,048,576 | ≤ 1,048,576 | 0 | 64 | 0 | 67,108,864 | < 8 MiB |
| U3 M=4 MiB | 4,128,768 | ≤ 4,194,304 | ≤ 4,194,304 | 0 | 16 | 0 | 67,108,864 | < 12 MiB |
| U4 M=16 MiB | 16,711,680 | ≤ 16,777,216 | ≤ 16,777,216 | 0 | 4 | 0 | 67,108,864 | < 24 MiB |
| U5 M=128 MiB | 67,108,864 | 67,108,864 | 67,108,864 | 67,108,864 | 0 | 0 | −1 (no file) | ≥ 60 MiB |
| U6 null path | 67,108,864 | 67,108,864 | 67,108,864 | 67,108,864 | 0 | 0 | −1 | ≥ 60 MiB |
| U7 bad dir | 67,108,864 | 67,108,864 | 67,108,864 | 67,108,864 | 0 | 1 (the 16th call, k = 1009) | −1 | ≥ 60 MiB |

- In U1–U4 the in-heap level follows `M` in a sawtooth that peaks at `M`, and the dump file takes the whole workload.
- In U5–U7 the in-heap level follows the workload.

**The claim is wrong if any of these is seen:**
- In U1–U4, `maxAfterReturn ≥ M`, `maxSampled` or `maxInHeap > M` (plus a chunk at most, for sampler skew), or `heapDelta` ≥ about 60 MiB.
- `rounds ≠ 64 MiB / M`.
- No dump file in U1–U4.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| U1–U4 counter and in-heap bytes stay ≤ M, rounds = 64 MiB/M, dump file = 64 MiB, heapDelta small | Claim confirmed: the mark caps heap-held out-of-order data and moves the rest to disk |
| U1–U4 maxInHeap or heapDelta tracks the 64 MiB workload instead of M | Claim refuted: the counter is capped but the data is not released (e.g. `data` still referenced) |
| Counter capped but rounds ≠ 64 MiB/M, or dump file shorter than predicted | The mechanism differs from A3 (e.g. partial dumps); re-read `dump()` |
| U5/U6 heap and counter reach 64 MiB while U1–U4 stay flat | Positive control: the instruments see the growth when the cap does not bind |
| U5/U6 do not reach 64 MiB | Control failed (workload or instrument broken); claim not confirmed |
| U7 stuck = 1 and counter → 64 MiB | Dump-failure bypass confirmed: cap lost, one writer blocked indefinitely |
| U7 stuck = 0 and counter stays ≤ M | The A3 failure analysis is wrong (note it in D) |

**B2h. Controls.**
- U5 and U6 run the same workload with the cap out of play. U2 against U5 differs only in `M`, which isolates the constant as the cause.
- `maxInHeap` is computed from `WriteCtx` states, independent of the counter.
- Each run uses a new `OpenFileCtx` and a new dump file, and `M` is restored to 1 MiB afterwards.
- `heapDelta` is coarse. The decision rests on the counter, `maxInHeap` and dump length, and heap is only checked for the gross 64 MiB difference.

### B3. Cluster tier

**B3a. Environment and build.**
- **Host:** one Linux host, pseudo-distributed. **Daemons:** NameNode, DataNode, Hadoop portmap and the NFS3 gateway (`nfs3`, the daemon under test).
- **Kernel NFS client:** mounts the export on the same host.
- **Root:** needs `sudo` for portmap (port 111) and for `mount`/`umount`.
- **Build:** `cd $S4/src && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`, then `cp -a hadoop-dist/target/hadoop-3.4.2 $S4/hadoop`, `export HADOOP_HOME=$S4/hadoop HADOOP_CONF_DIR=$S4/hadoop/etc/hadoop`.
- **Disk:** all data on local disk under `$S4`, ≥ 6 GiB free: HDFS about 1.3 GiB plus dump about 0.8 GiB plus logs.

**`core-site.xml`:**
- `fs.defaultFS = hdfs://localhost:9000`
- `hadoop.tmp.dir = $S4/tmp`
- `hadoop.proxyuser.<runuser>.groups = *`
- `hadoop.proxyuser.<runuser>.hosts = *`

The gateway user must be a proxy user (`HdfsNfsGateway.md:38-60`).

**`hdfs-site.xml`:**
- `dfs.replication = 1`
- `dfs.namenode.name.dir = file://$S4/nn`
- `dfs.datanode.data.dir = file://$S4/dn`
- `nfs.dump.dir = $S4/nfs-dump`
- `nfs.file.dump = true`
- `nfs.stream.timeout = 60000` (so the dump file is deleted soon after the run; minimum 10 s, `NfsConfigKeys.java:46`)
- `nfs.exports.allowed.hosts = * rw` (default, `CommonConfigurationKeys.java:389-390`)

**`hadoop-env.sh`:**
- `export JAVA_HOME=<jdk8>`
- `HADOOP_LOG_DIR=$S4/logs`
- `HADOOP_PID_DIR=$S4/pids`
- `HDFS_NFS3_OPTS="-Xms256m -Xmx256m"` (C1/C3/C4) or `"-Xms512m -Xmx512m"` (C2, C5)
- `HDFS_NAMENODE_OPTS`/`HDFS_DATANODE_OPTS` at `-Xmx1g`

**`log4j.properties`:** append `log4j.logger.org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx=DEBUG`. This logs every counter update (`OpenFileCtx.java:213-214`).

**Ports:**
- Check with `ss -ltnup | grep -E ':(111|2049|4242|9000|9870|9864|9866|9867|50079)\b'`.
- If a kernel nfsd holds 2049, set `nfs.server.port=12049` and `nfs.mountd.port=14242` and use those in the mount options.

**Driver:** `$S4/ooo_write.py`, kept outside the source tree. It writes descending offsets with `O_DIRECT`, so each `pwrite` becomes one WRITE RPC of `--chunk` bytes, in the order issued:

```python
#!/usr/bin/env python3
import os, mmap, time, argparse
p = argparse.ArgumentParser()
p.add_argument('--dir', required=True); p.add_argument('--files', type=int, default=1)
p.add_argument('--chunk', type=int, default=65536); p.add_argument('--chunks', type=int, default=12288)
p.add_argument('--checkpoint-sleep', type=int, default=20); p.add_argument('--pause', type=int, default=60)
a = p.parse_args()
buf = mmap.mmap(-1, a.chunk); buf.write(b'\xab' * a.chunk)          # page-aligned buffer
fds = [os.open(os.path.join(a.dir, 'f%03d' % i), os.O_WRONLY | os.O_CREAT | os.O_DIRECT, 0o644)
       for i in range(a.files)]
marks = {int(a.chunks * q) for q in (0.75, 0.5, 0.25)}
for k in range(a.chunks - 1, 0, -1):                                   # chunk 0 held back
    for fd in fds:
        assert os.pwrite(fd, buf, k * a.chunk) == a.chunk
    if k in marks:
        print(time.strftime('%T'), 'CHECKPOINT k=%d' % k, flush=True); time.sleep(a.checkpoint_sleep)
print(time.strftime('%T'), 'PAUSE all out-of-order chunks sent', flush=True); time.sleep(a.pause)
for fd in fds:
    os.pwrite(fd, buf, 0); os.close(fd)                                # fill the hole -> write-back
print(time.strftime('%T'), 'DONE', flush=True)
```

How the gateway handles these writes:
- Out-of-order writes are answered UNSTABLE (`OpenFileCtx.java:665-681`).
- The client's COMMIT for a range with a hole returns `COMMIT_SPECIAL_SUCCESS` at once with `nfs.large.file.upload=true` (default) (`OpenFileCtx.java:875-891`), so the driver does not block.

**B3b. Knobs.** The constant cannot be set in a stock distribution (A1). The cluster tier varies:
- the workload size relative to the fixed 1 MiB mark (C1 against C3);
- the request size (C4);
- the number of concurrently written files (C2, positive control of the instrument and the per-file scope).

Optional C5 changes the constant in a **separate patched copy** (`OpenFileCtx.java:73` set to `64L * 1024 * 1024`; rebuild only `hadoop-hdfs-nfs` and replace `share/hadoop/hdfs/hadoop-hdfs-nfs-3.4.2.jar` in a copy of the distribution). This is a code change; label its results as such.

All config changes need a gateway restart (`hdfs --daemon stop nfs3; hdfs --daemon start nfs3`, then re-mount).

`nfs.file.dump=false` is **not** used as a control: in the daemon it does not give a null dump path (A3) and is predicted to stall the connection.

| Run | Files | Chunk (B) | Chunks per file (file size) | Gateway Xmx | Mount `wsize` |
|---|---|---|---|---|---|
| C1 | 1 | 65,536 | 12,288 (768 MiB) | 256m | 65536 |
| C2 | 32 | 65,536 | 256 (16 MiB each, 512 MiB total) | 512m | 65536 |
| C3 | 1 | 65,536 | 16 (1 MiB) | 256m | 65536 |
| C4 | 1 | 1,048,576 | 768 (768 MiB) | 256m | 1048576 |
| C5 (optional, patched M = 64 MiB) | 1 | 65,536 | 12,288 | 512m | 65536 |

**B3c. Workload.**
- **C1:** 12,287 out-of-order 64 KiB writes = 805,240,832 B, three times the 256 MiB heap. Without a working cap the gateway could not hold it, and would hit `OutOfMemoryError`.
  - The mark (16 chunks) is reached 767 times (12,287 = 16·767 + 15).
  - Duration: a few minutes plus 3 × 20 s checkpoints and a 60 s pause.
- **C2:** 32 files × 255 out-of-order chunks. Per file 255 = 16·15 + 15, so each file keeps a residual 15 chunks (983,040 B) in heap at the pause. That is 31,457,280 B (30 MiB) across files, which the heap instrument must detect.
- **C3:** 15 out-of-order chunks = 983,040 B < mark, so no dump is expected.
- **C4:** each 1 MiB write alone reaches the mark, so every write triggers a dump round (767 rounds).
- **C5:** the mark is 1,024 chunks, so 11 rounds (11·1,024 = 11,264) and 1,023 chunks (67,043,328 B) held at the pause.

**B3d. Observables and instruments.**
- **Counter (the check's operand, in the real daemon):** the DEBUG lines `Update nonSequentialWriteInMemory by <d> new value: <v>` in `$S4/logs/hadoop-*-nfs3-*.log`.
  - Maximum `v`: `grep -o 'new value: [0-9]*' <log> | awk '{print $3}' | sort -n | tail -1`.
  - Number of times `v` reaches the mark: `grep -c 'new value: 1048576$'`.
  - Dump events: INFO `Create dump file:` and DEBUG `Asking dumper to dump...`.
- **Heap (actual resource):**
  - At each `CHECKPOINT`/`PAUSE` line, and every 5 s, run `jcmd $GWPID GC.class_histogram | awk '$4=="[B"{print $3}'`. This is total live `byte[]` bytes after the full GC the histogram triggers.
  - Also `jstat -gc $GWPID 1000 > $S4/obs/jstat.log` (old-gen used, full-GC count).
  - Find `$GWPID` with `jps | awk '/Nfs3/{print $1}'` or from `$S4/pids/hadoop-*-nfs3.pid`.
- **Disk (where the data goes):** `while sleep 1; do date +%T; ls -l $S4/nfs-dump; du -sb $S4/nfs-dump; done > $S4/obs/dump.log`.
- **End state:**
  - `hdfs dfs -ls /nfstest`: file sizes.
  - `hdfs dfs -checksum` or `cmp` of a read-back against a locally generated file of 0xAB bytes, to show data integrity after reload from the dump file.
  - The dump file is deleted after `nfs.stream.timeout`.
- **Process health:**
  - `grep -c OutOfMemoryError $S4/logs/*nfs3*`;
  - the driver finishes with `DONE`.
- **Not observable directly:**
  - per-file attribution of the DEBUG counter lines (they carry no file id), so C2 uses aggregate heap and per-file dump file sizes;
  - the exact peak between increment and dump.

**B3e. Procedure.**
1. **Build and configure** per B3a. Then run `hdfs namenode -format -nonInteractive` and `start-dfs.sh`. Make the test directory: `hdfs dfs -mkdir /nfstest && hdfs dfs -chmod 777 /nfstest`.
2. **Portmap.** Run `rpcinfo -p localhost`.
   - **(a)** If nothing listens on 111: `sudo -E $HADOOP_HOME/bin/hdfs --daemon start portmap` (`HdfsNfsGateway.md:209-211`).
   - **(b)** If a system rpcbind runs, first try starting nfs3 as the run user (step 3). If its log shows `Registration failure`, there are two options:
     - On a dedicated host only: `sudo systemctl stop rpcbind.socket rpcbind`, then (a). Restore it in cleanup.
     - On a shared host: keep rpcbind and start the gateway without registration: `java -cp "$($HADOOP_HOME/bin/hadoop classpath)" $HDFS_NFS3_OPTS -Dhadoop.log.dir=$S4/logs <launcher>`, where `<launcher>` is a one-line class calling `new org.apache.hadoop.hdfs.nfs.nfs3.Nfs3(new NfsConfiguration()).startServiceInternal(false)`. Then mount with explicit `port=2049,mountport=4242,mountproto=tcp`, which skips the portmapper.
3. **Start the gateway:** `hdfs --daemon start nfs3`. Check `rpcinfo -p localhost` lists 100003 and 100005, and `ls $S4/nfs-dump` exists and is empty (`RpcProgramNfs3.java:232-245`).
4. **Mount:** `sudo mkdir -p $S4/mnt && sudo mount -t nfs -o vers=3,proto=tcp,nolock,noacl,sync,soft,timeo=600,retrans=2,wsize=<per run> localhost:/ $S4/mnt` (based on `HdfsNfsGateway.md:280`, plus `soft` so a stall cannot hang the host).
5. **Start the samplers** (jcmd loop, jstat, dump.log) in the background into `$S4/obs/<run>/`.
6. **Run the driver as the run user**, e.g. C1: `python3 $S4/ooo_write.py --dir $S4/mnt/nfstest/c1 --chunk 65536 --chunks 12288` (after `mkdir $S4/mnt/nfstest/c1`). At each `CHECKPOINT` and at `PAUSE`, run the `jcmd` histogram once by hand as well.
7. **After `DONE`:** wait 90 s (stream timeout), record `ls -l $S4/nfs-dump`, `hdfs dfs -ls -R /nfstest`, the max counter, the mark-hit count and OOM count from the log. Stop the samplers.
8. **Repeat for C2–C4** (and optionally C5):
   - change `wsize` (re-mount) or `HDFS_NFS3_OPTS` (restart nfs3, re-mount) as the table says;
   - delete earlier test files with `hdfs dfs -rm -r -skipTrash /nfstest/c*` between runs to save disk;
   - clear the OpenFileCtx DEBUG log by rotating the gateway log (restart) before each run.
9. **Cleanup** per B4.

**B3f. Predictions** (stated before any run; mark = 1,048,576).

| Run | Max counter `v` | Times `v` = 1,048,576 | Counter at PAUSE | Dump file at PAUSE | Live `byte[]` at PAUSE vs. C1@25% | Outcome |
|---|---|---|---|---|---|---|
| C1 | 1,048,576 | 767 | 983,040 | 804,257,792 B (767 MiB) | within ±8 MiB (flat at 25/50/75%/PAUSE) while the dump grows 0 → 767 MiB | completes, no OOM, HDFS file 805,306,368 B, dump file deleted after timeout |
| C2 | ≤ 1,048,576 per update (aggregate of 32 files ≤ 32 × 1,048,576 + 32 × 65,536) | — | aggregate 31,457,280 | 32 files × 15,728,640 B | +30 MiB (between +25 and +40 MiB) above the C1 baseline | completes; shows the instrument sees about 1 MiB per file and the cap is per file |
| C3 | 983,040 | 0 | 983,040 | no dump file (no `Create dump file` line) | about baseline | completes; below the mark nothing is dumped |
| C4 | 1,048,576 | 767 | 0 | 804,257,792 B | within ±8 MiB of the C1 baseline | completes, no OOM |
| C5 (patched) | 67,108,864 | 11 (at `new value: 67108864`) | 67,043,328 | 738,197,504 B | about +64 MiB above C1, sawtooth to about 64 MiB at checkpoints | completes in 512m heap |

**The claim is wrong if any of these is seen:**
- In C1, live `byte[]` grows with the bytes sent (e.g. more than +50 MiB between the 25% and PAUSE checkpoints), or the gateway hits `OutOfMemoryError`.
- The max counter exceeds 1,048,576 + 65,536 for a single file.
- The dump file does not grow to about 767 MiB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| C1 completes in 256 MiB heap; `byte[]` flat; dump file grows to 804,257,792 B; max counter 1,048,576 | Claim confirmed in the real daemon: heap capped per file, excess on local disk |
| C1 `byte[]` rises with progress or OOM | Claim refuted: the mark does not bound held heap |
| C2 heap about +30 MiB at PAUSE and back down after DONE | Positive control: the heap instrument resolves about 1 MiB per file; the cap is per file and scales with open files |
| C2 shows no heap difference | Instrument too coarse; heap-flatness in C1 is not conclusive and rests on the counter and OOM evidence |
| C3 no dump file; C1/C4 dump file | Dumping starts exactly at the mark, not before |
| C4 one dump round per write, counter 0 at PAUSE | Overshoot is bounded by one request (≤ `nfs.wtmax`) |
| C5 heap and counter about 64 MiB | The constant, not something else, sets the held amount (code-change run) |
| Driver stalls; gateway log shows a dump `IOException` and no further replies | Dump-failure bypass (A3) reached; cap lost and connection stuck |
| Read-back differs from 0xAB bytes | Dump/reload corrupts data (side finding; not part of the claim) |

**B3h. Controls.**
- The same driver, mount and heap size are used across C1/C3/C4, varying only size and chunk.
- C2 checks that the heap instrument can see MiB-level held data.
- C3 checks that below the mark nothing is dumped.
- The C1 heap (256 MiB) is set below the workload (768 MiB), so completion alone shows data left the heap.
- DEBUG counter lines give the check's own operand in the real daemon, independent of GC timing.
- An optional baseline: one 768 MiB **sequential** write (`dd if=/dev/zero of=$S4/mnt/nfstest/seq bs=1M count=768 oflag=direct`). It should produce no counter growth and no dump file, showing that only out-of-order data is subject to this mark.

**B4. Risks and cleanup.**
- **Disk:** C1/C4 each use about 0.8 GiB in `nfs-dump` (until stream timeout) and about 0.8 GiB in HDFS. The unit tier uses about 64 MiB per dump run. Everything stays under `$S4` on local disk. Never use the default `/tmp/.hdfs-nfs`, which `clearDirectory` deletes at gateway start (`RpcProgramNfs3.java:232-245`).
- **Root actions:** portmap, mount and umount. On a shared host, do not stop the system rpcbind; use the no-registration launcher. Use a `soft` mount, so a stalled gateway cannot hang processes.
- **Ports:** 111, 2049, 4242, 9000, 9870, 9864/9866/9867, 50079. Move nfs/mountd ports if taken.
- **Memory:** gateway at most 512 MiB, NN/DN 1 GiB each, surefire 2 GiB.
- **Unit tier:** U7 leaves one daemon thread blocked in `wait()`. It is a daemon thread and dies with the surefire JVM; check that no surefire JVM remains with `jps`.
- **Cleanup:**
  1. `sudo umount $S4/mnt`
  2. `hdfs --daemon stop nfs3`, or kill the launcher JVM
  3. `sudo -E hdfs --daemon stop portmap` (if started)
  4. `stop-dfs.sh`
  5. `sudo systemctl start rpcbind` only if it was stopped
  6. `jps`: no NameNode, DataNode, Nfs3 or Portmap left; `rpcinfo -p localhost` shows no 100003/100005 entries from this run
  7. `rm -rf $S4/{nn,dn,tmp,nfs-dump,logs,pids,mnt,obs,unit-dump}`

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/WriteCtx.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/WriteManager.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/RpcProgramNfs3.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtxCache.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/AsyncDataService.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/Nfs3.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/Nfs3Utils.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/Nfs3Metrics.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/conf/NfsConfigKeys.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3/TestWrites.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/TestOutOfOrderWrite.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3/TestRpcProgramNfs3.java (grep only)
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/nfs3/Nfs3Base.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/oncrpc/RpcProgram.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/oncrpc/SimpleTcpServer.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/nfs3/request/WRITE3Request.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/nfs3/FileHandle.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/nfs3/Nfs3FileAttributes.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/NfsExports.java (grep only)
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/CommonConfigurationKeys.java
- hadoop-common-project/hadoop-common/src/main/conf/hadoop-env.sh
- hadoop-common-project/hadoop-common/src/main/conf/log4j.properties
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
- hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/HdfsNfsGateway.md
- hadoop-hdfs-project/hadoop-hdfs/src/main/bin/hdfs
- hadoop-project/pom.xml (surefire argLine)
- https://issues.apache.org/jira/browse/HDFS-7259 (cited from the code comment; not fetched)

## D. Stage-4 feedback

none yet
