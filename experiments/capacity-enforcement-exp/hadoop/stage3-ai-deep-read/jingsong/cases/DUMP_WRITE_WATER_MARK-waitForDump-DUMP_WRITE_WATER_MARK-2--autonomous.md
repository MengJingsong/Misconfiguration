# DUMP_WRITE_WATER_MARK — `OpenFileCtx.waitForDump` `:284` — verification solution  <!-- file: cases/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-2--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`OpenFileCtx.java:284`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java#L284): `if (nonSequentialWriteInMemory.get() >= DUMP_WRITE_WATER_MARK)` in `OpenFileCtx.waitForDump()` (row unit; this is also the main enforcement point) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive`: the 1 MiB constant bounds, per open file, the NFS gateway heap held by out-of-order (non-sequential) WRITE payloads. Once the counted bytes reach it, the RPC thread that handles the WRITE blocks until a per-file dumper thread has moved all of them to a local dump file, so the counted bytes return to 0. The cap is per file and is overshot by at most one request (≤ `nfs.wtmax`, 1 MiB) while the request is being handled. It trades heap for local disk, and that disk is not capped. |
| Ground | — |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). Use a permalink at the pinned tag,
> `[`File.java:123`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/<full path under the repository root>#L123)`
> (a range is `#L123-L130`). Check that the line number is the line you mean. Other citations may
> stay plain `file:line`.

All paths below are relative to `hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/` unless they are written in full.

## A. Constraint trace

