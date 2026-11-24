# nfs.max.open.files — verification solution  <!-- file: cases/nfs.max.open.files-put-maxStreams--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`OpenFileCtxCache.java:124`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtxCache.java#L124) — `if (size() == this.maxStreams) {` in `OpenFileCtxCache.put` (unit kind: row) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive` — `nfs.max.open.files` is a hard cap on the number of cached write streams (`OpenFileCtx`) the NFS gateway holds at once. Each one holds an HDFS `DFSOutputStream` (two threads and a packet queue) and up to about 1 MiB of buffered out-of-order write data. So the gateway heap these streams hold grows with min(open files, cap). The cap limits the number of streams, not bytes per stream: it bounds memory only through that count, and it does not bound the size of each stream's dump file. |
| Ground | — |

Name parts: constraint `nfs.max.open.files`; function `put` (encloses the given if; it is also the main
enforcement point); operand `maxStreams` (written `this.maxStreams` at the check).

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3).

## A. Constraint trace

**A1. The constraint.**
- Name: `nfs.max.open.files` (exact key). Deprecated alias `dfs.nfs3.max.open.files`, mapped by a
  `DeprecationDelta` at `hadoop-hdfs-nfs/.../conf/NfsConfiguration.java:54-55`.
- Kind: configuration key (int).
- First declared: [`NfsConfigKeys.java:41`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/conf/NfsConfigKeys.java#L41-L42)
  (`DFS_NFS_MAX_OPEN_FILES_KEY = "nfs.max.open.files"`; `DFS_NFS_MAX_OPEN_FILES_DEFAULT = 256` on line 42).
- `*-default.xml` entry: **none**. The key is missing from `hdfs-default.xml`, which has other
  `nfs.*` keys such as `nfs.rtmax` at line 2292 and `nfs.dump.dir` at line 2281. It is also not
  mentioned in `HdfsNfsGateway.md`. The only default is the Java constant, 256.
- Unit: a count of open write streams (one per file being written through the gateway), not bytes.
- How it is set: `hdfs-site.xml` (or `core-site.xml`) on the NFS gateway host, read into an
  `NfsConfiguration` when the gateway process starts. The value is read once, in the
  `OpenFileCtxCache` constructor (`OpenFileCtxCache.java:52-55`), and logged as
  `Maximum open streams is <n>`. `WriteManager.java:98-100` reads and logs it again but uses it
  for nothing else. There is no refresh command, so a change needs a restart of the `nfs3` daemon.
  The NameNode and DataNodes do not read it.
- Reader: the NFS gateway (`hdfs nfs3`, class `org.apache.hadoop.hdfs.nfs.nfs3.Nfs3`).
- Related values that are not this key: `nfs.stream.timeout` (`NfsConfigKeys.java:44-45`,
  10 min) controls idle-stream reaping. The hard-coded `DFS_NFS_STREAM_TIMEOUT_MIN_DEFAULT = 10 s`
  (`NfsConfigKeys.java:46`) is the minimum idle time before a stream can be evicted. The
  hard-coded `DUMP_WRITE_WATER_MARK = 1 MiB` (`OpenFileCtx.java:73`) is the per-stream in-memory
  out-of-order buffer threshold.

**A2. What it caps.** It caps the number of `OpenFileCtx` entries in the gateway's
`OpenFileCtxCache.openFileMap` (`OpenFileCtxCache.java:45-46`). The check compares
`size()` (= `openFileMap.size()`, line 190-192) with `maxStreams`. The memory resource behind each
entry is gateway heap plus thread stacks:
- an `HdfsDataOutputStream` / `DFSOutputStream` opened with `create` or `append`. Each has a
  `DataStreamer` thread (`DataStreamer.java:664,680`), a `ResponseProcessor` thread once a block
  pipeline exists (`DataStreamer.java:1172`), and a packet queue of up to
  `dfs.client.write.max-packets-in-flight` = 80 packets (`HdfsClientConfigKeys.java:408-409`,
  enforced at `DataStreamer.java:1010-1011`).
- `pendingWrites` (`OpenFileCtx.java:123`): `WriteCtx` objects that each hold a full copy of the
  write payload (`WRITE3Request.deserialize` copies the bytes, `WRITE3Request.java:41`,
  `XDR.java:138-143`). Out-of-order data stays in memory up to about 1 MiB
  (`OpenFileCtx.java:278-294`); beyond that it is dumped to `nfs.dump.dir/<fileId>` on local disk
  (`OpenFileCtx.java:308-316`).
- at most one dump file on local disk (`WriteManager.java:182-185`).

So the key bounds how many of these per-stream bundles exist at once. It does not bound bytes inside
a stream.

**A3. Mechanism.**
1. A WRITE to a file with no cached stream goes to `WriteManager.handleWrite`
   (`RpcProgramNfs3.java:898`, `WriteManager.java:140-141`). It opens an HDFS append stream
   (`WriteManager.java:153-154`), builds an `OpenFileCtx` (`WriteManager.java:184-185`) and calls
   `addOpenFileStream` → `OpenFileCtxCache.put` (`WriteManager.java:81-82,187`). A CREATE opens a
   stream with `dfsClient.create` (`RpcProgramNfs3.java:993-994`) and calls the same `put`
   (`RpcProgramNfs3.java:1013-1017`).
2. `put` (`OpenFileCtxCache.java:118-145`), inside `synchronized(this)`: asserts
   `size() <= maxStreams` (line 121-123), then runs the check
   [`if (size() == this.maxStreams)`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtxCache.java#L124).
3. When the cap is reached, `getEntryToEvict` (lines 69-116) picks the victim:
   - an inactive ctx, if there is one (line 81-86);
   - otherwise, among ctxs with no pending writes or commits (`hasPendingWork`,
     `OpenFileCtx.java:206-208`; skipped at line 87-90), the idlest one. It is returned only if it
     has been idle for at least 10 s (line 104-114). Otherwise the result is `null`.
4. If the result is `null`, `put` returns `false` (line 126-127) and the new stream is not cached:
   - WRITE path: the new append stream is closed and the client gets `NFS3ERR_JUKEBOX`, meaning
     retry later (`WriteManager.java:187-200`). The write data is dropped.
   - CREATE path: the stream is closed and the file stays created; later writes go through the
     append path (`RpcProgramNfs3.java:1017-1021`).
5. If a victim is found, it is removed from the map (line 132) and `cleanup()`ed outside the lock
   (line 141-143). `cleanup` closes the `DFSOutputStream`, fails any pending writes and deletes the
   dump file (`OpenFileCtx.java:1218-1275`). The new ctx is then inserted (line 137).
6. Independently, `StreamMonitor` (lines 239-271) scans every 5 s and removes ctxs idle longer than
   `nfs.stream.timeout` (`scan`, lines 148-184).

Bypass and overshoot paths:
- Transient: the HDFS stream (create or append) is opened *before* `put` (`WriteManager.java:153`,
  `RpcProgramNfs3.java:993`). So up to `maxStreams` + (number of concurrent opening RPCs) output
  streams exist for a moment before the extra ones are closed.
- Eviction cleanup runs outside the lock, so an evicted stream's memory is freed shortly after the
  new one is inserted.
- The cap does not bound bytes per stream. In-order data waits for the write-back task, and
  out-of-order data is about 1 MiB in memory per stream plus an unbounded dump file per stream.
- `maxStreams = 0`: every `put` fails (the map is empty, so `getEntryToEvict` returns `null`), and
  every write is answered `JUKEBOX`. A negative value fails the `checkState` at line 121 with
  `IllegalStateException`.
- Reads do not use this cache. Read streams live in `DFSClientCache`'s input-stream cache.

**A4. Other consumers.** Other things use the same gateway heap and disk outside this key's control:
- the `DFSClientCache` client and input-stream caches;
- Netty RPC buffers;
- the `AsyncDataService` write-back thread pool;
- per-stream dump files under `nfs.dump.dir` (default `/tmp/.hdfs-nfs`), whose size is limited only
  by how much out-of-order data a client sends;
- each `DFSOutputStream`'s packet queue (`dfs.client.write.max-packets-in-flight`);
- `nfs.rtmax`/`nfs.wtmax`, which bound a single request's size;
- NameNode leases: one per open stream.

**A5. Evidence beyond the source.**
- `hadoop-hdfs/src/site/markdown/HdfsNfsGateway.md:121-136` describes the out-of-order dump to
  `nfs.dump.dir` and the roughly 1 MB in-memory threshold. It does not mention `nfs.max.open.files`.
- Existing test `TestOpenFileCtxCache#testEviction`
  (`hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3/TestOpenFileCtxCache.java:39-96`)
  sets the key to 2 and asserts that `put` fails at the cap and that the size stays at 2. It uses
  mocked streams and measures no memory.
- HDFS-4763 (portmap; cited in the gateway docs):
  https://issues.apache.org/jira/browse/HDFS-4763 — only relevant to starting the gateway.

## B. Verification solution

**B1. Claim under test.** With `nfs.max.open.files = K` and a client that opens M > K files at
once, each holding out-of-order (pending) data:
- the gateway never holds more than K `OpenFileCtx` write streams;
- the extra opens are refused with `NFS3ERR_JUKEBOX`;
- the gateway heap held by write streams grows with min(K, M) (about 1 stream's buffered data per
  held stream), not with M.

### B2. Unit tier

**B2a. Environment and build.**
- Use a local copy of the tree at `rel/release-3.4.2`, outside any shared directory, for example
  `rsync -a <source>/ /mydata/<run>/hadoop-src/`. Use JDK 8 and Maven 3.3+.
- Build the module and its dependencies:
  `cd /mydata/<run>/hadoop-src && mvn -pl hadoop-hdfs-project/hadoop-hdfs-nfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
- New test class
  `hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3/TestMaxOpenFilesMemory.java`.
  Use package `org.apache.hadoop.hdfs.nfs.nfs3` so the package-private `getWriteManager()`,
  `getOpenFileCtxCache()`, `create(...)`, `write(...)` and `getPendingWritesForTest()` are
  visible. Copy the setup from `TestWrites#testWriteStableHow` (`TestWrites.java:460-500`):
  - set the proxy-user keys for the current user to `*`;
  - start `MiniDFSCluster` with 1 DataNode;
  - set `nfs3.mountd.port`/`nfs3.server.port` = 0;
  - `new Nfs3(config).startServiceInternal(false)` (no portmap);
  - use a mocked `SecurityHandler` returning the current user.
- Use the surefire JVM options from the module (`-Xmx` as configured by the build). Add
  `-DargLine="-Xmx1g"` if needed.

**B2b. Knobs.** `config.setInt(NfsConfigKeys.DFS_NFS_MAX_OPEN_FILES_KEY, K)` for K ∈ {8, 32, 128},
set before `new Nfs3(config)`, one test method (fresh MiniDFSCluster) per value. M = 64 files in
every run:
- K = 8 and K = 32 are below M, so the cap binds.
- K = 128 is above M, so the cap does not bind. This is the positive control showing that the
  workload itself moves memory when no cap applies.

Also set `nfs.dump.dir` to a fresh temp dir under `target/` and keep `nfs.stream.timeout` at its
600000 ms default, so the idle reaper cannot remove streams during the run.

**B2c. Workload.**
1. Get the root handle: `new FileHandle(client.getFileInfo("/").getFileId(), Nfs3Utils.getNamenodeId(config))`.
2. Phase 1: issue M `CREATE3Request(rootHandle, "f"+i, CREATE_UNCHECKED, new SetAttr3(), 0)`
   through `nfsd.create(...)` back to back, within a few seconds (well under the 10 s eviction
   threshold).
3. Phase 2: for each of the M handles, issue one `WRITE3Request(handle, offset = 1048576,
   count = 983040, UNSTABLE, ByteBuffer.wrap(new byte[983040]))` through
   `nfsd.write(xdr, null, xid, securityHandler, addr)`. Drop the test's reference to each byte array
   after sending.
4. Each write starts at 1 MiB in an empty file. It is out of order (offset > nextOffset = 0), so
   it is buffered as `ALLOW_DUMP` (`OpenFileCtx.java:562-573`). 983040 B is below the 1 MiB water
   mark, so it stays in heap and the stream keeps pending work. Such a stream can never be evicted.

Arithmetic:
- The first min(K, M) creates are cached.
- The remaining creates find every cached stream idle for less than 10 s, so `put` fails.
- In phase 2, writes to the cached files become pending (~0.94 MiB each). Writes to the other files
  open an append stream, fail `put` because every cached stream has pending work, and are rejected.
- Expected held data: K = 8 → 7.5 MiB; K = 32 → 30 MiB; K = 128 → 64 × 0.9375 = 60 MiB.

**B2d. Observables and instruments.**
- (a) The check's operand: `cache.size()` (`nfsd.getWriteManager().getOpenFileCtxCache()`), read
  after every create and write. Record the maximum.
- (b) Count of handles h with `cache.get(h) != null` after phase 2.
- (c) Pending bytes: the sum over cached ctxs of
  `getPendingWritesForTest().values()` → `WriteCtx.getCount()`.
- (d) Live HDFS output streams: count `Thread.getAllStackTraces().keySet()` whose name starts with
  `"DataStreamer for file /.reserved/.inodes/"`.
- (e) Heap used after GC: call `System.gc()` three times with 200 ms sleeps, then
  `ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed()`. Take this baseline just
  before phase 2 and again after phase 2 plus 2 s.
- (f) Files in the dump dir, which should be 0.

The JUKEBOX status is not visible with a `null` channel (`Nfs3Utils.java:140-145`). Infer the
rejection from (b) instead, and from log lines `Can't add new stream` / `Can't add more stream`
(count them with a log4j appender or by grepping surefire output).

**B2e. Procedure.**
1. Create the test with three methods `testK8`, `testK32`, `testK128` sharing a helper `run(K)`
   that does B2c and prints `K, maxSize, cachedCount, pendingBytes, streamerThreads, heapDelta,
   dumpFiles`.
2. Run `mvn -pl hadoop-hdfs-project/hadoop-hdfs-nfs test -Dtest=TestMaxOpenFilesMemory -DargLine="-Xmx1g"`.
3. Collect the printed lines from
   `hadoop-hdfs-project/hadoop-hdfs-nfs/target/surefire-reports/*TestMaxOpenFilesMemory-output.txt`.
4. In `finally`: `nfs3.stop()`, `cluster.shutdown()`.

**B2f. Predictions.**

| K | max `size()` | cached after phase 2 | pending bytes | DataStreamer threads | heap delta | dump files |
|---|---|---|---|---|---|---|
| 8 | 8 | 8 | 8 × 983040 = 7 864 320 | 8 | ≈ 7.5 MiB (6–12 MiB) | 0 |
| 32 | 32 | 32 | 31 457 280 | 32 | ≈ 30 MiB (25–40 MiB) | 0 |
| 128 | 64 | 64 | 62 914 560 | 64 | ≈ 60 MiB (50–75 MiB) | 0 |

Heap delta should be roughly linear in min(K, M), with a slope of about 1 MiB per held stream, and
`size()` should never exceed K.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| max `size()` = min(K, M); pending bytes and heap delta scale with min(K, M); K = 128 shows ~8× the K = 8 delta | Claim confirmed: the key caps the number of held streams, and so their buffered memory |
| `size()` > K at any point, or cached count > K | Claim refuted: the cap does not hold |
| K = 8 heap delta ≈ K = 128 heap delta (both ≈ 60 MiB) while `size()` ≤ 8 | Refuted for memory: memory is held outside the cached ctxs (for example rejected write data retained elsewhere) |
| K = 128 delta not clearly above K = 8 delta | Not confirmed: the workload did not move memory (check that the writes reached `pendingWrites` and that dump files = 0) |
| dump files > 0 | Workload crossed the water mark; data went to disk, so the heap reading is not valid. Reduce the count |
| cached count < min(K, M) | Streams were reaped or evicted; check the timing (creates must take < 10 s) and `nfs.stream.timeout` |

**B2h. Controls.**
- K = 128 (> M) is the no-cap positive control.
- A null-workload run with K = 8 and count = 1 byte separates per-stream overhead from payload.
- A fresh MiniDFSCluster per K keeps runs independent.
- The baseline heap is measured inside the same JVM just before phase 2, so MiniDFSCluster memory
  cancels out.
- The dump-file count = 0 check confirms the data is in heap.
- Thread count (d) confirms that the `DFSOutputStream`s, not only the ctx objects, are bounded.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux host with JDK 8 and ≥ 4 GB free RAM, pseudo-distributed. Build the distribution from
  the local copy: `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`, then unpack
  `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `/mydata/<run>/hadoop` (`HADOOP_HOME`).
- Use `HADOOP_CONF_DIR=/mydata/<run>/conf`, `HADOOP_LOG_DIR=/mydata/<run>/logs` and
  `HADOOP_PID_DIR=/mydata/<run>/pids`.
- `core-site.xml`:
  - `fs.defaultFS=hdfs://localhost:9000`
  - `hadoop.tmp.dir=/mydata/<run>/tmp`
  - `hadoop.proxyuser.<runuser>.hosts=*`
  - `hadoop.proxyuser.<runuser>.groups=*`
- `hdfs-site.xml`:
  - `dfs.replication=1`
  - `dfs.namenode.name.dir=/mydata/<run>/nn`
  - `dfs.datanode.data.dir=/mydata/<run>/dn`
  - `nfs.dump.dir=/mydata/<run>/nfsdump`
  - `nfs.max.open.files=<K>`
  - `nfs.stream.timeout=600000`
  - `nfs.exports.allowed.hosts=* rw` (this is also the default)
- `hadoop-env.sh`: `export HDFS_NFS3_OPTS="-Xms1g -Xmx1g"`. This keeps the heap size fixed so
  after-GC numbers are comparable.
- Daemons: NameNode, DataNode, NFS gateway. The gateway must register with a portmapper on UDP/TCP
  111 at start (`Nfs3Base.java:52-59`, `RpcProgram.java:44,147`), otherwise it exits.
  - Option A (sudo available, no system rpcbind running): `sudo $HADOOP_HOME/bin/hdfs --daemon start portmap`.
  - Option B (system rpcbind running): start the gateway as root with
    `HDFS_NFS3_SECURE_USER=<runuser>` (`HdfsNfsGateway.md:229`).
  - Option C (no root): run the gateway class from the distribution's jars without registration
    using a 5-line launcher
    `public static void main(String[] a) throws Exception { new Nfs3(new NfsConfiguration()).startServiceInternal(false); }`
    (`Nfs3.java:55-58`, public). Compile it against `$(hadoop classpath)` and run it with
    `hadoop --config $HADOOP_CONF_DIR <LauncherClass>` and `HADOOP_OPTS="-Xms1g -Xmx1g"`. Our load
    client talks to TCP 2049 directly and needs no portmapper.
  - Record which option was used.
- Load client `NfsStreamLoad.java`, built against `$(hadoop classpath)`. It is a blocking
  `java.net.Socket` to `localhost:2049` and uses the hadoop-nfs classes as in
  `TestOutOfOrderWrite.java:68-86`:
  - Each call: `RpcCall.getInstance(xid, Nfs3Constant.PROGRAM, Nfs3Constant.VERSION, proc, cred, new VerifierNone()).write(xdr)`.
    `cred` is a `CredentialsSys` with the run user's uid/gid. `CredentialsNone` is not accepted:
    `RpcProgramNfs3.java:2145-2152`.
  - Serialize the request, send `XDR.writeMessageTcp(xdr, true)` bytes, read a 4-byte record mark
    plus the reply, then `RpcReply.read`, then the status int.
  - For CREATE replies, read the `handle_follows` boolean and `FileHandle.deserialize`
    (as at `TestOutOfOrderWrite.java:121-125`).
  - Root handle: `new FileHandle(16385 /* INodeId.ROOT_INODE_ID */, Nfs3Utils.getNamenodeId(conf))`.
  - Arguments: `M chunkBytes offset`.
  - Prints per-file `create_status write_status`. `NFS3_OK=0`, `NFS3ERR_JUKEBOX=10008`.

**B3b. Knobs.** `nfs.max.open.files` K ∈ {8, 32, 128} in `hdfs-site.xml`, with a gateway restart
for each value (only the gateway; NN and DN stay up). Confirm the value in the gateway log line
`Maximum open streams is K`. M = 64 files, chunk 983040 B at offset 1048576 in all runs. K = 128 is
the no-cap control.

**B3c. Workload.**
1. Run `java -cp "$(hadoop classpath):loadclient.jar" NfsStreamLoad 64 983040 1048576`. Files are
   `/nfsload-<runid>-<i>`. It sends 64 CREATEs back to back (< 5 s), then 64 WRITEs, one per file.
2. Keep the client process alive (sleep 120 s) so the measurements happen while the streams are
   held. The gateway holds them in any case until `nfs.stream.timeout` (10 min).

The arithmetic matches B2c: the held payload is min(K, 64) × 983040 B, that is 7.5 / 30 / 60 MiB,
well inside the 1 GiB heap. There is no dump, because each payload is below the 1 MiB water mark.
Each run lasts about 3 min.

**B3d. Observables and instruments.** `PID=$(jps | awk '/Nfs3|Launcher/{print $1}')`.
- Client output: count of write status 0 vs 10008, and create status.
- Gateway log: `grep -c "Can't add new stream"` and `grep -c "Can't add more stream"` in
  `$HADOOP_LOG_DIR/*nfs3*.log` (or the launcher stdout).
- Live output streams: `jstack $PID | grep -c '"DataStreamer for file'`.
- Instance counts and payload:
  `jcmd $PID GC.class_histogram | grep -E ' org.apache.hadoop.hdfs.nfs.nfs3.(OpenFileCtx|WriteCtx)$| org.apache.hadoop.hdfs.DFSOutputStream$| \[B$'`.
  The histogram forces a full GC, so it shows live objects.
- Heap used after GC: `jcmd $PID GC.run; jcmd $PID GC.heap_info` (sum of "used"), or
  `jstat -gc $PID` (OU+EU+S0U+S1U).
- RSS: `grep VmRSS /proc/$PID/status`. This is secondary and noisy because of the fixed heap.
- Open HDFS files: `hdfs dfsadmin -listOpenFiles | grep -c nfsload-<runid>`.
- Dump dir: `ls /mydata/<run>/nfsdump | wc -l; du -sb /mydata/<run>/nfsdump`.
- Sampling: a baseline before the client starts, after 2 GCs. Then 3 samples at +15 s, +45 s and
  +90 s after the client finishes sending.

The `openFileMap.size()` operand cannot be read directly in the cluster tier. The
`OpenFileCtx` instance count from the histogram and the DataStreamer thread count stand in for it.

**B3e. Procedure.**
1. Format and start: `hdfs namenode -format -nonInteractive`, `hdfs --daemon start namenode`,
   `hdfs --daemon start datanode`. Wait for `hdfs dfsadmin -report` to show 1 live DN.
2. Set K = 8 in `hdfs-site.xml` and start the gateway (Option A, B or C). Check
   `Maximum open streams is 8`.
3. Take the baseline per B3d.
4. Start `NfsStreamLoad` in the background and wait for it to finish sending (it prints `SENT`).
5. Take the three samples per B3d and save the client output.
6. Stop the client and stop the gateway (`hdfs --daemon stop nfs3`, or kill the launcher). Remove the
   files with `hdfs dfs -rm -skipTrash '/nfsload-<runid>-*'`.
7. Repeat steps 2-6 for K = 32 and K = 128, each with a new `<runid>`.
8. Optional: repeat K = 8 with chunk = 1 B (overhead-only control).
9. Clean up per B4.

**B3f. Predictions.**

| K | OpenFileCtx instances | DataStreamer threads | write OK / JUKEBOX | listOpenFiles | heap-after-GC delta vs baseline | dump files |
|---|---|---|---|---|---|---|
| 8 | 8 | 8 | 8 / 56 | 8 | ≈ 7.5 MiB (6–12) | 0 |
| 32 | 32 | 32 | 32 / 32 | 32 | ≈ 30 MiB (25–40) | 0 |
| 128 | 64 | 64 | 64 / 0 | 64 | ≈ 60 MiB (50–75) | 0 |

The create statuses are all 0. The `Can't add more stream` count (from the create path) is
64 − min(K, 64). The `Can't add new stream` count equals the JUKEBOX count. The `[B` histogram
growth follows the heap delta. Heap delta is close to linear in min(K, 64).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Instances, threads and open files = min(K, 64); heap delta scales with min(K, 64); K = 128 delta ≈ 8× K = 8 delta | Claim confirmed in the real daemon |
| Any count > K at a sample, or JUKEBOX count < 64 − K | Claim refuted: the cap is not enforced |
| Counts ≤ K but the K = 8 heap delta ≈ the K = 128 delta | Refuted for memory: memory is held outside the cached streams |
| The K = 128 delta is not above the K = 8 delta (control did not move) | Not confirmed: the workload did not hold memory. Check write statuses and that the dump dir is empty |
| Dump files > 0 | Payload went to disk. Lower the chunk size and rerun |
| Counts below min(K, 64) at +15 s | Streams were reaped or evicted early; check the timing and `nfs.stream.timeout` |

**B3h. Controls.**
- The K = 128 run (cap not binding) is the positive control for the workload.
- The chunk = 1 B run separates per-stream overhead from payload.
- A fixed `-Xms=-Xmx` and after-GC readings remove heap-sizing noise.
- The NN and DN stay up across K values while only the gateway restarts, so each gateway starts
  fresh.
- The listOpenFiles count independently confirms how many HDFS streams the gateway holds.

**B4. Risks and cleanup.**
- Disk: all data and logs are under `/mydata/<run>/`, about 0.5 GB including the build, never on
  shared storage. HDFS data is about 64 MiB per run (rejected writes store nothing).
- Ports: 9000, 9864-9867, 9870, 2049, 4242, 50079, and 111 for Options A and B. Check them first
  with `ss -ltnu`. Option A and Option B touch the host's portmapper: do not use them if other
  users rely on rpcbind. Prefer Option C on a shared host.
- Do not mount NFS. This design needs no kernel mount.
- Cleanup:
  - Unit tier: the test's `finally` stops `Nfs3` and the MiniDFSCluster; check with `jps` that no
    surefire JVM is left.
  - Cluster tier: `hdfs --daemon stop nfs3` (or kill the launcher),
    `sudo hdfs --daemon stop portmap` (Option A), `hdfs --daemon stop datanode`,
    `hdfs --daemon stop namenode`. Check that `jps` shows no `NameNode`/`DataNode`/`Nfs3`/
    `Portmap`/launcher/`NfsStreamLoad`.
  - Then `rm -rf /mydata/<run>/{nn,dn,tmp,nfsdump,logs,pids}`.

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtxCache.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/conf/NfsConfigKeys.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/conf/NfsConfiguration.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/WriteManager.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/WriteCtx.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/RpcProgramNfs3.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/Nfs3Utils.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/Nfs3.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3/TestOpenFileCtxCache.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3/TestWrites.java
- hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/TestOutOfOrderWrite.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
- hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/HdfsNfsGateway.md
- hadoop-hdfs-project/hadoop-hdfs/src/main/bin/hdfs
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/INodeId.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/tools/DFSAdmin.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/HdfsClientConfigKeys.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DataStreamer.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DFSOutputStream.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/nfs3/Nfs3Base.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/oncrpc/RpcProgram.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/oncrpc/XDR.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/oncrpc/security/CredentialsSys.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/nfs3/request/WRITE3Request.java
- hadoop-common-project/hadoop-nfs/src/main/java/org/apache/hadoop/nfs/NfsExports.java
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/CommonConfigurationKeys.java
- hadoop-common-project/hadoop-common/src/main/conf/hadoop-env.sh
- https://issues.apache.org/jira/browse/HDFS-4763 (cited via HdfsNfsGateway.md; not fetched)

## D. Stage-4 feedback

none yet
