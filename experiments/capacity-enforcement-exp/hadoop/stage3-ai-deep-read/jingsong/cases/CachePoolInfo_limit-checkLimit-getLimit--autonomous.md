# CachePoolInfo_limit — verification solution  <!-- file: cases/CachePoolInfo_limit-checkLimit-getLimit--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`CacheManager.java:462`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/CacheManager.java#L462), `if (pool.getBytesNeeded() + stats.getBytesNeeded() > pool.getLimit())` in `CacheManager.checkLimit` (row unit) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive`. The cache-pool `limit` (bytes, set with `hdfs cacheadmin -addPool/-modifyPool -limit`) bounds the replica-weighted bytes that the NameNode asks DataNodes to `mmap`+`mlock` for directives in that pool: the line-462 check rejects directives that would exceed it at admission. The CacheReplicationMonitor rescan check (`CacheReplicationMonitor.java:403`) also stops scheduling caching once the pool's running total passes the limit, which covers `-force`, a lowered limit and files that appear later. The bound works per pool, cluster-wide, a whole file at a time. Per cached replica, the DataNode can overshoot it by at most one OS page of rounding. |
| Ground | — |

Name parts: constraint `CachePoolInfo_limit` (the field `limit` that first carries the value along the setting path. The bare name `limit` is ambiguous, so it is qualified with its class). Function `checkLimit` (the method that encloses the given if). Operand `getLimit` (written `pool.getLimit()` at the check). The check that bounds actual memory at runtime is a second if, [`CacheReplicationMonitor.java:403`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/CacheReplicationMonitor.java#L403) in `rescanFile`. It uses the same operand and is covered by this solution.

## A. Constraint trace

**A1. The constraint.**
- **Name:** the cache-pool limit, set with `-limit <bytes>` on `hdfs cacheadmin -addPool` / `-modifyPool`, or with `CachePoolInfo.setLimit(Long)` through `DistributedFileSystem.addCachePool/modifyCachePool`. It is a per-pool attribute, not a `*-site.xml` key.
- **Kind:** a value an administrator sets at runtime, per object. It is held in a declared field and defaults to a constant.
- **First declaration:** the field `Long limit` in [`CachePoolInfo.java:71`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/CachePoolInfo.java#L71), the client-side request object, `@Nullable`, set by `setLimit` at `CachePoolInfo.java:137-140`. On the NameNode the value is copied into [`CachePool.limit` at `CachePool.java:71`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/CachePool.java#L71). That copy happens in `createFromInfoAndDefaults` (`CachePool.java:127-128`) on add and in `setLimit` (`CachePool.java:202-205`, called from `CacheManager.java:876-882`) on modify. `pool.getLimit()` (`CachePool.java:198-200`) returns it.
- **Unit and default:** bytes (a `long`). The default is `CachePoolInfo.DEFAULT_LIMIT = LIMIT_UNLIMITED = Long.MAX_VALUE` (`CachePoolInfo.java:54-55`), applied when no `-limit` is given (`CachePool.java:127-128`). No `*-default.xml` entry exists, so nothing conflicts with the default. `-limit unlimited` maps to `Long.MAX_VALUE` (`AdminHelper.java:114-124`). A negative value is rejected (`CachePoolInfo.java:221-222`).
- **How set:** with `hdfs cacheadmin -addPool <name> -limit <bytes>` (`CacheAdmin.java:620-623`) or `hdfs cacheadmin -modifyPool <name> -limit <bytes>` (`CacheAdmin.java:704-748`). Only the superuser can change it. The change takes effect at once, with no daemon restart: the modify path calls `setNeedsRescan()` (`CacheManager.java:880-881`). The value is persisted in the edit log (`FSNDNCacheOp.java:89-90`) and the fsimage (`CacheManager.java:1104-1105`, `1174`).
- **Reader:** the NameNode (`CacheManager`, `CacheReplicationMonitor`). DataNodes never see it. They act on the per-block cache and uncache commands the NameNode derives from it.
- **Related keys** (not this constraint, but they bound the same memory): `dfs.datanode.max.locked.memory` (`DFSConfigKeys.java:155-156`, `hdfs-default.xml:2985`, default 0, which disables caching), `dfs.namenode.path.based.cache.refresh.interval.ms` (`DFSConfigKeys.java:503-505`, default 30000) and `dfs.cachereport.intervalMsec` (`DFSConfigKeys.java:1090`).

**A2. What it caps.** It caps DataNode memory used for HDFS centralized caching: block replica files that are `mmap`ed and `mlock`ed off-heap in the DataNode process. The pmem variant is out of scope here. The cap is an aggregate over all directives in one pool and all DataNodes. The quantity compared is the pool's `bytesNeeded`: for each file covered by a directive, file length × the directive's cache replication (`CacheManager.java:475-508`, `CacheReplicationMonitor.java:395-397`). A directory directive counts only its direct child files (`CacheManager.java:494-503`, `CacheReplicationMonitor.java:365-373`). The pool also reports `bytesCached` (replicas actually reported cached, `CacheReplicationMonitor.java:440-442`) and `bytesOverlimit = max(bytesNeeded - limit, 0)` (`CachePool.java:280-282`).

**A3. Mechanism.**
1. **Admission (the given if).** `addDirective` (`CacheManager.java:574-601`) calls `checkLimit(pool, path, replication)` at `CacheManager.java:587-588`, unless `CacheFlag.FORCE` is set (`-force`, `CacheAdmin.java:168,198`). `modifyDirective` does the same, but only when the directive moves to a different pool (`CacheManager.java:681-686`). Inside `checkLimit` (`CacheManager.java:456-469`):
   - `computeNeeded` (`CacheManager.java:475-509`) returns `computeFileSize() × replication` for the path. A non-existent path gives 0 (`CacheManager.java:481-489`).
   - An unlimited pool returns early (`CacheManager.java:459-461`).
   - [`CacheManager.java:462`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/CacheManager.java#L462): if `pool.getBytesNeeded() + stats.getBytesNeeded() > pool.getLimit()`, it throws `InvalidRequestException("Caching path ... would exceed pool <name>'s remaining capacity of <limit - needed> bytes.")` (`CacheManager.java:463-467`). The directive is not created and nothing is logged to the edit log. Exactly equal to the limit is accepted (strict `>`).
   - Otherwise `addInternal` (`CacheManager.java:543-556`) adds the directive's needed bytes to the pool (`CacheDirective.addBytesNeeded`, `protocol/CacheDirective.java:179-182`) and requests a rescan.
2. **Runtime scheduling (the rescan).** The CacheReplicationMonitor runs every `dfs.namenode.path.based.cache.refresh.interval.ms`, or on `setNeedsRescan`. Each run resets all pool and directive statistics (`CacheReplicationMonitor.java:306,315-322`) and walks every directive in ID order (`CacheReplicationMonitor.java:341-381`). For each file, `rescanFile` first adds `computeFileSizeNotIncludingLastUcBlock() × replication` to `bytesNeeded` (`CacheReplicationMonitor.java:393-397`). Then, at [`CacheReplicationMonitor.java:403`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/CacheReplicationMonitor.java#L403), if `pool.getBytesNeeded() > pool.getLimit()` it returns without marking the file's blocks (`:403-412`). Blocks that are not marked in this scan get replication 0 ("no longer needed", `CacheReplicationMonitor.java:494-505`), so they are uncached or never cached. Because `bytesNeeded` only grows during a scan, the file that crosses the limit and every later file in the pool are skipped, even small ones. The bytes of files that are admitted therefore sum to at most `limit`.
3. **DataNode side.** For each marked block, the NameNode sends cache commands to DataNodes (`rescanCachedBlockMap`, `CacheReplicationMonitor.java:515ff`). The DataNode reserves `roundUp(blockLength, osPageSize)` bytes against `dfs.datanode.max.locked.memory` (`CacheStats.java:94-106`, `FsDatasetCache.java:415-424`), then mmaps and mlocks the replica.
4. **Bypasses and overshoots:**
   - `-force` skips line 462, but the rescan still holds the pool to the limit, so the directive is accepted but only partly cached.
   - Lowering the limit with `-modifyPool` does not re-check existing directives. The next rescan uncaches past the limit (this is the existing assertion `TestCacheDirectives.java:1288-1295`).
   - A directive on a missing path or an empty directory passes line 462 with 0 bytes. Files created there later are bounded only by the rescan check.
   - Edit-log replay (`addDirectiveFromEditLog`, `CacheManager.java:562-572`) skips the check by design.
   - Overshoot: the DataNode rounds each replica up to the page size (CacheStats line above), so locked bytes can exceed `bytesNeeded` by less than one page per cached replica.
   - Line 462 counts the under-construction last block (`computeFileSize`) but the rescan does not. The admission check is therefore more conservative than the runtime check.
   - Two directives in the same pool on the same file count it twice but cache it once, which makes the cap conservative.

**A4. Other consumers.**
- The same DataNode locked memory is used by directives in other pools, including unlimited ones. A block covered by directives in two pools counts against both pools but is cached once.
- `dfs.datanode.max.locked.memory` is a per-DataNode cap, shared with Lazy Persist (RAM_DISK) writes (`CentralizedCacheManagement.md:226`).
- If `dfs.datanode.pmem.cache.dirs` is set, the cache lives on persistent memory instead of DRAM.
- Outside both limits: client short-circuit mmaps, the OS page cache, and the DataNode and NameNode heaps (NameNode heap holds the CachedBlock map).

**A5. Evidence beyond the source.**
- `hadoop-hdfs/src/site/markdown/CentralizedCacheManagement.md:75` ("Pools can enforce a maximum *limit*, which restricts the number of bytes that can be cached in aggregate by directives in the pool"), `:100` (`-force` "Skips checking of cache pool resource limits"), `:150`, `:204` (mlock needs native `libhadoop.so`) and `:266-270` (RLIMIT_MEMLOCK). Published at https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/CentralizedCacheManagement.html
- The existing test `TestCacheDirectives#testLimit` (`hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestCacheDirectives.java:1247-1319`) covers rejection, raise, lower-then-uncache and `-force`, using pool stats only. It does not check DataNode cache usage.
- HDFS-4949 (centralized cache management umbrella), https://issues.apache.org/jira/browse/HDFS-4949. Not relied on for any claim above.

## B. Verification solution

**B1. Claim under test.** Take a cache pool with limit `L` bytes. (a) An `addDirective` without `-force` whose replica-weighted size would bring the pool's `bytesNeeded` above `L` is rejected at `CacheManager.java:462`, and one that lands exactly on `L` is accepted. (b) Whatever the admission path (`-force`, a lowered limit, files appearing later under a directive), the DataNode cache memory attributed to the pool settles at or below `L`, plus less than one page per cached replica, while the same workload in an unlimited pool settles at its full size. The claim is wrong if cache usage settles above `L` plus page rounding, or if an over-limit add is accepted without `-force`.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 8 and Maven 3.3+. Copy the tree to local disk: `rsync -a ~/hadoop-3.4.2/ /mydata/<run>/hadoop-src/`. Build there with `mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
- Add a test class `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestO34CachePoolLimit.java` in that copy only. Model it on `TestCacheDirectives` and reuse its setup pattern (`TestCacheDirectives.java:114-160`):
  - In a static block and in `@Before`, call `NativeIO.POSIX.setCacheManipulator(new NoMlockCacheManipulator())`. Without native code, the DataNode then still mmaps and accounts cache usage, but skips `mlock` (`NativeIO.java:311`).
  - Run `MiniDFSCluster` with 3 DataNodes.
- JVM: the surefire defaults are enough.
- Run with `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestO34CachePoolLimit`.

**B2b. Knobs.**
- Configuration on the `HdfsConfiguration`:
  - `dfs.blocksize=65536` (page-aligned, so DataNode rounding adds 0).
  - `dfs.namenode.fs-limits.min-block-size=0` (already set in `src/test/resources/hdfs-site.xml:30`. Set it in code too.)
  - `dfs.datanode.max.locked.memory=1048576` per DataNode (16 blocks; with 3 DataNodes this is far above every `L` below, so the DataNode cap never binds in the main runs).
  - `dfs.heartbeat.interval=1`, `dfs.cachereport.intervalMsec=1000`, `dfs.namenode.path.based.cache.refresh.interval.ms=1000`.
- Pool limit `L`, set with `CachePoolInfo.setLimit` through `dfs.addCachePool`/`modifyCachePool`. With B = 65536:
  - `L = 4B = 262144`: the exact boundary.
  - `L = 4B-1 = 262143`: one byte short.
  - `L = 4B+1 = 262145`: one byte over.
  - `L = unlimited`: the control.
  - Lowered to `2B = 131072` in phase C.
- The `CacheFlag.FORCE` flag: off, then on.
- Directive replication: 1 (main runs), or 3 (phase E).

**B2c. Workload.**
- Create 10 files `/o34/f01..f10`, each exactly one block (65536 bytes), file replication 3 (`DFSTestUtil.createFile(dfs, path, 65536, (short)3, seed)`). Total 10B = 655360 bytes.
- Phase A: add one directive per file (pool `p34`, replication 1, no flag) in order f01..f10, stopping at the first `InvalidRequestException`. With `L = 4B`, the needed total after k adds is kB, so add 5 would make 5B > 4B.
- Phase B: add the remaining files with `EnumSet.of(CacheFlag.FORCE)`. The pool now needs 10B against `L`.
- Phase C: `modifyCachePool(L = 2B)`.
- Phase D: in a fresh pool `p34d` with `L = 4B`, add a directive on the empty directory `/o34/grow` (needed 0, so it passes line 462). Then create 10 one-block files inside it.
- Phase E: pool `p34r` with `L = 2B`, and a directive with replication 3 on f01. Needed is 3B > 2B, so it is rejected. With `L = 3B` it is accepted and 3 replicas are cached.

**B2d. Observables and instruments.**
- Pool statistics from `dfs.listCachePools()` → `CachePoolEntry.getStats()`: `getBytesNeeded`, `getBytesCached`, `getBytesOverlimit`, `getFilesNeeded`, `getFilesCached`.
- Accept or reject result of each add, and the exception message.
- DataNode-side reserved cache: the sum over `cluster.getDataNodes()` of `dn.getFSDataset().getCacheUsed()` and `getNumBlocksCached()` (`FSDatasetMBean.java:104-114`).
- NameNode view: `cluster.getNamesystem().getCacheUsed()`.
- Poll every 500 ms until values are stable for 3 consecutive refresh intervals (wait up to 60 s, the way `waitForCachePoolStats` does at `TestCacheDirectives.java:843ff`). Log every sample.
- Not observable here: real mlocked pages (mlock is stubbed). The cluster tier covers them.

**B2e. Procedure.**
1. `@Before`: build the cluster as in B2a/B2b and `waitActive()`. Create the files.
2. For each `L` in {4B-1, 4B, 4B+1, unlimited}, in a fresh cluster or after removing all directives and pools (do this between runs; `TestCacheDirectives.java:162-169` shows how):
   1. Run phase A and record how many adds were accepted and the first rejection message.
   2. Wait for stable stats and record `bytesNeeded`, `bytesCached` and the summed DataNode `getCacheUsed`.
   3. Run phase B and record the same after stabilising.
3. Starting from the `L = 4B` state at the end of phase B, run phase C and record the same.
4. Run phases D and E in fresh pools and record the same.
5. `@After`: remove all directives, wait for `NumBlocksCached = 0` on every DataNode, and shut the cluster down.

**B2f. Predictions.** With B = 65536:

| Run | Accepted without force | bytesNeeded | bytesCached = Σ DN cacheUsed |
|---|---|---|---|
| A, L=4B-1 | 3 (4th rejected: "would exceed pool p34's remaining capacity of 65535 bytes") | 3B = 196608 | 196608 |
| A, L=4B | 4 (5th rejected, remaining capacity 0) | 4B = 262144 | 262144 |
| A, L=4B+1 | 4 (5th rejected, remaining capacity 1) | 262144 | 262144 |
| A, unlimited | 10 | 10B = 655360 | 655360 |
| B (force), L=4B | 10 | 655360, bytesOverlimit = 393216 | 262144 (f01..f04, the lowest directive IDs) |
| C, L lowered to 2B | — | 655360, overlimit 524288 | 131072 (f01..f02) |
| D, dir directive, L=4B | 1 (needed 0 at add) | 655360 after rescan | 262144 |
| E, repl 3, L=2B / 3B | rejected / accepted | — / 196608 | — / 196608 (one replica on each of 3 DataNodes) |

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Accepted counts and messages as in B2f; bytesCached and Σ DN cacheUsed equal the table | Claim confirmed at the operand level |
| L=4B accepts only 3 (equality rejected) or L=4B-1 accepts 4 | Boundary differs from `>` at line 462: claim (a) wrong |
| Phase A without force accepts more than floor(L/B) | Admission check not enforced: claim (a) wrong |
| Phase B/C/D: Σ DN cacheUsed settles above L | Runtime enforcement (`CacheReplicationMonitor.java:403`) does not bound usage: claim (b) wrong |
| Unlimited control does not reach 655360 | The workload or DataNode capacity is limiting. Result not conclusive; check `dfs.datanode.max.locked.memory` and DataNode logs for "could not reserve" |
| Phase C stays at 262144 after 60 s | Uncaching after a lowered limit failed. Claim (b) wrong for that path |

**B2h. Controls.**
- The unlimited pool on the same files and cluster shows that the workload can drive cache usage to 10B.
- `dfs.datanode.max.locked.memory` (3 × 1 MiB) is far above every `L`, so the DataNode cap is not what binds.
- Positive control for a known cap: an extra run with an unlimited pool and `dfs.datanode.max.locked.memory=131072` per DataNode must settle at ≤ 3 × 131072 cached with failed reservations logged. This shows the instruments respond to a binding cap.
- Page-aligned block size removes rounding as an explanation.
- Directive IDs are monotonic, which makes "which files are cached" predictable (f01..fk).

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux host, pseudo-distributed: 1 NameNode and 1 DataNode (plus SecondaryNameNode if `start-dfs.sh` starts it; it is not needed). Cache replication is 1, file replication 1.
- **Native code is required.** The DataNode refuses to start with `max.locked.memory > 0` unless it can mlock (`DataNode.java:1892-1897`). Build the distribution with native code from a local copy:
  - Install the packages listed at `BUILDING.txt:64`: `build-essential cmake zlib1g-dev pkg-config libssl-dev ...`.
  - Run `mvn package -Pdist,native -DskipTests -Dtar -Dmaven.javadoc.skip=true` in `/mydata/<run>/hadoop-src`.
  - Unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `/mydata/<run>/hadoop`.
  - Check that `bin/hadoop checknative` shows `hadoop: true`.
- **RLIMIT_MEMLOCK** must be ≥ `dfs.datanode.max.locked.memory`, or the DataNode aborts (`DataNode.java:1902-1910`). Before starting HDFS, raise it on the launching shell, for example with `sudo prlimit --pid $$ --memlock=unlimited:unlimited`, then check `ulimit -l`. Start the daemons from that shell so they inherit the limit.
- `etc/hadoop/hadoop-env.sh`:
  - `export JAVA_HOME=<jdk8>`
  - `export HADOOP_HEAPSIZE_MAX=1g`
  - `export HADOOP_LOG_DIR=/mydata/<run>/logs`
  - `export HADOOP_PID_DIR=/mydata/<run>/pids`
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=/mydata/<run>/tmp`.
- `hdfs-site.xml`:
  - `dfs.replication=1`
  - `dfs.namenode.name.dir=/mydata/<run>/nn`
  - `dfs.datanode.data.dir=/mydata/<run>/dn`
  - `dfs.blocksize=16777216`
  - `dfs.datanode.max.locked.memory=536870912` (512 MiB)
  - `dfs.namenode.path.based.cache.refresh.interval.ms=3000`
  - `dfs.cachereport.intervalMsec=3000`
- Host needs: at least 4 GiB free RAM (512 MiB locked + 2 heaps) and at least 2 GiB free local disk on `/mydata`.

**B3b. Knobs.**
- Pool limit `L` (with B = 16 MiB = 16777216), set with `hdfs cacheadmin -addPool p34 -limit <L>` or `-modifyPool p34 -limit <L>`. No restart is needed.
  - `L = 67108864` (4B)
  - `L = 67108863` (4B-1)
  - `L = unlimited` (control)
  - Lowered to `33554432` (2B)
- `-force`: off, then on.
- For the positive control only, restart the DataNode with `dfs.datanode.max.locked.memory=67108864`.

**B3c. Workload.**
- Create 16 files of exactly 16 MiB each:
  `for i in $(seq -w 1 16); do head -c 16777216 /dev/urandom > /mydata/<run>/f.bin; hdfs dfs -put -f /mydata/<run>/f.bin /o34/f$i; done`. Total 256 MiB = 16B, half of the DataNode's locked-memory cap, so the DataNode cap does not bind and 4B is well below the workload.
- The phases mirror the unit tier:
  - A: `hdfs cacheadmin -addDirective -path /o34/fNN -pool p34 -replication 1` for NN=01..16, until one fails.
  - B: the rest with `-force`.
  - C: `-modifyPool p34 -limit 33554432`.
  - D: a new pool `p34d -limit 67108864`, a directive on the empty `/o34/grow`, then put 16 files into it.
- Each phase lasts until stable: about 30 s (3 refresh plus report intervals), capped at 120 s.

**B3d. Observables and instruments.**
- **Actual resource:** `VmLck` in `/proc/<DN pid>/status`, in kB of mlocked memory in the DataNode process. The DataNode pid comes from `jps | awk '/ DataNode$/{print $1}'`. Sample it every 2 s with timestamps into a CSV. Supporting reading: `grep Mlocked /proc/meminfo`, which is host-wide and noisy, so use deltas only.
- **DataNode view:** `curl -s 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=FSDatasetState*'` → `CacheUsed`, `CacheCapacity`, `NumBlocksCached`, `NumBlocksFailedToCache`.
- **NameNode view:** `hdfs cacheadmin -listPools -stats` (BYTES_NEEDED, BYTES_CACHED, BYTES_OVERLIMIT, FILES_*), `hdfs cacheadmin -listDirectives -stats -pool p34`, and `hdfs dfsadmin -report` ("Cache Used").
- Exit status and stderr of each `-addDirective`.
- Not observable: which pool a locked page "belongs" to. Attribution comes from using one pool at a time on a fresh DataNode cache (Σ VmLck delta equals that pool's caching).

**B3e. Procedure.**
1. Prepare the host:
   1. Raise memlock on the shell.
   2. Run `hdfs namenode -format -nonInteractive`, then `start-dfs.sh`.
   3. Confirm with `jps` and `hdfs dfsadmin -report`: Cache Capacity is 512 MiB and VmLck of the DataNode is about 0 kB.
2. Write the 16 files (B3c).
3. Run pool `p34` with `L = 4B-1`: phase A, record, then remove the pool (`hdfs cacheadmin -removePool p34`, which also removes its directives) and wait until VmLck is back to baseline.
4. Run pool `p34` with `L = 4B`: phase A and record, phase B and record, phase C and record. Then remove the pool and wait for baseline.
5. Run phase D in pool `p34d`, then remove it.
6. Control: pool `p34u` with `-limit unlimited`, add all 16 directives, record, remove.
7. Positive control: `hdfs --daemon stop datanode`, set `dfs.datanode.max.locked.memory=67108864`, `hdfs --daemon start datanode` (from the memlock-raised shell). Repeat step 6 and record.
8. Clean up: `hdfs cacheadmin -removePool` for every pool, `stop-dfs.sh`, `jps` shows no Hadoop process, then `rm -rf /mydata/<run>/{nn,dn,tmp}`.

**B3f. Predictions.** Baseline VmLck is b (expected about 0 kB). With B = 16384 kB:
- L = 4B-1: 3 directives accepted. The 4th fails with "would exceed pool p34's remaining capacity of 16777215 bytes". BYTES_CACHED = 50331648, VmLck = b + 49152 kB.
- L = 4B, phase A: 4 accepted, the 5th fails (remaining capacity 0). BYTES_CACHED = 67108864, VmLck = b + 65536 kB.
- Phase B (`-force`): BYTES_NEEDED = 268435456, BYTES_OVERLIMIT = 201326592, BYTES_CACHED stays 67108864, VmLck stays b + 65536 kB.
- Phase C: BYTES_CACHED goes to 33554432 and VmLck to b + 32768 kB within about 2 refresh intervals. No client mmaps are held, so the revocation timeout (`dfs.datanode.cache.revocation.timeout.ms`, `DFSConfigKeys.java:475-476`) does not delay this.
- Phase D: BYTES_CACHED = 67108864, VmLck = b + 65536 kB.
- Unlimited control: BYTES_CACHED = 268435456, VmLck = b + 262144 kB.
- Positive control (DN cap 64 MiB, unlimited pool): VmLck plateaus at b + 65536 kB with `NumBlocksFailedToCache` > 0.
- Tolerance on VmLck: ±1 page per cached block plus b drift. With 16 MiB page-aligned blocks the rounding is 0.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| VmLck deltas and BYTES_CACHED match B3f in every phase | Pool limit governs real locked memory: claim confirmed |
| Phase A accepts more than floor(L/B) directives without `-force` | Line 462 not enforced: claim (a) wrong |
| Phase B/C/D VmLck delta settles above L/1024 kB + page rounding | Usage not bounded by the limit: claim (b) wrong |
| BYTES_CACHED ≤ L but VmLck delta > L | NameNode accounting and real usage diverge (for example rounding or leaked mmaps): claim (b) wrong for actual memory |
| Unlimited control stays below 256 MiB | Workload, ulimit or DataNode cap limiting; run not conclusive |
| Positive control does not plateau at 64 MiB | Instrument (VmLck) does not track caching; run not conclusive |

**B3h. Controls.**
- The unlimited pool on the identical files and daemon shows the workload can lock 256 MiB.
- The DataNode-cap positive control shows VmLck responds to a known binding cap.
- Baseline VmLck is taken before each phase, and each pool is removed with a return to baseline in between, so earlier phases cannot carry over.
- File replication 1 and a single DataNode make replica count unambiguous.
- `dfs.datanode.max.locked.memory` (512 MiB) is above every `L`, so the DataNode cap is not what binds in the main runs.

**B4. Risks and cleanup.**
- **Memory:** at most 512 MiB locked plus 2 × 1 GiB heap. Check `free -g` first.
- **Locked memory stays resident while cached:** always remove pools before stopping, and stop the DataNode at the end. Locked pages are released when the process exits.
- **memlock:** raising it needs sudo. Raise only on the launching shell (`prlimit --pid $$`) and never edit `/etc/security/limits.conf` on a shared host.
- **Disk:** about 300 MiB of HDFS data plus logs, all under `/mydata/<run>`. Nothing goes on shared storage.
- **Ports:** 9000, 9870, 9864, 9866, 9867 and 9868 must be free. Check with `ss -ltn` and change them in `hdfs-site.xml` if taken.
- **Unit tier:** MiniDFSCluster uses `target/test/data` inside the local copy. Delete `/mydata/<run>/hadoop-src/hadoop-hdfs-project/hadoop-hdfs/target/test` afterwards. No daemons persist after the JVM exits; check with `jps`.
- **Cluster tier:** `stop-dfs.sh`, then `jps` shows no NameNode, DataNode or SecondaryNameNode. Then `rm -rf /mydata/<run>/{nn,dn,tmp,pids}`.
- Build only in the local copy, never in the shared tree.

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/CacheManager.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/CachePool.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/protocol/CacheDirective.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/CachePoolInfo.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/CacheReplicationMonitor.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSNDNCacheOp.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/tools/CacheAdmin.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/tools/AdminHelper.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataNode.java (1885-1912)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/CacheStats.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetCache.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/MemoryMappableBlockLoader.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/metrics/FSDatasetMBean.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml (dfs.datanode.max.locked.memory)
- hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/CentralizedCacheManagement.md
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestCacheDirectives.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/resources/hdfs-site.xml
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/nativeio/NativeIO.java (NoMlockCacheManipulator)
- BUILDING.txt
- https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/CentralizedCacheManagement.html (same content as the .md above)

## D. Stage-4 feedback

none yet