**A1. The constraint.**
- Name: `DUMP_WRITE_WATER_MARK` (field of `org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx`). The bare name is unique in the tree. A grep of all `*.java` finds it only in `OpenFileCtx.java`.
- Kind: a constant or hard-coded variable. It is declared `private static long`, not `final`, with comment `// Pending writes water mark for dump, 1MB`.
- First declared: [`OpenFileCtx.java:73`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java#L73) `private static long DUMP_WRITE_WATER_MARK = 1024 * 1024;`.
- `*-default.xml`: none. No key maps to it. The `nfs.dump.dir` description in `hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml:2280-2289` mentions it only in prose: "out-of-order writes are dumped after they are accumulated to exceed certain threshold (e.g., 1MB) in memory". `HdfsNfsGateway.md:121-130` says the same.
- Unit: bytes, counted as the WRITE `count` fields. Default 1,048,576 (1 MiB), from the initializer. There is no XML value that could compete with it.
- How it can be set: it cannot be set through configuration, a `-D` option or a refresh. The code has no setter and no `@VisibleForTesting` accessor. Because the field is not `final`, a test in the same JVM can change it by reflection. A changed value in a running gateway needs a patched `hadoop-hdfs-nfs` jar and a gateway restart.
- Which process reads it: the HDFS NFS gateway (`hdfs nfs3`). It reads the value in `waitForDump()` (`OpenFileCtx.java:278,284,294`) and in `Dumper.run()` (`OpenFileCtx.java:379,383`).
- Related settings that are not this constraint. A1 lists them because they decide whether the cap is active and where the spilled data goes:
  - `nfs.dump.dir` (`NfsConfigKeys.java:31-32`, default `/tmp/.hdfs-nfs`) is the spill directory.
  - `nfs.file.dump` (`NfsConfigKeys.java:29-30`, default `true`). A3 explains why it does not actually switch dumping off.
  - `nfs.wtmax` (`NfsConfigKeys.java:36-37`, default 1 MiB) is the largest WRITE request, and so the overshoot bound.
  - `nfs.max.open.files` (`NfsConfigKeys.java:41-42`, default 256) is the number of `OpenFileCtx` instances, each of which has its own cap.

**A2. What it caps.**
- Resource: NFS gateway JVM heap. Specifically, the `byte[]` payloads of WRITE requests that arrived ahead of the file's current write offset and are held in `OpenFileCtx.pendingWrites` (`OpenFileCtx.java:123`). Each payload is a fresh `byte[count]` from `XDR.readFixedOpaque` (`hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/nfs3/request/WRITE3Request.java:41`, `.../oncrpc/XDR.java:138-143`), so the counted bytes match the retained payload bytes closely.
- Compared quantity: `nonSequentialWriteInMemory` (`OpenFileCtx.java:179`), an `AtomicLong` per open file. It goes up by `count` for every write in state `ALLOW_DUMP`, meaning a write with `offset > nextOffset` (`OpenFileCtx.java:562-573`). It goes down when such data is dumped (`OpenFileCtx.java:358-361`) or written to HDFS (`OpenFileCtx.java:1152-1156`).
- The scope is per open file (per `OpenFileCtx`), not per gateway.

**A3. Mechanism.**
1. An NFS WRITE goes through `RpcProgramNfs3.write` (`RpcProgramNfs3.java:834-898`), then `WriteManager.handleWrite` (`WriteManager.java:122`), then `OpenFileCtx.receivedNewWrite` (`WriteManager.java:212-213`, `OpenFileCtx.java:426`), then `receivedNewWriteInternal` (`OpenFileCtx.java:642`).
2. `addWritesToCache` (`OpenFileCtx.java:515`) puts the write into `pendingWrites`. If `offset != nextOffset`, its state is `ALLOW_DUMP` and the counter goes up by `count` (`OpenFileCtx.java:562-573`). A write with `offset == nextOffset` is `NO_DUMP` and is not counted.
3. `checkAndStartWrite` (`OpenFileCtx.java:623-640`) starts the write-back only when the write is sequential. Otherwise `waitForDump()` is called (`OpenFileCtx.java:659`) on the RPC (Netty worker) thread, before the WRITE is answered.
4. `waitForDump()` (`OpenFileCtx.java:272-302`):
   - It returns at once if `enabledDump` is false (`:273`). It also returns, without taking a lock, if the counter is below the mark (`:278`).
   - Otherwise, under the `OpenFileCtx` monitor, the check [`OpenFileCtx.java:284`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java#L284) runs: `if (nonSequentialWriteInMemory.get() >= DUMP_WRITE_WATER_MARK)`.
   - **True branch** (limit reached): it starts the per-file `Dumper` daemon thread on first use (`:286-288`) or `notifyAll()`s it (`:290`). The RPC thread then loops `wait()` while the counter is still at or above the mark (`:294-299`). This is the back-pressure: the client gets no WRITE reply until the data is spilled.
   - **False branch**: none. This branch runs only if the counter fell in the gap after `:278`. The wait loop then exits at once.
5. `Dumper.dump()` (`OpenFileCtx.java:306-373`):
   - On first use it creates the dump file `<nfs.dump.dir>/<fileId>` (`:308-317`, path built at `WriteManager.java:182-185` and `RpcProgramNfs3.java:1013-1015`).
   - It walks every pending write and calls `WriteCtx.dumpData` (`WriteCtx.java:150-183`). That method appends the payload to the dump file, sets `data = null`, marks the write `DUMPED`, and returns `count`. The counter goes down by that amount (`OpenFileCtx.java:358-361`).
   - The loop goes on while the counter is `> 0` (`:349-350`), so it drains all counted data, not just down to the mark.
   - `Dumper.run()` then sees the counter below the mark, `notifyAll()`s the blocked writer, and waits (`:382-392`).
6. When the hole at `nextOffset` is finally written, the write-back reads dumped data back one request at a time (`WriteCtx.loadData`, `WriteCtx.java:229-241`) and writes it to HDFS.
7. The dump file is deleted only in `cleanup()` (`OpenFileCtx.java:1218`, `:1262-1273`). That runs on stream close, eviction, or `nfs.stream.timeout` (10 min default, `NfsConfigKeys.java:44-45`). The whole dump directory is cleared at gateway start (`RpcProgramNfs3.java:213-214`, `:232-244`).

Overshoot and bypass paths:
- **Overshoot.** The check runs after the write is added. While a request is being handled, the counted bytes can reach `mark - 1 + count` (below 2 MiB at default `nfs.wtmax`). Concurrent writes to the same file over different connections can each add before either one blocks. One mount's TCP connection is served by one Netty event-loop thread (`Nfs3Base.java:64-66`, `SimpleTcpServer.java:68`), so a single client is serial.
- **Not counted.** Sequential (`NO_DUMP`) data that is queued for write-back is not counted (`OpenFileCtx.java:562-563`).
- **Per-file only.** The cap applies per file. With up to `nfs.max.open.files` (256) open contexts, the gateway-wide total of out-of-order data is not capped by this constant (about 256 × (1 MiB + one request)).
- **Dump failure (source-inferred).** Any `IOException` while creating or writing the dump file sets `enabledDump = false` (`OpenFileCtx.java:318-330, 336-342, 362-367`). After that:
  - Every later `waitForDump` returns at `:273`, so out-of-order data for that file is no longer capped.
  - The writer already waiting at `:294-299` gets no `notifyAll()` on that path: `Dumper.run()` only notifies when the counter is below the mark (`:383-384`), and then exits its loop. So that writer appears to stay blocked.
  - A full `nfs.dump.dir` therefore turns the memory cap into a stalled connection.
- **`nfs.file.dump=false` does not switch dumping off (source-inferred).**
  - `RpcProgramNfs3` sets `writeDumpDir = null` (`RpcProgramNfs3.java:211-212`). The CREATE path then builds the string `"null/<fileId>"` (`RpcProgramNfs3.java:1014`).
  - `WriteManager` always builds `<nfs.dump.dir>/<fileId>` (`WriteManager.java:182-185`).
  - So `dumpFilePath` is never `null` and `enabledDump` (`OpenFileCtx.java:251`) is always true in the gateway.
  - The flag only skips creating the dump directory, so the first dump probably fails as in the previous bullet.

**A4. Other consumers.**
Gateway heap that this constant does not control:
- Sequential `NO_DUMP` payloads waiting for the async write-back (`AsyncDataService`).
- The one payload that `loadData` reads back during write-back.
- `DFSClient` / `DFSOutputStream` packet buffers for each open `HdfsDataOutputStream`.
- READ buffers (`nfs.rtmax`), Netty buffers, the RPC call cache (`RpcProgramNfs3.java:217`), and `DFSClientCache`.
- Out-of-order data of all other open files, each capped separately.

Disk that this constant does not control:
- The dump files themselves. They grow without any cap, by the full amount of out-of-order data, until cleanup.
- Gateway logs.

**A5. Evidence beyond the source.**
- `hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml:2280-2289` (`nfs.dump.dir`: "dumped after they are accumulated to exceed certain threshold (e.g., 1MB) in memory. One needs to make sure the directory has enough space").
- `hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/HdfsNfsGateway.md:121-130` (the same text, plus sizing advice: 10 files × 100 MB means about 1 GB of dump space). Published at https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/HdfsNfsGateway.html.
- The code comment at `OpenFileCtx.java:82-97` cites HDFS-7259 (https://issues.apache.org/jira/browse/HDFS-7259) for commit handling of staged data.
- Existing tests (`src/test/java/.../nfs3/TestWrites.java`) build `OpenFileCtx` with a mocked `HdfsDataOutputStream`. None of them exercises the dumper.

## B. Verification solution

**B1. Claim under test.** Out-of-order WRITE payloads that one open file holds in the NFS gateway heap are capped by `DUMP_WRITE_WATER_MARK`. Once a request is answered, the counted in-memory bytes are below the mark; while a request is handled they never exceed mark + one request. Everything beyond the cap appears in `<nfs.dump.dir>/<fileId>`. If the mark changes, the in-memory amount and the spill points move with it, and without the cap (control) all out-of-order data stays in heap.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 8 and Maven 3.3+.
- Copy the tree to local disk first: `rsync -a ~/hadoop-3.4.2/ /mydata/<run>/src/`. Work only in that copy.
- Install the module and its dependencies once: `cd /mydata/<run>/src && mvn -pl hadoop-hdfs-project/hadoop-hdfs-nfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
- Add the new test class `hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3/TestDumpWaterMark.java`. It must be in package `org.apache.hadoop.hdfs.nfs.nfs3`, because the `OpenFileCtx` constructor, `receivedNewWrite`, `getPendingWritesForTest` and `RpcProgramNfs3.metrics` are package-visible.
- Default surefire JVM options are enough. Running the 4 MiB arm needs about 64 MiB of heap.

> **Amendment 2026-11-25 (stage-4 audit, before any reading; B2f/B2g unchanged).** Environment of the Hadoop stage-4 nodes
> (`hadoop/stage4-runtime-verification/jingsong/environment.md`): the local copy is made with that folder's
> `copy-source.sh /mydata/jingsong-s4/<stem>-run1/src` (there is no `~/hadoop-3.4.2`), and the `-am install` step is skipped
> because every 3.4.2 module is already in `~/.m2` on the node; the test runs offline (`mvn -o`). Surefire heap is set to
> `-Xmx512m`.

**B2b. Knobs.** The value of `DUMP_WRITE_WATER_MARK`, set by reflection before each arm (the field is static and non-final, and is read on every check) and restored in `@After`:

```java
Field mark = OpenFileCtx.class.getDeclaredField("DUMP_WRITE_WATER_MARK");
mark.setAccessible(true);
mark.setLong(null, M);
```

Values for M:
- 256 KiB, to show that a lower mark lowers the ceiling.
- 1 MiB, the shipped default.
- 4 MiB, to show that a higher mark raises it.
- Control arm: dump disabled by constructing `OpenFileCtx` with `dumpFilePath = null` (`OpenFileCtx.java:251`). There is then no cap.

**B2c. Workload.**
- One `OpenFileCtx` per arm, built like this:
  - A mocked `HdfsDataOutputStream` whose `getPos()` returns 0 (pattern from `TestWrites.java:137-144`).
  - `new Nfs3FileAttributes()` (size 0, so `nextOffset = 0`).
  - A mocked `DFSClient`, `new ShellBasedIdMapping(conf)`, `aixCompatMode=false`, `new NfsConfiguration()`.
  - `dumpFilePath = new File(GenericTestUtils.getTestDir(), "dump-" + M).getPath()`, deleted beforehand (`createNewFile` must succeed, `OpenFileCtx.java:314`).
- Before the first ctx, set `RpcProgramNfs3.metrics = Nfs3Metrics.create(conf, "dumpwm-test")` once in `@BeforeClass`. The non-sequential path calls `metrics.addWrite` (`OpenFileCtx.java:676`).
- Send N = 255 non-sequential writes of r = 64 KiB: for k = 1..255, call `ctx.receivedNewWrite(dfsClient, new WRITE3Request(new FileHandle(1), k*r, r, WriteStableHow.UNSTABLE, ByteBuffer.wrap(new byte[r])), null /*channel*/, k /*xid*/, Mockito.mock(AsyncDataService.class), iug)`. A `null` channel is accepted (`Nfs3Utils.java:141-145`).
- Offset 0 is never written, so every write is `ALLOW_DUMP` and nothing is written back.
- Arithmetic: 255 × 64 KiB = 15.94 MiB. That is about 64× the 256 KiB mark, 16× the 1 MiB mark and 4× the 4 MiB mark, so every capped arm spills many times.
- Extra sub-test (shows that sequential data is not counted): one write at offset 0 into a fresh ctx.

> **Amendment 2026-11-25 (stage-4 audit; instrument only, B2f/B2g unchanged).** Each `receivedNewWrite` call is run on a
> daemon worker thread and the test waits at most 10 s for it. A call that does not return is logged as a `BLOCKED` row
> (this is how step 5's "does not return" is observed, instead of relying on the JUnit timeout alone); the blocked writer is
> then released (counter set to 0 plus `notifyAll()`) so `cleanup()` can run. In the bypass probe, after the block, a second
> writer sends 16 more out-of-order writes to the same ctx and the counter is logged (extra observation for A3's
> "no longer capped"; not a B2f prediction).

**B2d. Observables and instruments.**
After each `receivedNewWrite` returns, read and log one CSV row per write (`M,k,counted,dumpLen,dumped,maxSeen`):
- `counted`: `((AtomicLong) field("nonSequentialWriteInMemory").get(ctx)).get()`.
- `dumpLen`: `new File(dumpFilePath).length()`.
- `dumped`: the number of `pendingWrites` entries with `getDataState() == DUMPED`, through `ctx.getPendingWritesForTest()`.
- The sum of `data != null` payload sizes, by reflection on `WriteCtx.data`.

The peak during a call cannot be read from outside the call. Infer it as `counted_before + r`. Optionally confirm it with DEBUG logging of `OpenFileCtx` ("Update nonSequentialWriteInMemory by ... new value ...", `OpenFileCtx.java:213-214`) and take the maximum.

**B2e. Procedure.**
1. Write the test as in B2c and B2d. Use one `@Test(timeout = 60000)` method per M, and a control method with `dumpFilePath = null`.
2. Run `cd /mydata/<run>/src && mvn -pl hadoop-hdfs-project/hadoop-hdfs-nfs test -Dtest=TestDumpWaterMark`.
3. Collect the CSV from `hadoop-hdfs-project/hadoop-hdfs-nfs/target/surefire-reports/*TestDumpWaterMark-output.txt`.
4. In each test, call `ctx.cleanup()` at the end and check that the dump file is deleted (`OpenFileCtx.java:1262-1273`).
5. Optional probe of the bypass: point `dumpFilePath` at a file whose parent directory does not exist, at M = 1 MiB, with `@Test(timeout = 20000)`. Record whether write k = 16 returns.

**B2f. Predictions.** With r = 64 KiB and q = M / r writes per spill:

| M | q | counted after write k | dump file after write 255 | max counted (debug log) |
|---|---|---|---|---|
| 256 KiB | 4 | (k mod 4)·r; 0 at k = 4, 8, … | 63·256 KiB = 16,515,072 B | 262,144 |
| 1 MiB | 16 | (k mod 16)·r; 0 at k = 16, 32, … | 15·1 MiB = 15,728,640 B | 1,048,576 |
| 4 MiB | 64 | (k mod 64)·r; 0 at k = 64, 128, 192 | 3·4 MiB = 12,582,912 B | 4,194,304 |
| control (no dump) | — | k·r, up to 16,711,680 B at k = 255 | no file | 16,711,680 |

- In every capped arm, after every write, `counted == sum of non-null payload bytes`, and `counted + dumpLen == k·r`.
- The dump file grows in steps of exactly M.
- Sequential sub-test: `counted == 0` after the write at offset 0.
- Bypass probe: the call for k = 16 does not return, and the timeout fires. This is source-inferred and the weakest prediction.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Sawtooth with period q, counted after each call `< M`, dump grows in steps of M, for all three M | Claim confirmed at the mechanism level; the ceiling follows the knob |
| Counted after a call ≥ M in a capped arm, or dump file size not a multiple of M | Claim wrong: the check does not bound the counter as traced |
| Counted grows linearly in a capped arm (no spill) | Claim wrong: the cap does not bind (dumper never runs) |
| Ceiling is the same for 256 KiB and 4 MiB | Claim wrong: the field is not the governing limit (or reflection did not take) |
| Control arm also flat | Not confirmed: the workload is not non-sequential or the counter is not wired; check the offsets |
| `counted` differs from the non-null payload bytes | The operand does not track real heap; the cap is on a proxy only |
| Bypass probe returns at k = 16 | A3's hang inference is wrong (does not change B1) |

**B2h. Controls.**
- The no-dump arm, with the same workload and no cap, shows the counter is driven by the workload.
- The sequential sub-test shows only out-of-order data is counted.
- The mocked output stream makes sure no write-back drains memory, so any decrease can only come from the dumper.
- `counted + dumpLen == k·r` rules out lost data.
- Each arm uses a fresh ctx and dump file, and the mark is restored in `@After`.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux host with sudo, needed for the RPC portmapper registration and the NFS mount. Run data goes under `/mydata/<run>/` on local disk with at least 2 GB free.
- Distribution:
  - `cd /mydata/<run>/src && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`.
  - Unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `/mydata/<run>/hadoop` (`HADOOP_HOME`).
  - The gateway jar is `$HADOOP_HOME/share/hadoop/hdfs/hadoop-hdfs-nfs-3.4.2.jar` (`hadoop-assemblies/src/main/resources/assemblies/hadoop-hdfs-nfs-dist.xml:26`).
- Daemons, all pseudo-distributed on this host:
  - NameNode and DataNode, started as `$USER` with `start-dfs.sh`.
  - The NFS gateway `hdfs nfs3`, which runs the NFS and MOUNT services.
  - A portmapper: either the system `rpcbind` with the gateway started as root and `HDFS_NFS3_SECURE_USER=$USER` (`HdfsNfsGateway.md:227`; no system restart), or, if the host has no `rpcbind`, `sudo -E $HADOOP_HOME/bin/hdfs --daemon start portmap`.
  - Check first that no kernel NFS server holds 2049 (`rpcinfo -p`). If one does, set `nfs.server.port` / `nfs.mountd.port` to free ports and pass `port=`/`mountport=` at mount time.
- `etc/hadoop/core-site.xml`:
  - `fs.defaultFS=hdfs://localhost:9000`
  - `hadoop.tmp.dir=/mydata/<run>/tmp`
  - `hadoop.proxyuser.$USER.groups=*`
  - `hadoop.proxyuser.$USER.hosts=*`
- `etc/hadoop/hdfs-site.xml`:
  - `dfs.replication=1`
  - `dfs.namenode.name.dir=/mydata/<run>/nn`
  - `dfs.datanode.data.dir=/mydata/<run>/dn`
  - `nfs.dump.dir=/mydata/<run>/nfs-dump`
  - `nfs.exports.allowed.hosts=* rw`
  - `nfs.file.dump=true` (default)
  - `nfs.wtmax=1048576` (default)
  - `nfs.stream.timeout=600000` (default)
- `etc/hadoop/hadoop-env.sh`:
  - `HADOOP_LOG_DIR=/mydata/<run>/logs`
  - `HADOOP_PID_DIR=/mydata/<run>/pids`
  - `HDFS_NFS3_OPTS="-Xms1g -Xmx1g -XX:NativeMemoryTracking=summary"`
- `etc/hadoop/log4j.properties`: add `log4j.logger.org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx=DEBUG`.
- Mount: `sudo mount -t nfs -o vers=3,proto=tcp,nolock,noacl,sync,wsize=65536 localhost:/ /mydata/<run>/mnt` (`HdfsNfsGateway.md:280`, plus `wsize`). The `sync` option makes each `pwrite` go out as its own WRITE RPC, in program order.

**B3b. Knobs.** `DUMP_WRITE_WATER_MARK`, which can only be changed by rebuilding the gateway jar from the local copy:
1. `sed -i 's/private static long DUMP_WRITE_WATER_MARK = 1024 \* 1024;/private static long DUMP_WRITE_WATER_MARK = <V>;/' hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java`
2. `mvn -o -pl hadoop-hdfs-project/hadoop-hdfs-nfs package -DskipTests`
3. Copy `target/hadoop-hdfs-nfs-3.4.2.jar` over the distribution jar. Keep the original as `.orig`.
4. Restart only the gateway.

Values:
- `1024 * 1024`, the stock jar.
- `8L * 1024 * 1024`.
- `64L * 1024 * 1024`, so the heap difference is far above GC noise.
- Positive control (no cap): `Long.MAX_VALUE`.

**B3c. Workload.**
- On the mount, run `python3 oow.py /mydata/<run>/mnt/t<arm> 4095 65536 120`:
  - open with `O_CREAT|O_WRONLY`;
  - for k = 1..4095, `os.pwrite(fd, os.urandom(65536), k*65536)`;
  - print a timestamp, then `sleep 120` (the hold);
  - `os.pwrite` the block at offset 0, then `os.fsync`, then close.
- Out-of-order bytes: 4095 × 64 KiB = 268,369,920 B (255.94 MiB). That is 256× the 1 MiB mark, so the cap is reached many times.
- Each arm runs in about 2–5 min plus the hold.
- Sequential control: write the same 256 MiB file with k = 0..4095 ascending.

**B3d. Observables and instruments.**
Every 1 s from workload start to end of hold:
- Dump file size: `stat -c %s /mydata/<run>/nfs-dump/*` (one file; its name is the HDFS inode id).
- Free space on the dump directory: `df -B1 /mydata/<run>/nfs-dump`.
- Gateway RSS: `/proc/<nfs3pid>/status` `VmRSS`.

During the hold (about 60 s in):
- `jcmd <nfs3pid> GC.class_histogram`. This forces a full GC. Record total bytes of `[B` and the instance count of `org.apache.hadoop.hdfs.nfs.nfs3.WriteCtx`.
- `jcmd <nfs3pid> GC.heap_info`.
- Take the same histogram once before the workload, as the baseline.

From the gateway log:
- The maximum and the last value of `Update nonSequentialWriteInMemory by ... new value: ...`.
- `Create dump file:` lines.
- The `WRITE ... offset ... count` debug lines, to confirm request size 65536 and ascending order.

After the hold:
- `hdfs dfs -cat /t<arm> | md5sum` compared with the md5 of the bytes written (`oow.py` prints it).

Cannot be observed directly: the heap held only by payloads. Infer it as the `[B` delta from baseline, and cross-check with dump size: `in_memory = 268,369,920 − dumpsize`.

**B3e. Procedure.**
1. Format and start HDFS: `hdfs namenode -format -force`, then `start-dfs.sh`. Run `hdfs dfs -chmod 777 /`.
2. Start the portmapper if needed. Start the gateway: `sudo -E HDFS_NFS3_SECURE_USER=$USER $HADOOP_HOME/bin/hdfs --daemon start nfs3`. Check with `rpcinfo -p localhost` and `showmount -e localhost`.
3. Mount as in B3a.
4. For each arm (stock 1 MiB, 8 MiB, 64 MiB, `Long.MAX_VALUE`), then the sequential control on the stock jar:
   1. Swap the jar and restart the gateway. The restart clears `nfs.dump.dir`.
   2. Remount if needed.
   3. Take the baseline histogram.
   4. Start the 1 s samplers.
   5. Run `oow.py`, and take the hold-time histogram.
   6. After close, verify the md5.
   7. Stop the samplers.
5. Restore the original jar.

> **Amendment 2026-11-25 (stage-4 audit, before any reading; B3f/B3g unchanged).** Runbook fixes for the Hadoop stage-4
> nodes (`environment.md` §4), none of which changes the workload, the knob values or the predictions:
> 1. **Distribution:** copy the node's built distribution (`cp -a /mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2 <run>/hadoop`)
>    instead of rebuilding it. The three changed jars (`8L * 1024 * 1024`, `64L * 1024 * 1024`, `Long.MAX_VALUE`) are built
>    in the per-case copy with `mvn -B -o -q package -pl hadoop-hdfs-project/hadoop-hdfs-nfs -Dmaven.test.skip=true`, one
>    `sed` per value on line 73, `git checkout` after each; the constant in each jar is checked with `javap -c` (`static {}`).
> 2. **HDFS:** `ssh localhost` does not work on these nodes, so NameNode and DataNode are started with
>    `hdfs --daemon start namenode|datanode` (not `start-dfs.sh`), `HADOOP_CONF_DIR=<run>/conf`, and
>    `hdfs namenode -format -nonInteractive`.
> 3. **Gateway and portmapper:** there is no `jsvc` for the privileged secure starter, so the gateway is started as `$USER`
>    with `hdfs --daemon start nfs3` (`nfs.port.monitoring.disabled` left at its default). If it cannot register with the
>    system `rpcbind`, the system `rpcbind` is stopped for the run (nothing else on the node is registered with it), the
>    Hadoop `portmap` is started as root, and `rpcbind` is restarted at teardown.
> 4. **Mount:** `vers=3,proto=tcp,nolock,noacl,sync,wsize=65536,soft,timeo=600,retrans=2` on `<run>/mnt` (`soft` only so a
>    stalled gateway cannot leave an unkillable client; 60 s per try is far above any dump time).
> 5. **Request size and order** are read from the `OpenFileCtx` DEBUG lines (`requested offset=… and current offset=…` and
>    `Update nonSequentialWriteInMemory by 65536 …`), which carry the same information as the `WRITE … offset … count`
>    lines named in B3d.

**B3f. Predictions.** In-memory at hold = (4095 mod (M / 64 KiB)) × 64 KiB:

| Arm | In memory at hold | Dump file at hold | Max counted (log) | `[B` delta at hold |
|---|---|---|---|---|
| 1 MiB | 983,040 B | 267,386,880 B | 1,048,576 | < ~5 MiB, within noise |
| 8 MiB | 8,323,072 B | 260,046,848 B | 8,388,608 | ≈ +8 MiB |
| 64 MiB | 67,043,328 B | 201,326,592 B | 67,108,864 | ≈ +64 MiB |
| `Long.MAX_VALUE` | 268,369,920 B | no file | 268,369,920 | ≈ +256 MiB |
| sequential, stock | ~0 | no file | 0 | ~0 |

Further predictions:
- `WriteCtx` count at hold is about 4095 in all out-of-order arms. Their entries stay; only `data` is nulled.
- In the capped arms the dump file grows in steps of exactly M.
- After the hole is written, the md5 matches in all arms. Data is read back from the dump file.
- The dump file stays until the stream times out (about 10 min) or the gateway restarts.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| `[B` delta and `268,369,920 − dumpsize` follow the table and scale with M; dump grows in steps of M | Claim confirmed: the constant governs real gateway heap per file |
| Capped arm with in-memory ≥ M at hold, or `[B` delta ≈ +256 MiB | Claim wrong: the cap does not bind in a real gateway |
| `Long.MAX_VALUE` arm keeps everything in heap, while the stock arm spills to disk | Positive control moved; the difference is due to the constant |
| `Long.MAX_VALUE` arm also shows a dump file or a small `[B` delta | Not confirmed: the workload is not reaching the gateway out of order (check the WRITE log) |
| Debug log shows request sizes ≠ 65536 or non-ascending offsets | Workload not as designed; recompute predictions with the logged sizes before judging |
| md5 mismatch | Separate correctness defect; note it, it does not decide B1 |

**B3h. Controls.**
- The `Long.MAX_VALUE` arm (no cap) and the sequential arm use the same file size, mount and gateway.
- Baseline histograms are taken before each arm.
- A full GC is forced by `class_histogram`, so garbage does not count as held data.
- Dump size is an exact, independent measure of what left the heap.
- The gateway is restarted between arms, which clears the dump directory and the old contexts.
- One writer and a sync mount give one connection with serial RPCs, so concurrent overshoot is excluded.

**B4. Risks and cleanup.**
- Disk: each out-of-order arm writes about 256 MiB to `/mydata/<run>/nfs-dump` and about 256 MiB to HDFS (`/mydata/<run>/dn`). Keep `nfs.dump.dir` off `/tmp` and off shared storage.
- A hung writer, which is possible if the dump fails (A3), blocks the mount. Use `umount -f -l` if needed.
- Ports: 9000, 9866/9867/9864 and 9870 (HDFS), 2049, 4242 and 111. Do not stop the system `rpcbind` or a kernel NFS server on a shared host. Use other ports instead.
- Memory: the gateway has `-Xmx1g`. The no-cap arm needs about 300 MiB of heap.
- Cleanup:
  1. `sudo umount /mydata/<run>/mnt`
  2. `sudo -E hdfs --daemon stop nfs3`
  3. `sudo hdfs --daemon stop portmap`, if it was started.
  4. `stop-dfs.sh`
  5. Check with `jps` and `sudo jps` that no NameNode, DataNode or Nfs3 process is left. Also check that no `Portmap` process is left.
  6. Restore the jar.
  7. `rm -rf /mydata/<run>/{nfs-dump,dn,nn,tmp,logs,pids,mnt}`.
- Unit tier: the test writes its dump files under `target/test-dir` and deletes them in `cleanup()`. Delete the source copy when done.

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/WriteCtx.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/WriteManager.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/RpcProgramNfs3.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtxCache.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/Nfs3Utils.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/Nfs3Metrics.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/AsyncDataService.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/conf/NfsConfigKeys.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3/TestWrites.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/pom.xml
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/nfs3/request/WRITE3Request.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/nfs3/Nfs3FileAttributes.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/nfs3/Nfs3Base.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/oncrpc/XDR.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/oncrpc/SimpleTcpServer.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
- hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/HdfsNfsGateway.md
- hadoop-assemblies/src/main/resources/assemblies/hadoop-hdfs-nfs-dist.xml
- https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/HdfsNfsGateway.html (same content as the markdown above)
- https://issues.apache.org/jira/browse/HDFS-7259 (cited from the code comment)

## D. Stage-4 feedback

- **2026-11-25, run 1 on `pc72` (results: `results/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-2--autonomous.md`; frozen
  version sha256 `3b8bfc582ed4982800f2973b95be0f8ecdd81af31cb33f4eee56ed6e2f976e5a`, after the three dated amendments above).**
  - **Unit: Confirmed — caps** (B2g row 1). For M = 256 KiB / 1 MiB / 4 MiB the counter after every write was exactly (k mod q)·r,
    the dump file grew only in steps of M (final 16,515,072 / 15,728,640 / 12,582,912 B), the in-call peak was exactly M, and
    counted bytes equalled the referenced payload bytes; the dump-disabled control grew linearly to 16,711,680 B. Bypass probe:
    write 16 blocked as A3 inferred; afterwards a second writer added 16 uncapped writes (counter 2 MiB, 2× the mark), so a dump
    failure both stalls the waiting writer and removes the cap for that file (bypass recorded, source inference of A3 confirmed).
  - **Cluster: Confirmed — caps** (B3g rows 1 and 3). Real gateway, 256 MiB out-of-order file: in-memory at hold 983,040 /
    8,323,072 / 67,043,328 B and dump file 267,386,880 / 260,046,848 / 201,326,592 B for M = 1 / 8 / 64 MiB, exactly B3f;
    `[B` delta +0.45 / +7.8 / +66.4 MB; every dump round went from M to 0; `Long.MAX_VALUE` kept all 268,369,920 B in heap
    (+267.7 MB `[B`, no dump file); sequential control counted nothing. md5 matched in all arms.
  - **Outcome class: true positive.** No change to A or B1. Recommendation for stage 3 (not applied): at 1 s sampling the per-step
    dump growth cannot be seen for small M; name the dumper's `Start dump. Before dump … == M` / `After dump … == 0` DEBUG lines as
    the step evidence.
