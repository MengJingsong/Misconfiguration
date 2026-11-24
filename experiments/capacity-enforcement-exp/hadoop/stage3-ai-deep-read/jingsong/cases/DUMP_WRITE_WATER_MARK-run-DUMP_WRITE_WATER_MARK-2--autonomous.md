# DUMP_WRITE_WATER_MARK — `OpenFileCtx$Dumper.run` `:383` — verification solution  <!-- file: cases/DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK-2--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`OpenFileCtx.java:383`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java#L383): `if (nonSequentialWriteInMemory.get() < DUMP_WRITE_WATER_MARK)` in `OpenFileCtx.Dumper.run()` (the dumper thread's "below the mark, release blocked writers and sleep" check). Main enforcement point: the writer-side gate `OpenFileCtx.waitForDump()` ([`OpenFileCtx.java:278`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java#L278), :284, :294). The stem keeps `run`, the method that encloses the given line. |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive`: in the NFS gateway, the in-heap bytes of out-of-order (non-sequential) WRITE data buffered for one open file are held to about `DUMP_WRITE_WATER_MARK` (1 MiB) plus at most one WRITE. The writer thread is blocked and the dumper moves the excess to a local file under `nfs.dump.dir`. The cap applies to each file separately, not to the whole gateway. It moves memory to disk and puts no limit on the disk, and it fails into a hang (not unbounded growth) when the dump file cannot be created. |
| Ground | — |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). Use a permalink at the pinned tag. Other citations stay plain `file:line`. All plain
> `OpenFileCtx.java`, `WriteCtx.java`, `RpcProgramNfs3.java`, `WriteManager.java` and `NfsConfigKeys.java` citations are under
> `hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/` (`nfs3/` or `conf/`).

## A. Constraint trace

