# CachePoolInfo_limit — verification solution  <!-- file: cases/CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`CacheReplicationMonitor.java:403`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/CacheReplicationMonitor.java#L403) — `if (pool.getBytesNeeded() > pool.getLimit())` in `CacheReplicationMonitor.rescanFile` (row unit; not a helper) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive` — the per-pool cache limit (set by `hdfs cacheadmin -addPool/-modifyPool -limit`) decides, at every NameNode cache rescan, which files of the pool's directives get their blocks scheduled for caching; files whose cumulative replicated size would exceed the limit are not cached (and are uncached if they were), so the DataNodes' mlocked off-heap cache memory attributable to the pool stays at or below the limit (up to page rounding). |
| Ground | — |

Name parts: constraint `CachePoolInfo_limit` (the per-pool field `CachePoolInfo.limit`; the bare name `limit` is ambiguous, so it is class-qualified); function `rescanFile` (encloses the given if; it is the rescan-time enforcement point, the add-time one is `CacheManager.checkLimit`); operand `pool.getLimit()` as written at the check, written `pool.getLimit` in the file name (call parentheses dropped).

## A. Constraint trace

**A1. The constraint.**
- **Name:** the cache pool *limit* — "the maximum aggregate number of bytes that can be cached by directives in this pool" (`CachePoolInfo.java:129-132` Javadoc). Not a configuration key: it is a per-pool attribute stored in NameNode metadata.
- **Kind:** runtime, admin-set per-object attribute (the Java default is a constant).
- **First declared:** [`CachePoolInfo.java:71`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/CachePoolInfo.java#L71) (`@Nullable Long limit;`), the client/RPC-side description of a pool. The NameNode copy is `CachePool.limit` (`hadoop-hdfs/.../server/namenode/CachePool.java:71`), filled from the info at `CachePool.java:127-128` (`info.getLimit() == null ? CachePoolInfo.DEFAULT_LIMIT : info.getLimit()`) and changed by `CachePool.setLimit` (`CachePool.java:202-203`) from `CacheManager.modifyPool` (`CacheManager.java:876-881`). No `*-default.xml` entry.
- **Unit:** bytes (replicated bytes: file length × directive replication, see A2).
- **Default:** `CachePoolInfo.DEFAULT_LIMIT = LIMIT_UNLIMITED = Long.MAX_VALUE` (`CachePoolInfo.java:54-55`), i.e. no limit. Only one source, nothing to reconcile.
- **How set:** `hdfs cacheadmin -addPool <name> -limit <bytes|unlimited>` or `hdfs cacheadmin -modifyPool <name> -limit <bytes|unlimited>` (`CacheAdmin.java:620-621`, `704-705`; parsing in `AdminHelper.parseLimitString`, `AdminHelper.java:114-124`: `unlimited` → `Long.MAX_VALUE`, else `Long.parseLong`), or the Java API `DistributedFileSystem.addCachePool/modifyCachePool(new CachePoolInfo(name).setLimit(bytes))`. Negative values are rejected (`CachePoolInfo.validate`, `CachePoolInfo.java:221-223`, called at `CacheManager.java:821,851`). No restart: a modify takes effect immediately and triggers a rescan (`setNeedsRescan()` at `CacheManager.java:881`). The value is persisted in the edit log / fsimage with the pool.
- **Who reads it:** the active NameNode — `CacheManager.checkLimit` (add/modify-directive time) and the `CacheReplicationMonitor` thread (every rescan). Related settings that shape the outcome but are not this constraint: `dfs.namenode.caching.enabled` (default `true`, `hdfs-default.xml:2932-2933`), `dfs.namenode.path.based.cache.refresh.interval.ms` (rescan period, default 30000, `hdfs-default.xml:3039-3040`), `dfs.datanode.max.locked.memory` (per-DataNode cache capacity, default 0 = caching off, `hdfs-default.xml:2985-2986`), `dfs.cachereport.intervalMsec` (default 10000, `hdfs-default.xml:3083-3084`).

**A2. What it caps.** Memory: the DataNodes' HDFS centralized cache — block replicas `mmap`ed and `mlock`ed into DataNode off-heap memory (`FsDatasetCache.CachingTask.run`, `FsDatasetCache.java:409-430`). The pool limit is an aggregate, cluster-wide cap on the cache bytes scheduled for the directives of one pool (summed over all DataNodes and cached replicas). The quantity compared against the limit is `pool.getBytesNeeded()`: the running sum, during the current rescan, of `file.computeFileSizeNotIncludingLastUcBlock() × directive.getReplication()` over every file of every directive of that pool scanned so far, **including the current file** (`CacheReplicationMonitor.java:395-397`, `CacheDirective.java:179-181` forwards to `CachePool.addBytesNeeded`, `CachePool.java:256-257`; reset to 0 at the start of every rescan by `resetStatistics`, `CacheReplicationMonitor.java:315-322`, `CachePool.java:250`).

**A3. Mechanism.**
1. Admin sets the limit on the pool (A1). On `-modifyPool -limit` the NameNode calls `setNeedsRescan()` (`CacheManager.java:881`).
2. Add-time check (first gate, bypassable): `CacheManager.addDirective` calls `checkLimit(pool, path, replication)` unless `-force` / `CacheFlag.FORCE` is given (`CacheManager.java:587-589`; same for a pool move in `modifyDirective`, `CacheManager.java:682-686`). `checkLimit` (`CacheManager.java:456-469`) returns at once for an unlimited pool and otherwise throws `InvalidRequestException("... would exceed pool ...'s remaining capacity ...")` if `pool.getBytesNeeded() + computeNeeded(path).bytesNeeded > pool.getLimit()`. It uses the pool's bytesNeeded from the last rescan and the path's size *now*; it does not see files added to a directory later.
3. Rescan (the enforcement that decides what is actually cached): the `CacheReplicationMonitor` thread rescans every `intervalMs` or when woken (`CacheReplicationMonitor.java:181-186`). `rescan()` resets statistics, then `rescanCacheDirectives()` iterates directives in ID order (`CacheManager.directivesById` is a `TreeMap`, `CacheManager.java:137,337`); a directory directive visits its direct child files in name order (`CacheReplicationMonitor.java:364-372`; children are kept sorted, `INodeDirectory.java:204-205`).
4. For each file, `rescanFile` (`CacheReplicationMonitor.java:389`) adds `size × replication` to the directive's and the pool's bytesNeeded (`:395-397`) and then checks
   [`if (pool.getBytesNeeded() > pool.getLimit())`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/CacheReplicationMonitor.java#L403).
   - **True (limit exceeded):** log at debug and `return` (`:404-411`) — none of the file's blocks is put into (or re-marked in) `cachedBlocks`.
   - **False:** every COMPLETE block of the file gets a `CachedBlock` with the directive's replication and the current scan's `mark` (`:413-456`).
5. `rescanCachedBlockMap()` (`:515`) then, per `CachedBlock`: a block not re-marked in this scan is "no longer needed by any directives" and gets replication 0 (`:499-505`, used at `:572-578`); if cached replicas exceed what is needed it schedules uncaching (`addNewPendingUncached`, `:610-614`), if fewer it schedules caching on DataNodes with enough remaining cache (`addNewPendingCached`, `:616-620`; per-DN capacity pruning at `:517-537`). DataNodes receive DNA_CACHE / DNA_UNCACHE commands on heartbeat and mlock / munmap the replicas.
- **Outcome when the limit is reached:** the first file whose cumulative demand crosses the limit is not cached, and — because bytesNeeded only grows during a scan — **every later file of every later directive in the same pool is also skipped**, even a file small enough to fit in the remaining room. Already-cached blocks of skipped files are uncached at the next rescan. Equality is allowed (`>` not `>=`): demand exactly equal to the limit is cached.
- **Bypasses / overshoots:**
  - `-force` skips only the add-time check; the rescan check still applies (so `-force` does not raise cache usage above the limit, it only lets the directive exist with BYTES_OVERLIMIT > 0).
  - Lag: after the limit is lowered (or files appended), cache usage stays above the new limit until the next rescan plus the next DataNode heartbeat(s) execute the uncache; uncaching can be further delayed while clients hold the replica's mmap (anchor) (comment at `CacheReplicationMonitor.java:487-492`).
  - Page rounding: the DataNode reserves `length` rounded up to the OS page size per cached replica (`FsDatasetCache.java:388-389`, `CacheStats.java:209-210`), so real locked memory can exceed the pool's logical bytes by < 1 page per replica.
  - Accounting is pessimistic, not optimistic: bytesNeeded counts `size × requested replication` even when fewer DataNodes can hold a replica, and counts the last under-construction block's absence (`INodeFile.java:969-971`) — both keep actual usage ≤ limit.
  - The same block named by directives in two pools is counted in both pools but cached once; a block reached by a pool with room is cached regardless of another pool's limit (each pool's limit governs only its own directives' scheduling).

**A4. Other consumers.** Of the same DataNode locked memory: directives in other pools (each pool has its own limit; the sum of pool limits is not checked against cluster cache capacity — the docs only say they "normally ... approximately equal", `CentralizedCacheManagement.md:75`); Lazy Persist (RAM_DISK) writes, which reserve from the same DataNode cache budget (`FsDatasetImpl.java:3770-3778`, `CentralizedCacheManagement.md:226`); the per-DataNode cap `dfs.datanode.max.locked.memory` (`FsDatasetCache` reserve fails above capacity, `FsDatasetCache.java:415-422`); client zero-copy reads' mmaps of cached replicas. Outside HDFS caching: the DataNode JVM heap and OS page cache are not governed by this limit.

**A5. Evidence beyond the source.** `hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/CentralizedCacheManagement.md:75` (pools "enforce a maximum *limit*, which restricts the number of bytes that can be cached in aggregate by directives in the pool"), `:100` (`-force` "Skips checking of cache pool resource limits"), `:140-165` (`-addPool/-modifyPool -limit`), `:222-226`, `:266-270` (`dfs.datanode.max.locked.memory`, `ulimit -l`). Existing test `TestCacheDirectives#testLimit` (`hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestCacheDirectives.java:1247-1319`): lowering the limit below a cached file's size drops BYTES_CACHED to 0 (`:1287-1293`), and FORCE bypasses the add-time check (`:1309-1318`).

## B. Verification solution

**B1. Claim under test.** For a cache pool with limit `L`, the bytes the HDFS centralized cache actually holds for that pool's directives (cached replica bytes on DataNodes, i.e. mlocked DataNode memory) never exceed `L` once the rescan has settled: files are admitted in directive-ID / file-name order while the cumulative `size × replication` stays ≤ `L`, everything after the first crossing is not cached, and lowering `L` on a live pool uncaches down to ≤ `L`. With `L = unlimited` the same workload is cached in full (up to the DataNode capacity).

### B2. Unit tier

**B2a. Environment and build.** Local copy of the tag (never the shared tree), JDK 8, Maven 3.3+. `cd <copy> && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`. New test class `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestPoolLimitRescanCap.java` (package `org.apache.hadoop.hdfs.server.namenode`), modelled on `TestCacheDirectives` (`:108-180`): static `NativeIO.POSIX.setCacheManipulator(new NoMlockCacheManipulator())` (so no native code / `ulimit -l` needed; the DataNode still reserves and accounts cache bytes), `MiniDFSCluster` with **1 DataNode**, `HdfsConfiguration` with `dfs.blocksize=4096` (`B`), `dfs.datanode.max.locked.memory=65536` (16 B), `dfs.heartbeat.interval=1`, `dfs.cachereport.intervalMsec=1000`, `dfs.namenode.path.based.cache.refresh.interval.ms=1000`, `dfs.replication=1` (test `hdfs-site.xml` already sets `dfs.namenode.fs-limits.min-block-size=0`). Run: `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestPoolLimitRescanCap` (surefire defaults; no extra JVM options). *[Amended 2026-11-24, stage-4 audit A1: node paths, no `install` step, surefire counts — see D1.]*

**B2b. Knobs.** Pool limit `L` (via `CachePoolInfo.setLimit` at `addCachePool`, or `modifyCachePool` for the live-lowering case), with `B = 4096`:
- `L ∈ {0, 2B=8192, 2.5B=10240, 4B=16384, 6B=24576, unlimited}` — 0 and unlimited are the ends; 2B / 4B / 6B hit exact equality (`>` vs `>=`); 2.5B is a non-multiple (must round down to 2 files).
- Live lowering: `unlimited → 3B=12288` on the same pool.
- Order case: `L = 3B` with mixed file sizes (B2c).
- Positive control (cap known to bind): pool `unlimited`, `dfs.datanode.max.locked.memory = 3B = 12288` (fresh cluster).

**B2c. Workload.** Create pool `p` with limit L; `mkdirs /d`; add directive `{pool=p, path=/d, replication=1}` **without FORCE** while `/d` is empty — `checkLimit` computes 0 needed, so `0 > L` is false and it is accepted for every L ≥ 0; this isolates the rescan check at `:403` from the add-time check. Then write `/d/f01 … /d/f06`, each exactly `B` bytes, replication 1 (`DFSTestUtil.createFile(dfs, path, B, (short)1, seed)`). Total demand 6B = 24576 ≤ DataNode capacity 16B, so only the pool limit can bind. Order case: separate pool `q` (L = 3B) on directory `/e` with `/e/a1` = 1B, `/e/a2` = 3B, `/e/a3` = 1B. Add-time contrast: also try `addCacheDirective` on the already-populated `/d` into a fresh pool with L=2B without FORCE (expect `InvalidRequestException` "remaining capacity") and with FORCE (expect success). *[Amended 2026-11-24, A3: the add-time contrast is its own test on a fresh cluster with only pool `r` — see D1.]*

**B2d. Observables and instruments.** After each change, poll every 500 ms for up to 60 s until two consecutive readings are equal (pattern of `waitForCachedBlocks`, `TestCacheDirectives.java:753-799`), then record:
- Operand: `CachePoolStats` from `dfs.listCachePools()` — `getBytesNeeded()` (the value compared at `:403`), `getBytesCached()`, `getBytesOverlimit()`, `getFilesNeeded()`, `getFilesCached()`; per-directive stats from `dfs.listCacheDirectives()`. *[Amended 2026-11-24, A2: steady-state rule and required disallow-branch evidence — see D1.]*
- NameNode view: count of `CachedBlock` with ≥ 1 `Type.CACHED` datanode in `namesystem.getCacheManager().getCachedBlocks()` (under `namesystem.readLock()`).
- DataNode accounting: `cluster.getDataNodes().get(0).getFSDataset().getCacheUsed()` and `.getNumBlocksCached()`.
- Not observable here: real locked memory (mlock is stubbed). Debug log of `CacheReplicationMonitor` ("not scanning file ... because bytesNeeded for pool ...") can be enabled with `GenericTestUtils.setLogLevel(CacheReplicationMonitor.LOG, Level.DEBUG)` to see which file tripped the check.

**B2e. Procedure.**
1. Copy the tree to local disk; add `TestPoolLimitRescanCap` with one `@Test` per knob value (fresh `MiniDFSCluster` per test, `@After` removes directives, waits for 0 cached, shuts down, restores the cache manipulator, as `TestCacheDirectives.teardown`).
2. Per L: build pool/directive/files as in B2c, wait for steady state, record B2d values, assert the predictions (B2f).
3. Live-lowering test: L unlimited → wait for 6 cached blocks → `modifyCachePool(new CachePoolInfo("p").setLimit(12288L))` → wait → record.
4. Order test (pool `q`).
5. Add-time contrast (no FORCE vs FORCE).
6. Positive control on a cluster with `max.locked.memory = 12288`, pool unlimited.
7. Build and run per B2a; keep surefire reports (`target/surefire-reports/`).

**B2f. Predictions.** (B = 4096; "cached" = steady state.)

| Case | BYTES_NEEDED | BYTES_CACHED | DN getCacheUsed | DN blocks cached | BYTES_OVERLIMIT |
|---|---|---|---|---|---|
| L = 0 | 24576 | 0 | 0 | 0 | 24576 |
| L = 8192 (2B) | 24576 | 8192 | 8192 | 2 (f01, f02) | 16384 |
| L = 10240 (2.5B) | 24576 | 8192 | 8192 | 2 | 14336 |
| L = 16384 (4B) | 24576 | 16384 | 16384 | 4 | 8192 |
| L = 24576 (6B) | 24576 | 24576 | 24576 | 6 | 0 |
| L = unlimited | 24576 | 24576 | 24576 | 6 | 0 |
| unlimited → 12288 | 24576 | 24576 → 12288 | 24576 → 12288 | 6 → 3 (f01–f03) | 0 → 12288 |
| order: q, L = 3B; a1=1B, a2=3B, a3=1B | 20480 | 4096 (a1 only) | 4096 | 1 | 8192 |
| control: pool unlimited, DN cap 12288 | 24576 | 12288 | 12288 | 3 | 0 |

Add-time contrast: without FORCE → `InvalidRequestException` containing "remaining capacity"; with FORCE → accepted, and the cached bytes for that pool still follow the L = 2B row. In every case `BYTES_CACHED ≤ L`.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Rows match B2f; BYTES_CACHED and DN cache used step with L and never exceed it | claim confirmed at the mechanism level |
| L = 2.5B caches 2 files, L = 2B caches 2, L = 6B caches 6 | the check is `>` on cumulative replicated bytes as traced |
| Order case caches a1 only (a3 skipped though it fits) | skip-after-first-crossing behaviour confirmed |
| Any case with BYTES_CACHED or DN cache used > L at steady state | **claim refuted**: the limit does not cap cached bytes |
| L = 0 or 2B caches all 6 files | **claim refuted** (rescan check not effective; e.g. the limit is not consulted) |
| Live lowering leaves 6 blocks cached for > 60 s | rescan does not enforce a lowered limit — **claim refuted** for that path |
| Unlimited case does not cache 6 blocks, or the DN-cap control does not stop at 3 | setup broken (caching not working / not observed); result **not confirmed**, fix and rerun |
| *(A7, 2026-11-24)* Every finite-L row ≤ L, but a row's file/block count differs from B2f (e.g. fewer files cached than predicted) | admission rule not as traced: **Not confirmed**; feedback to stage 3 |
| *(A7, 2026-11-24)* Counts match B2f but no "not scanning file" DEBUG line for a row with < 6 files cached | cut-off not shown to come from the check at `:403`: **Not confirmed** |

**B2h. Controls.** Unlimited pool with the same files shows the workload does cache (rules out "nothing ever gets cached"). The DN-cap control shows the instruments move where a known cap binds and that its cut-off differs in mechanism (DN reserve) from the pool cut-off. Directive added on an empty directory without FORCE rules out the add-time check as the cause of non-caching. Single DataNode and replication 1 remove replica placement as a variable; DN capacity (16B) > total demand (6B) rules out the DN cap as the binding limit in the L rows.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, pseudo-distributed: NameNode + one DataNode (no YARN needed). Distribution from the local copy: `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true` (`BUILDING.txt:364-368`). **Native code is required** here: a DataNode with `dfs.datanode.max.locked.memory > 0` refuses to start without native mlock support (`DataNode.java:1892-1898`). Either build with `-Pdist,native` (`BUILDING.txt:370-372`; needs CMake, zlib-devel, GCC per `BUILDING.txt:9-15`), or build only `hadoop-common` natively (`mvn -pl hadoop-common-project/hadoop-common package -Pnative -DskipTests`) and copy `libhadoop.so*` into `$HADOOP_HOME/lib/native/`. Verify with `hadoop checknative` (hadoop: true). *[Amended 2026-11-24, A4: native build on `pc75` and run paths — see D1.]* Run on JDK 8 or 11. `export HADOOP_HOME=<untarred dist>`, `RUN=<local-disk run dir of known size, e.g. under /mydata>`, `HADOOP_LOG_DIR=$RUN/logs`, `HADOOP_PID_DIR=$RUN/pid`, `HADOOP_HEAPSIZE_MAX=1g`.
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:8020`, `hadoop.tmp.dir=$RUN/tmp`.
- `hdfs-site.xml`: `dfs.replication=1`; `dfs.namenode.name.dir=$RUN/nn`; `dfs.datanode.data.dir=$RUN/dn`; `dfs.blocksize=1048576` (U = 1 MiB = the default `dfs.namenode.fs-limits.min-block-size`); `dfs.datanode.max.locked.memory=8388608` (8 MiB = 8U); `dfs.namenode.path.based.cache.refresh.interval.ms=2000`; `dfs.cachereport.intervalMsec=2000`; `dfs.heartbeat.interval=1`.
- `ulimit -l` of the shell starting the DataNode must be ≥ 8192 (KB) (`DataNode.java:1901-1911`; `CentralizedCacheManagement.md:266-270`). Linux 5.11+ defaults to 8 MiB; if lower, raise it (`/etc/security/limits.conf` memlock, or `sudo prlimit --memlock=unlimited --pid $$`), or use the scaled variant: `dfs.namenode.fs-limits.min-block-size=0`, U = `dfs.blocksize=8192`, `max.locked.memory=65536` (fits a 64 KB ulimit), same file counts.

**B3b. Knobs.** Pool limit `L` via `hdfs cacheadmin -addPool p -limit <bytes>` / `-modifyPool p -limit <bytes>` (no restart; takes effect at the next rescan, ≤ 2 s): `L ∈ {0, 2U=2097152, 2.5U=2621440, 4U=4194304, unlimited}`, plus live lowering `unlimited → 3U=3145728`. Positive control: pool `unlimited` with `dfs.datanode.max.locked.memory=3145728` (3U) — needs a DataNode restart (`hdfs --daemon stop datanode; hdfs --daemon start datanode`).

**B3c. Workload.** `hdfs dfs -mkdir /d`; `hdfs cacheadmin -addPool p -limit <L>`; `hdfs cacheadmin -addDirective -path /d -pool p -replication 1` (empty directory → add-time check passes for any L ≥ 0). Then six files of exactly 1 MiB: `for i in 01 02 03 04 05 06; do head -c 1048576 /dev/urandom > $RUN/f$i; hdfs dfs -D dfs.blocksize=1048576 -put $RUN/f$i /d/f$i; done`. Demand = 6 MiB ≤ DN cap 8 MiB, so only L can bind. Per knob value about 1 minute (settling ≤ ~10 s). Between knob values: `hdfs cacheadmin -removeDirectives -path /d`, `hdfs cacheadmin -removePool p`, wait until DN cache used = 0, then recreate the pool with the next L and re-add the directive (files stay). *[Amended 2026-11-24, A8: re-adding the directive on the populated `/d` would hit the add-time check for every finite L < 6U; the files are moved out and back instead — see D1.]*

**B3d. Observables and instruments.** Sample every 2 s for 60 s after each change; report the plateau (last 10 samples equal): *[Amended 2026-11-24, A6: plateau and VmLck baseline rules — see D1.]*
- **Actual resource:** `grep VmLck /proc/$DNPID/status` (kB locked by the DataNode; `DNPID=$(cat $HADOOP_PID_DIR/hadoop-$USER-datanode.pid)`), with a baseline taken before any directive exists.
- DataNode JMX: `curl -s 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=FSDatasetState*'` → `CacheUsed`, `CacheCapacity`, `NumBlocksCached`.
- `hdfs dfsadmin -report` → "Cache Used".
- Operand: `hdfs cacheadmin -listPools -stats p` (LIMIT, BYTES_NEEDED, BYTES_CACHED, BYTES_OVERLIMIT, FILES_NEEDED, FILES_CACHED) and `hdfs cacheadmin -listDirectives -stats -pool p`.
- Which file was skipped: NameNode log at DEBUG for `org.apache.hadoop.hdfs.server.blockmanagement.CacheReplicationMonitor` (`hadoop daemonlog -setlevel localhost:9870 org.apache.hadoop.hdfs.server.blockmanagement.CacheReplicationMonitor DEBUG`).
- Not directly observable: per-pool split of DN memory (only one pool is used, so DN totals equal the pool's share).

**B3e. Procedure.**
1. Build (B3a); untar the dist on local disk; write configs; check `ulimit -l` and `hadoop checknative`.
2. `hdfs namenode -format -nonInteractive`; `hdfs --daemon start namenode`; `hdfs --daemon start datanode`; `hdfs dfsadmin -report` shows Cache Capacity 8 MiB; record VmLck baseline.
3. Put the six files (B3c); `hdfs fsck /d -files -blocks` shows 6 blocks of 1048576.
4. For each L in B3b order (unlimited first as the positive control of the workload): create pool + directive, sample (B3d), record plateau, remove directive and pool, wait for CacheUsed = 0.
5. Live lowering: pool unlimited + directive → plateau at 6 MiB → `hdfs cacheadmin -modifyPool p -limit 3145728` → sample 60 s.
6. Add-time contrast: `hdfs cacheadmin -addPool r -limit 2097152; hdfs cacheadmin -addDirective -path /d -pool r` (expect error "remaining capacity"), then the same with `-force` (accepted; cached bytes for r follow the 2U row). Remove r. *[Amended 2026-11-24, A5: remove pool `p` and wait for CacheUsed = 0 before step 6 — see D1.]*
7. DN-cap control: set `dfs.datanode.max.locked.memory=3145728`, restart the DataNode, pool unlimited + directive, sample.
8. Cleanup (B4).

**B3f. Predictions.** (U = 1048576; VmLck in kB above baseline; page size 4 KiB divides U, so no rounding.)

| Case | BYTES_NEEDED | BYTES_CACHED = CacheUsed | NumBlocksCached | VmLck Δ (kB) |
|---|---|---|---|---|
| unlimited | 6291456 | 6291456 | 6 | 6144 |
| L = 0 | 6291456 | 0 | 0 | 0 |
| L = 2U | 6291456 | 2097152 | 2 | 2048 |
| L = 2.5U | 6291456 | 2097152 | 2 | 2048 |
| L = 4U | 6291456 | 4194304 | 4 | 4096 |
| unlimited → 3U | 6291456 | 6291456 → 3145728 within ~10 s | 6 → 3 | 6144 → 3072 |
| `-force` into L = 2U | 6291456 | 2097152 | 2 | 2048 |
| DN cap 3U, pool unlimited | 6291456 | 3145728 | 3 | 3072 |

Relation: steady-state VmLck Δ ≈ CacheUsed ≤ L for every finite L.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| CacheUsed and VmLck Δ follow B3f, ≤ L, stepping by 1 MiB with L | claim confirmed: the pool limit caps real locked memory |
| L = 2.5U gives 2 MiB, not 3 | whole-file admission confirmed |
| Live lowering drops VmLck to ~3072 kB | enforcement on a live pool confirmed |
| Steady CacheUsed or VmLck Δ > L for any finite L | **claim refuted** |
| L = 0 / 2U caches all 6 MiB | **claim refuted** (limit not enforced at rescan) |
| Unlimited case caches < 6 MiB, or DN-cap control does not stop at 3 MiB, or VmLck does not move while CacheUsed does | setup/instrument problem (ulimit, native, mlock stubbed); **not confirmed** — fix and rerun |
| CacheUsed matches but VmLck Δ is larger by a constant | other locked memory in the JVM; compare to baseline, not a refutation |
| *(A7, 2026-11-24)* Every finite-L row ≤ L but a count differs from B3f | **Not confirmed**; feedback to stage 3 |
| *(A7, 2026-11-24)* CacheUsed ≤ L but VmLck Δ − c > L + 24 kB at plateau (c = the constant offset of the L = 0 row) | counter capped but real memory not: **Refuted** |
| *(A7, 2026-11-24)* Counts match B3f but no "not scanning file" DEBUG line in the NameNode log for a row with < 6 files cached | **Not confirmed** |

**B3h. Controls.** Unlimited pool (same files) shows the workload fills the cache; DN-cap control shows VmLck/CacheUsed respond to a known binding cap; the empty-directory directive without `-force` separates the rescan check from the add-time check, and the `-force` step shows the add-time bypass does not lift the cap; single DataNode, replication 1 and DN capacity (8U) > demand (6U) keep the pool limit as the only binding cap in the L rows; files written with exact 1 MiB block size avoid partial blocks and page rounding.

**B4. Risks and cleanup.** Unit tier: MiniDFSCluster data under the module's `target/test/data` on local disk (small); `NoMlockCacheManipulator` avoids locking memory. Cluster tier: locks at most 8 MiB; disk ≈ 6 MiB of blocks plus logs under `$RUN`; ports 8020, 9870, 9864, 9866, 9867 must be free (check `ss -ltn` first; move them in `hdfs-site.xml` if taken). Raising `ulimit -l` affects only the starting shell if done with `prlimit`; revert any `limits.conf` change. Cleanup: `hdfs cacheadmin -removeDirectives -path /d; hdfs cacheadmin -removePool p`; `hdfs --daemon stop datanode; hdfs --daemon stop namenode`; `jps` shows no `NameNode`/`DataNode`; `rm -rf $RUN`.

## C. Sources read

hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/CacheReplicationMonitor.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/CachePool.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/CacheManager.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/protocol/CacheDirective.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/CachePoolInfo.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/tools/CacheAdmin.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/tools/AdminHelper.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/INodeDirectory.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/INodeFile.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataNode.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetCache.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/CacheStats.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetImpl.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/metrics/FSDatasetMBean.java
hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/CentralizedCacheManagement.md
hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestCacheDirectives.java
hadoop-hdfs-project/hadoop-hdfs/src/test/resources/hdfs-site.xml
BUILDING.txt

## D. Stage-4 feedback

### D1. Stage-4 design audit amendments (2026-11-24, before any harness run or reading)

Audit by the stage-4 agent (Jingsong's share, node `pc75`). sha256 of this file before the amendments:
`8bbbfa2b2651ff72d68ac0b12c4fb2e771ea2810943e828028075402bc64735a`. None changes B1's claim or any number in B2f / B3f.

- **A1 (B2a).** Node `pc75`; JDK 8 (`JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64`), Maven 3.6.3. Local copy
  `/mydata/jingsong-s4/CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous-run1/src` made with
  `hadoop/stage4-runtime-verification/jingsong/copy-source.sh`. No `install` step: the node's `~/.m2` holds the 3.4.2
  artifacts (incl. test-jars) from the base build; run `mvn -B -pl hadoop-hdfs-project/hadoop-hdfs test
  -Dtest=TestPoolLimitRescanCap -DfailIfNoTests=false`. Surefire failures do not fail `mvn test` in this build: read the
  surefire report counts, not the exit code. The test prints one machine-readable line per steady-state reading
  (`IFCHK,...`) to the surefire `-output.txt`.
- **A2 (B2d).** Steady state: poll every 500 ms; the reading is taken when the tuple (pool BYTES_NEEDED, BYTES_CACHED,
  BYTES_OVERLIMIT, FILES_NEEDED, FILES_CACHED, NN cached-block count, DN cacheUsed, DN numBlocksCached) has been unchanged
  for 10 consecutive polls (5 s) and at least 5 s after the change; at 60 s without that the reading is recorded as
  **not settled** (the row then cannot match). The `CacheReplicationMonitor` DEBUG log is **required** (not optional):
  the test captures it (`GenericTestUtils.LogCapturer`) and records, per row, the number of "not scanning file" lines and
  the set of file names they name. A row in which fewer than 6 files are cached matches only if those lines name exactly the
  files predicted to be skipped (L = 0: f01–f06; 2B and 2.5B: f03–f06; 4B: f05–f06; order case: a2, a3; lowering: f04–f06
  after the change), and no such line exists for the 6B / unlimited rows.
- **A3 (B2c/B2e step 5).** The add-time contrast is its own test on a fresh cluster in which only pool `r` (L = 2B) exists:
  first `addCacheDirective(/d, r)` without FORCE (expect "remaining capacity", no directive created), then with FORCE;
  pool `r` and the DataNode are then read as the L = 2B row of B2f.
- **A4 (B3a).** The base distribution on `pc75` (`/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2`) was
  built without `-Pnative`. The run copies it to `$RUN/hadoop` (`RUN=/mydata/jingsong-s4/CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous-run1/cluster`),
  builds `hadoop-common` natively in the case's source copy (`mvn -B -pl hadoop-common-project/hadoop-common package -Pnative
  -DskipTests -Dmaven.javadoc.skip=true`; CMake 3.22.1, zlib1g-dev, libssl-dev installed on `pc75` with apt on 2026-11-24)
  and copies `hadoop-common-project/hadoop-common/target/native/target/usr/local/lib/libhadoop.so*` into
  `$RUN/hadoop/lib/native/`. `hadoop checknative` must print `hadoop:  true`. `ulimit -l` on `pc75` is 16492912 KB (no
  change needed). Ports: default ports, after `ss -ltn` shows them free.
- **A5 (B3e).** After step 5 (live lowering), remove the directive and pool `p` and wait until CacheUsed = 0 before step 6;
  after step 6 remove pool `r` likewise before step 7. Step 6's predictions are pool `r` alone on an otherwise empty cache.
- **A6 (B3d).** Plateau: sample every 2 s; the plateau is reached when the last 10 samples of (CacheUsed, NumBlocksCached,
  VmLck, pool BYTES_CACHED) are equal; sample at least 60 s per change and at most 120 s, else **not settled**. VmLck
  baseline: after both daemons are up and before any directive; re-taken after the DataNode restart of step 7.
- **A7 (B2g, B3g).** Rows added for a count that differs from the prediction while staying ≤ L, for missing disallow-branch
  evidence, and (cluster) for a capped counter with real locked memory above L (in the tables, marked A7). Confirmation
  needs both the ceiling following L (B2f/B3f counts) and the DEBUG lines of A2/B3d.
- **A8 (B3c/B3e, runbook defect found in the audit).** B3e step 3 puts the files before step 4, and B3c re-adds the
  directive with the files in place, so `-addDirective` without `-force` would fail the add-time check
  (`0 + 6U > L`) for L = 0, 2U, 2.5U, 4U, contradicting B3c's "empty directory" isolation. Fix: the six files are put
  into `/stash`; for each knob value (and steps 5 and 7) the pool and the directive are created on the **empty** `/d`,
  then the files are moved in with `hdfs dfs -mv /stash/fNN /d/` in name order (same blocks, no re-upload), and the
  change time is the last move; between values they are moved back to `/stash`. Step 6 (add-time contrast) moves them
  into `/d` first, as intended there. The DEBUG requirement of A2 applies to the cluster rows with the names `/d/fNN`
  (L = 0: f01–f06; 2U, 2.5U: f03–f06; 4U: f05–f06; lowering after: f04–f06; `-force`: f03–f06; none for unlimited and
  the DN-cap control).

### D2. Stage-4 result (2026-11-24, run 1, node `pc75`)

Results file: `~/writeup-hadoop/out/o21/results.md` (outside the repository at run time). **Unit: Confirmed — caps**
(B2g row 1; all 11 rows of B2f matched exactly, add-time contrast as predicted, skipped-file DEBUG lines as A2 requires).
**Cluster: Confirmed — caps** (B3g rows 1–3; all 9 rows of B3f matched exactly, including real locked memory: DataNode
`VmLck` 0 / 2048 / 2048 / 4096 / 6144 kB at L = 0 / 2U / 2.5U / 4U / unlimited, 6144 → 3072 kB on live lowering,
2048 kB for `-force` into L = 2U, 3072 kB for the DN-cap control; baseline 0). **Outcome class: true positive.**
Note for the trace (A3 bypass "Lag"): on live lowering, real locked memory fell to 3072 kB within ~4 s while the
DataNode's `CacheUsed` counter stayed at 6 MiB until ~13 s; the counter lags the memory, not the reverse. Runbook
defects (harness only, none touching B1/B2f/B3f): see the results file §3. The B2f–B3h text is unchanged since the
frozen version (sha256 `b60c6fe5…`).