**A1. The constraint.**
- Name: `DUMP_WRITE_WATER_MARK` (class `org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx`).
- Kind: hard-coded constant (`private static long`, not `final`). No configuration key, JVM
  property or setter feeds it, and no code assigns it after initialisation (the only uses are
  `OpenFileCtx.java:278, 284, 294, 379, 383`). Declared at
  [`OpenFileCtx.java:73`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java#L73):
  `private static long DUMP_WRITE_WATER_MARK = 1024 * 1024;`, with the comment "Pending writes water mark for dump, 1MB" (:72).
- Unit: bytes. Default: 1 048 576 (1 MiB). There is no `*-default.xml` entry. The value is
  mentioned only in prose, in the `nfs.dump.dir` description in `hdfs-default.xml:2281-2289`
  ("dumped after they are accumulated to exceed certain threshold (e.g., 1MB)") and in
  `HdfsNfsGateway.md:121-127`.
- How it can be set: it cannot be set from configuration. The only ways to change it are a
  rebuilt `hadoop-hdfs-nfs` jar with a different literal, or reflection inside the JVM. The
  field is non-final static, so `Field.setAccessible(true); setLong(null, v)` works on JDK 8
  and 11. Any change needs a gateway restart.
- Related settings that decide whether the cap is active at all (secondary sources):
  - `nfs.file.dump` (`NfsConfigKeys.DFS_NFS_FILE_DUMP_KEY`, `NfsConfigKeys.java:29-30`, default `true`, not listed in `hdfs-default.xml`).
  - `nfs.dump.dir` (`NfsConfigKeys.java:31-32`, default `/tmp/.hdfs-nfs`, `hdfs-default.xml:2281`).
  
  Both go in `hdfs-site.xml` on the gateway host and need a gateway restart.
- Reader: the HDFS NFS gateway process (`hdfs --daemon start nfs3`, main class
  `org.apache.hadoop.hdfs.nfs.nfs3.Nfs3`). There is one `OpenFileCtx` and one dumper thread for
  each open file.

**A2. What it caps.** The resource is the NFS gateway's JVM **heap**, specifically the `byte[]`
payloads of WRITE requests that arrived ahead of the file's current HDFS write offset
(`nextOffset`) and are parked in `pendingWrites` as `WriteCtx` objects with
`DataState.ALLOW_DUMP`. The quantity compared against the limit is the per-file counter
`nonSequentialWriteInMemory` (`AtomicLong`, `OpenFileCtx.java:178-179`), the sum of `count` over
this file's ALLOW_DUMP writes that are still in memory. Excess bytes are moved to the **local
disk** file `<nfs.dump.dir>/<fileId>`, which no limit caps (see A3 and A4).

**A3. Mechanism.**
1. **Arrival.** `RpcProgramNfs3.write` (`RpcProgramNfs3.java:843-898`) calls `WriteManager.handleWrite`, which calls
   `OpenFileCtx.receivedNewWrite` (:426), which calls `receivedNewWriteInternal` (:642), which calls `addWritesToCache` (:514-587).
   A write whose offset is greater than `nextOffset` gets `DataState.ALLOW_DUMP` (:562-563), and
   the counter is increased by `count` (:570-573, `updateNonSequentialWriteInMemory` :211-220).
   A sequential write (offset equal to `nextOffset`) is `NO_DUMP` and is **not counted**.
2. **Writer-side gate.** If the write cannot start write-back (`checkAndStartWrite` returns false,
   :656-657), `waitForDump()` is called (:659):
   - If dumping is disabled (`enabledDump == false`, :273), it returns, so there is no cap.
   - If counter < mark (:278), it returns.
   - Otherwise, under the `OpenFileCtx` monitor, it starts the dumper daemon thread the first
     time, or `notifyAll()`s it (:284-291).
   - It then **blocks the RPC handler thread** in `while (counter >= mark) wait()` (:294-299),
     ignoring interrupts.
   
   The reply to the client (:665-681) is sent only after this returns, so the client cannot
   complete the WRITE until memory is back under the mark.
3. **Dumper thread** (`Dumper.run`, :376-406):
   - While active and dumping is enabled: if counter ≥ mark (:379), it calls `dump()` (:306-373).
   - `dump()` creates the dump file the first time with `createNewFile()` (:308-331). On
     `IOException` it sets `enabledDump=false` and returns.
   - It then walks `pendingWrites` (largest offset first, `ReverseComparatorOnMin` :237-238),
     calling `WriteCtx.dumpData` (`WriteCtx.java:150-183`). That writes `data` to the file, sets
     `data = null` and state `DUMPED`, and returns `count`, which is subtracted from the counter
     (:358-361).
   - The loop runs **while counter > 0** (:349-350), so a dump drains all ALLOW_DUMP data to the
     file, not just down to the mark.
4. **The given check**,
   [`OpenFileCtx.java:383`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java#L383).
   After a dump, under the `OpenFileCtx` monitor:
   - **If counter < mark:** it `notifyAll()`s the writers blocked in `waitForDump` (:384) and
     waits to be woken by the next writer that crosses the mark (:386).
   - **If counter ≥ mark** (new writes arrived during the dump): it skips the wait and loops
     back to :379 to dump again.
   
   This branch is what releases the back-pressure of step 2.
5. **Release of counted bytes on write-back.** When the gap is filled and an ALLOW_DUMP write is
   written to HDFS, it is set to `NO_DUMP` and the counter is decreased (:1151-1163). A `DUMPED`
   write is read back from the dump file into a new `byte[]` just before it is written
   (`WriteCtx.getData`/`loadData`, `WriteCtx.java:215-242`). That read-back is not counted.
6. **Cleanup.** `cleanup()` (:1218-1282, on close or after the `nfs.stream.timeout` idle time)
   interrupts the dumper and deletes the dump file (:1262-1274).

**Outcomes at the limit:** the handler thread blocks until the dumper has moved this file's
ALLOW_DUMP bytes to disk. The peak counter is `mark - 1 + count_of_last_write`, which is at most
`mark + wsize - 1` per blocked handler thread. One client connection is served by one Netty
worker thread (`SimpleTcpServer.java:67-68`, workers = 0, so Netty's default), so normally there
is one blocked write per file.

**Bypasses and overshoots:**
- *Dump disabled (`nfs.file.dump=false`).* `RpcProgramNfs3` sets `writeDumpDir = null`
  (`RpcProgramNfs3.java:211-212`), but CREATE then builds the path by string concatenation:
  `writeDumpDir + "/" + fileId` (`RpcProgramNfs3.java:1013-1014`) gives `"null/<fileId>"`, so
  `enabledDump` is still `true` (:251). The re-open path ignores the flag altogether
  (`WriteManager.java:182-185`). In either case, if the dump file cannot be created (relative
  dir `null/` missing, `nfs.dump.dir` missing or not writable, or disk full during the write),
  `dump()` sets `enabledDump=false` and returns without `notifyAll` while counter ≥ mark. The
  dumper loop then exits (:377), and the writer blocked at :294-299 is never woken: the handler
  thread hangs (nothing else notifies; :290, :384 and :399 are the only `notifyAll` calls). The
  result is a stuck client, not unbounded heap. Only an `OpenFileCtx` built with a real `null`
  dump path (tests) has `enabledDump=false` from the start, and there the counter is
  **uncapped**.
- *Not counted:*
  - Sequential `NO_DUMP` pending writes. The client is throttled by those replies, which are
    deferred until write-back.
  - Read-back buffers of `DUMPED` writes (step 5).
  - Netty socket and frame buffers.
  - Over-limit bytes from extra handler threads that write the same file over several
    connections. Each adds its `count` before blocking.
- *Per file only:* every open file has its own counter. Gateway-wide, in-heap out-of-order data
  can reach about `nfs.max.open.files` (default 256, `NfsConfigKeys.java:41-42`) × (mark + wsize).
- *Below the mark:* up to mark − 1 bytes can sit in heap indefinitely, until the gap is filled
  or the stream times out (`nfs.stream.timeout`, default 10 min, `NfsConfigKeys.java:44-45`).

**A4. Other consumers.**
- Disk: the dump files under `nfs.dump.dir` are not capped by anything. A file only grows (each
  dump appends, :164-165) until `cleanup()` deletes it. The dir is wiped at gateway start
  (`RpcProgramNfs3.java:213-214, 232-245`).
- Gateway heap otherwise:
  - The `DFSClient` cache and `HdfsDataOutputStream` packet buffers.
  - The `OpenFileCtxCache` (≤ `nfs.max.open.files` contexts).
  - The read path (`nfs.rtmax`).
  - Netty buffers.
  - The `RpcCallCache` (256 entries, `RpcProgramNfs3.java:217`).

**A5. Evidence beyond the source.**
- `hdfs-default.xml:2281-2289` (`nfs.dump.dir` description: "dumped after they are accumulated to exceed certain threshold (e.g., 1MB) in memory … make sure the directory has enough space").
- `hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/HdfsNfsGateway.md:121-127`, same text; published at https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/HdfsNfsGateway.html.
- HDFS-7259 (https://issues.apache.org/jira/browse/HDFS-7259), cited in `OpenFileCtx.java:97` for commit/upload behaviour (context only).
- Tests: `TestWrites.java` builds `OpenFileCtx` directly with mocks (:135-148) and drives a real in-JVM gateway (:460-560). `TestOutOfOrderWrite.java` is a manual out-of-order WRITE client. No existing test covers the watermark.

## B. Verification solution

**B1. Claim under test.** For one open file on the NFS gateway with dumping enabled and a
writable `nfs.dump.dir`, the in-heap bytes of out-of-order WRITE data
(`nonSequentialWriteInMemory`) never exceed `DUMP_WRITE_WATER_MARK + wsize − 1`. Every byte of
out-of-order data beyond that goes to `<nfs.dump.dir>/<fileId>`. So for gap data G ≫ mark, heap
held is O(mark) and dump-file size ≈ G. Moving the mark moves the threshold accordingly.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 8, Maven 3.3+. Work in a local copy of the tag (e.g. `$WORK/hadoop-3.4.2`, never the
  shared tree).
- Build once with `mvn -pl hadoop-hdfs-project/hadoop-hdfs-nfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
- New test `hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3/TestDumpWaterMark.java`.
  It is in the same package, so the package-private API is reachable: `receivedNewWrite`,
  `getPendingWritesForTest`, `cleanup`, `RpcProgramNfs3.metrics`, `AsyncDataService`.
- Run with `mvn -pl hadoop-hdfs-project/hadoop-hdfs-nfs test -Dtest=TestDumpWaterMark`.
- Surefire's default `-ea` is fine: the constructor assert at `OpenFileCtx.java:254` holds
  because the mock `getPos()` returns 0 and the attribute size is 0.
- No MiniDFSCluster is needed. HDFS is never touched, because no write is ever sequential (the
  file offset 0 is never written).

**Test skeleton:**
- `DefaultMetricsSystem.initialize("Nfs3"); RpcProgramNfs3.metrics = Nfs3Metrics.create(conf, "wm-test");`.
  This is needed because `OpenFileCtx.java:676` dereferences it.
- `DFSClient dfs = mock(DFSClient.class)`, `HdfsDataOutputStream fos = mock(...)` with `getPos()` returning 0.
- `Nfs3FileAttributes attr = new Nfs3FileAttributes()` (size 0).
- `dumpDir = Files.createTempDirectory(Paths.get("target"), "wm")`.
- `ctx = new OpenFileCtx(fos, attr, dumpDir + "/16386", dfs, new ShellBasedIdMapping(conf), false, conf)`.
- `AsyncDataService ads = new AsyncDataService()`.
- Writes: `ctx.receivedNewWrite(dfs, new WRITE3Request(new FileHandle(16386, 0), off, w, WriteStableHow.UNSTABLE, ByteBuffer.wrap(new byte[w])), null /*channel*/, xid++, ads, iug)`.
  A null channel is accepted, see `Nfs3Utils.java:140-145`.
- Reflection helpers:
  - `wm(v)` sets `OpenFileCtx.DUMP_WRITE_WATER_MARK`.
  - `ctr()` reads `nonSequentialWriteInMemory`.
  - `inHeap()` sums `count` over `getPendingWritesForTest().values()` whose private field `data` is non-null and whose `getDataState() != DUMPED`.
- Tear down with `ctx.cleanup()`, `ads.shutdown()`, restoring the mark to 1 048 576, and deleting `dumpDir`.

**B2b. Knobs.**

| Knob | Values | Why | How set |
|---|---|---|---|
| K1 mark `DUMP_WRITE_WATER_MARK` | 256 KiB, 1 MiB (default), 4 MiB | shows the threshold follows the constant | reflection `wm(v)` before constructing `ctx` (static, read on each check) |
| K2 write size w | 64 KiB, 96 KiB (not a divisor of the mark), 1 MiB (= default `nfs.wtmax`) | overshoot bound `mark + w − 1` | request `count` |
| K3 dump mode | enabled (real dir); disabled (`dumpFilePath = null`); broken (path under a non-existent dir `dumpDir + "/missing/16386"`) | positive control (uncapped) and failure path | constructor argument |

**B2c. Workload.** Issue N writes, each of size w, at offsets `w, 2w, …, N·w`. The range `[0, w)` is never sent, so every write is out of order and ALLOW_DUMP. Use G = N·w = 16 MiB (N = 256 at 64 KiB, N = 16 at 1 MiB). G is 4× to 64× the mark, so the mark is crossed between 4 and 64 times. In the default case, the 16th 64 KiB write brings the counter to exactly 1 MiB (16 × 65 536 = 1 048 576 ≥ mark).

**B2d. Observables and instruments.**
- `ctr()` after every `receivedNewWrite` returns, and its maximum. The maximum before blocking
  is seen through DEBUG lines `Update nonSequentialWriteInMemory by … new value: …`
  (`OpenFileCtx.java:213-214`). Enable them in `src/test/resources/log4j.properties` with
  `log4j.logger.org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx=DEBUG`, and parse the max "new value".
- `inHeap()` after each write.
- Dump file length `new File(dumpDir, "16386").length()`.
- Count of `DUMPED` entries.
- Whether the dumper thread exists (the `dumpThread` field).
- For K3-broken: the writer runs in a separate daemon thread, and after 10 s the test records its
  `Thread.getState()` and stack (expected: `WAITING` in `waitForDump`).
- Not observable directly: the exact JVM heap retained. `inHeap()` is the exact payload
  bytes still referenced.

**B2e. Procedure.**
1. Copy the tree to local disk, build (B2a), add the test and the log4j line.
2. One `@Test` per (K1, K2) for K3 = enabled: set the mark, build `ctx`, issue the B2c writes, and record the series and the maxima.
3. `@Test` K3 = disabled, with mark 1 MiB and w = 64 KiB.
4. `@Test` K3 = broken, with mark 1 MiB and w = 64 KiB, the writer in a daemon thread, and a join with a 10 s timeout.
5. Run `mvn -pl hadoop-hdfs-project/hadoop-hdfs-nfs test -Dtest=TestDumpWaterMark`, then collect `target/surefire-reports/*-output.txt`.

**B2f. Predictions.**

| K1 mark | K2 w | max counter (DEBUG) | `ctr()`/`inHeap()` after each return | dump file after G = 16 MiB | DUMPED entries |
|---|---|---|---|---|---|
| 256 KiB | 64 KiB | 256 KiB | < 256 KiB (falls to 0 after each dump) | 16 MiB (16 777 216 B) | 256 |
| 1 MiB | 64 KiB | 1 MiB | < 1 MiB | 16 MiB | 256 |
| 4 MiB | 64 KiB | 4 MiB | < 4 MiB | 16 MiB (last 4 MiB-aligned chunk dumped at the 256th write) | 256 |
| 1 MiB | 1 MiB | 1 MiB (each 1 MiB write alone crosses) | 0 | 16 MiB | 16 |
| 1 MiB | 96 KiB (non-aligned), N = 171 | 1 056 KiB (11 × 96 KiB), ≤ 1 MiB + 96 KiB − 1 | < 1 MiB | ≈ 16 MiB (all written bytes but those since the last dump) | ≈ all |

- **K3 disabled:** the counter rises linearly to 16 MiB, `inHeap()` = 16 MiB, there is no dump
  file and no dumper thread.
- **K3 broken:** the writer that brings the counter to 1 MiB stays `WAITING` in
  `OpenFileCtx.waitForDump` indefinitely. The counter is 1 MiB, there is no dump file, and the
  dumper thread has exited.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Max counter ≤ mark + w − 1 and dump file ≈ G for every mark; threshold moves with K1 | claim confirmed for the mechanism |
| Max counter or `inHeap()` exceeds mark + w − 1 with dumping enabled | claim **wrong** (cap leaks) |
| Dump file stays 0 / no DUMPED entries though counter crosses the mark | dumper not triggered; claim wrong for this path |
| Threshold does not move when K1 changes (e.g. dump at 1 MiB with mark 4 MiB) | the constant is not what governs; claim wrong |
| K3 disabled grows to G while K3 enabled stays ≤ mark | positive control moved: the same workload drives memory when uncapped, so the cap is what holds it |
| K3 disabled also stays ≤ 1 MiB | something else bounds it; re-examine (control failed, claim not confirmed) |
| K3 broken: writer hangs | failure path as traced (cap holds by hanging the writer) |
| K3 broken: writer returns and counter keeps growing | broken-dump path bypasses the cap (a memory overshoot, contrary to A3) |

**B2h. Controls.**
- The disabled-dump run uses the same workload without the cap (positive control).
- The K1 sweep shows the threshold follows the constant, not a coincidental 1 MiB elsewhere.
- Counting from both the counter and the independent `inHeap()` sum rules out bookkeeping-only
  agreement.
- The dump file length (bytes really moved to disk) is checked against G.
- The mark is restored in `@After` so test order cannot leak a value.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux host with `sudo` (needed for Hadoop `portmap` on port 111 and for `mount -t nfs`),
  JDK 8, `nfs-common`/`nfs-utils` client installed.
- Distribution: `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true` in a local copy
  of the tag, then unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `$S4/hadoop`.
- Patched gateway jars (knob K1): in a second local copy, change the literal at
  `OpenFileCtx.java:73` to `4 * 1024 * 1024`, and in a third to `1024L * 1024 * 1024` (1 GiB, the
  positive control). Build each with
  `mvn -pl hadoop-hdfs-project/hadoop-hdfs-nfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
  Then swap in `hadoop-hdfs-project/hadoop-hdfs-nfs/target/hadoop-hdfs-nfs-3.4.2.jar` over
  `$S4/hadoop/share/hadoop/hdfs/hadoop-hdfs-nfs-3.4.2.jar`, keeping the stock jar as
  `.stock`.
- Daemons, pseudo-distributed: NameNode, one DataNode, Hadoop `portmap` (root), `nfs3` gateway
  (run as the user).
- Every directory is under `$S4` on local disk (e.g. `/mydata/<person>-s4/o17`, ≥ 5 GiB free):
  `hadoop.tmp.dir=$S4/tmp`, `dfs.namenode.name.dir=$S4/nn`, `dfs.datanode.data.dir=$S4/dn`,
  `nfs.dump.dir=$S4/nfsdump`, `HADOOP_LOG_DIR=$S4/logs`, `HADOOP_PID_DIR=$S4/pids`.
- `core-site.xml`:
  - `fs.defaultFS=hdfs://localhost:9000`
  - `hadoop.proxyuser.$USER.groups=*`
  - `hadoop.proxyuser.$USER.hosts=*`
- `hdfs-site.xml`:
  - `dfs.replication=1`
  - `nfs.dump.dir=$S4/nfsdump`
  - `nfs.file.dump=true`
  - `nfs.exports.allowed.hosts=* rw`
  - `nfs.superuser=$USER`
  - `dfs.namenode.accesstime.precision=3600000`
  - `nfs.wtmax=1048576` (default)
- `hadoop-env.sh`: `export HDFS_NFS3_OPTS="-Xmx512m -XX:+UseG1GC"`.
- `log4j.properties`: add `log4j.logger.org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx=DEBUG`.

**B3b. Knobs.**

| Knob | Values | Why | How set |
|---|---|---|---|
| K1 mark | stock 1 MiB; patched 4 MiB; patched 1 GiB (control, cap effectively absent at G = 64 MiB) | threshold follows the constant; uncapped control | jar swap + `hdfs --daemon stop nfs3; hdfs --daemon start nfs3` (restart; dump dir is wiped at start) |
| K2 mount `wsize` | 65536, 1048576 | overshoot bound mark + wsize − 1 | `mount -o wsize=…` (remount) |
| K3 gap data G | 512 KiB (below mark), 64 MiB | below vs above mark | workload parameter |

**B3c. Workload.**
- Mount with `sudo mount -t nfs -o vers=3,proto=tcp,nolock,noacl,hard,wsize=$W localhost:/ $S4/mnt`.
  Do **not** use `sync`: a sync mount sends writes in order.
- Then run `python3 -I ooo.py $S4/mnt/o17-file G`, where `ooo.py` does the following:
  1. Open the file with `O_CREAT|O_WRONLY`.
  2. Write G bytes as 1 MiB `os.pwrite` blocks at offsets `1 MiB … 1 MiB + G`. Offset 0 is skipped.
  3. `os.fsync(fd)`, which forces the kernel to send every block as a WRITE RPC, all beyond the
     gateway's `nextOffset` 0.
  4. Print "GAP-SENT" and sleep 60 s (the observation window).
  5. `pwrite` the missing `[0, 1 MiB)`, `fsync`, close.
- Arithmetic: G = 64 MiB is 64 times the stock mark and 16 times the 4 MiB mark. With the 1 GiB
  control nothing is dumped and all 64 MiB stays in heap, which fits in `-Xmx512m`.
- The run takes about 2 min per point, well under `nfs.stream.timeout` (10 min).

**B3d. Observables and instruments.**
- **Operand:** gateway log `$S4/logs/hadoop-*-nfs3-*.log`. Track the maximum of `new value: N` in
  `Update nonSequentialWriteInMemory` lines during the gap phase, `Create dump file:` lines, and
  `Asking dumper to dump...` lines.
- **Disk:** `du -b $S4/nfsdump/*` and `ls -l`, sampled every 1 s during the window. A
  `stat --format=%s` loop writes it to `disk.csv`.
- **Heap:**
  - At "GAP-SENT" + 10 s: `jcmd $(jps | awk '/Nfs3/{print $1}') GC.class_histogram | awk '$4=="[B"'`.
    This is a forced full GC histogram of live objects; read the bytes of `[B`.
  - Also `jstat -gc <pid> 1000` for old-gen use after the GC.
  - The same histogram taken before the workload is the baseline. Report Δ`[B` = gap-phase
    value minus baseline.
- **HDFS:** after close, `hdfs dfs -stat %b /o17-file` = G + 1 MiB, and
  `hdfs dfs -cat /o17-file | cmp - localcopy` checks integrity.
- **Not observable directly:** the per-file counter split across files. Use one file per run.

**B3e. Procedure.**
1. Build and unpack (B3a). Format the NameNode with `hdfs namenode -format`. Start it with
   `hdfs --daemon start namenode; hdfs --daemon start datanode`.
2. `sudo systemctl stop rpcbind rpcbind.socket nfs-server 2>/dev/null || true`. Then
   `sudo -E $S4/hadoop/bin/hdfs --daemon start portmap`. Then `hdfs --daemon start nfs3`.
   Check with `rpcinfo -p localhost | grep -E 'nfs|mountd'`.
3. For each (K1, K2, K3) point:
   1. Restart nfs3 with the jar for K1.
   2. Remount with K2.
   3. Take the baseline histogram.
   4. Start the samplers.
   5. Run `ooo.py`.
   6. At GAP-SENT + 10 s, take the histogram and `du`.
   7. After the script ends, verify HDFS length and content.
   8. `hdfs dfs -rm /o17-file`.
   9. Save the log segment.
4. Run order: stock with wsize 1 MiB and G 64 MiB, then G 512 KiB. Stock with wsize 64 KiB and G
   64 MiB. Patched 4 MiB with G 64 MiB. Control 1 GiB with G 64 MiB.
5. Cleanup per B4.

**B3f. Predictions.**

| K1 | K2 | G | max `new value` in log | dump file during window | Δ live `[B` at window |
|---|---|---|---|---|---|
| 1 MiB | 1 MiB | 64 MiB | ≤ 1 MiB + 1 MiB − 1 (aligned: exactly 1 MiB) | ≈ 64 MiB (67 108 864 B) | ≈ 0–2 MiB (O(mark), not O(G)) |
| 1 MiB | 1 MiB | 512 KiB | 512 KiB | absent (no `Create dump file`) | ≈ 0.5 MiB |
| 1 MiB | 64 KiB | 64 MiB | ≤ 1 MiB + 64 KiB − 1 | ≈ 64 MiB | ≈ 0–2 MiB |
| 4 MiB | 1 MiB | 64 MiB | ≤ 4 MiB + 1 MiB − 1 | ≈ 64 MiB | ≈ 0–5 MiB |
| 1 GiB (control) | 1 MiB | 64 MiB | 64 MiB | absent | ≈ 64 MiB |

After the gap is filled, all points give HDFS length G + 1 MiB with identical content.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Stock/4 MiB: max counter ≤ mark + wsize − 1, dump ≈ G, Δ`[B` = O(mark); control: Δ`[B` ≈ G, no dump | claim confirmed: the constant caps gateway heap and diverts the rest to disk |
| Stock: Δ`[B` grows ≈ G or max counter ≫ mark + wsize | claim **wrong** |
| Dump created at 1 MiB with the 4 MiB jar | the constant is not the governing value; claim wrong |
| Control (1 GiB) also shows Δ`[B` small and no dump | the kernel client did not deliver out-of-order WRITEs (workload failed), so the claim is not confirmed: check log for `ALLOW_DUMP`-path DEBUG lines and rerun with smaller G or with `wsize=65536` |
| No `Update nonSequentialWriteInMemory` lines at all | writes were sequential or DEBUG not on; not confirmed |
| Client hangs at fsync with "Create dump file" error in log | dump file failure path of A3; check `nfs.dump.dir` permissions (a finding about the failure path, not about the cap) |

**B3h. Controls.**
- The 1 GiB jar runs the same workload with the cap out of reach. This positive control shows
  the workload does move heap by ≈ G.
- The 512 KiB point stays below the mark, so heap holds the data and nothing is dumped.
- The baseline histogram and a single file per run take out unrelated gateway heap.
- The integrity check after filling the gap rules out data being dropped rather than dumped.
- Restarting the gateway per K1 point gives a clean dump dir and counter.

**B4. Risks and cleanup.**
- **Disk:** dump files reach G (64 MiB) in `$S4/nfsdump`, and HDFS data is G + 1 MiB per run.
  Keep `$S4` on local disk with ≥ 5 GiB free. No use of `/tmp` (override the default
  `nfs.dump.dir=/tmp/.hdfs-nfs`).
- **Ports:** 111 (portmap), 2049 (nfs3), 4242 (mountd), 9000/9864/9866/9867/9870 (HDFS). Check
  first that none is in use, and that no system rpcbind or nfs-server is serving other users on
  a shared node. If the node relies on system rpcbind, use the root-start
  `HDFS_NFS3_SECURE_USER` mode (`HdfsNfsGateway.md:227`) instead of stopping it, and restore it
  afterwards with `sudo systemctl start rpcbind`.
- **Hangs:** a hard mount blocks clients if the gateway stops first. Always unmount first.
- **Cleanup:**
  1. `sudo umount -f -l $S4/mnt`.
  2. `hdfs --daemon stop nfs3; sudo -E $S4/hadoop/bin/hdfs --daemon stop portmap; hdfs --daemon stop datanode; hdfs --daemon stop namenode`.
  3. Check that `jps` (and `sudo jps`) show no `Nfs3`, `Portmap`, `NameNode` or `DataNode`.
  4. Restore the system rpcbind if it was stopped.
  5. `rm -rf $S4/nfsdump $S4/nn $S4/dn $S4/tmp`.
- **Unit tier:** the test writes only under `target/`. A K3-broken writer thread is a daemon
  thread, so the forked surefire JVM exits. Check with `jps` that no surefire JVM is left.

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/WriteCtx.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/WriteManager.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/RpcProgramNfs3.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/Nfs3Utils.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/Nfs3Metrics.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/AsyncDataService.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/conf/NfsConfigKeys.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3/TestWrites.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/TestOutOfOrderWrite.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/nfs3/Nfs3Base.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/nfs3/request/WRITE3Request.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/nfs3/FileHandle.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/oncrpc/SimpleTcpServer.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/oncrpc/RpcProgram.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml (nfs.* entries, 2270-2310)
- hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/HdfsNfsGateway.md
- hadoop-hdfs-project/hadoop-hdfs/src/main/bin/hdfs (nfs3/portmap subcommands)
- hadoop-common-project/hadoop-common/src/main/conf/log4j.properties
- https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/HdfsNfsGateway.html (same content as the .md)
- https://issues.apache.org/jira/browse/HDFS-7259 (referenced from source comment)

## D. Stage-4 feedback

none yet
