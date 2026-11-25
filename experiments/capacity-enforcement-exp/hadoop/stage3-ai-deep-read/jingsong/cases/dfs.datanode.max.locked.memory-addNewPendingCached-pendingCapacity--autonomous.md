# dfs.datanode.max.locked.memory — verification solution  <!-- file: cases/dfs.datanode.max.locked.memory-addNewPendingCached-pendingCapacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`CacheReplicationMonitor.java:745`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/CacheReplicationMonitor.java#L745) — `if (pendingCapacity < blockInfo.getNumBytes())` in `addNewPendingCached` (row unit) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive` — the NameNode only schedules a block for caching on a DataNode when that DataNode's reported cache remaining (capacity = `dfs.datanode.max.locked.memory`, minus used, minus bytes already pending) still holds the block, and the DataNode backs this with a hard reserve check against the same value before it mmaps and mlocks the block. So the DataNode's locked (pinned, off-heap) memory for HDFS centralized caching follows the key. |
| Ground | — |

Parts of the stem: constraint `dfs.datanode.max.locked.memory`; function `addNewPendingCached`
(the method that directly encloses the given if); operand `pendingCapacity` (the limit-side operand
of the given if, as written there).

## A. Constraint trace

**A1. The constraint.**
- Name: `dfs.datanode.max.locked.memory` (configuration key).
- First declared:
  [`DFSConfigKeys.java:155`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java#L155)
  (`DFS_DATANODE_MAX_LOCKED_MEMORY_KEY`), default constant `DFS_DATANODE_MAX_LOCKED_MEMORY_DEFAULT = 0`
  at `DFSConfigKeys.java:156`. `hdfs-default.xml:2984-2999` also gives `0` and documents that 0
  disables in-memory caching, that RLIMIT_MEMLOCK must be at least this value, and that it has no
  effect without the native library. Constant and XML agree (0).
- Unit: bytes; read with `getLongBytes` (`DNConf.java:265-267`), so size suffixes (`k`, `m`, `g`) are
  accepted.
- Set in `hdfs-site.xml` on each DataNode (or `-D` in a test `Configuration`). It is read once into
  the final field `DNConf.maxLockedMemory` (`DNConf.java:131`, `:265`), so a change needs a DataNode
  restart; it is not in the DataNode's reconfigurable set.
- Read by: the DataNode. At startup `DataNode.java:1892-1912` refuses to start if the value is > 0 and
  native mlock is unavailable (`verifyCanMlock`) or if the value exceeds RLIMIT_MEMLOCK. The value is
  turned into the DRAM cache capacity in `MemoryMappableBlockLoader.initialize`
  (`MemoryMappableBlockLoader.java:46-48`: `new CacheStats(dnConf.getMaxLockedMemory())`), reported to
  the NameNode in every heartbeat as `cacheCapacity` (`BPServiceActor.java:565-566`), stored on the
  NameNode in `DatanodeDescriptor.updateHeartbeatState` (`DatanodeDescriptor.java:458-459`), and
  consumed by the NameNode's `CacheReplicationMonitor` through `DatanodeInfo.getCacheRemaining()`
  = `cacheCapacity - cacheUsed` (`DatanodeInfo.java:229-231`).
- Other sources: when persistent-memory caching is configured (`dfs.datanode.pmem.cache.dirs`),
  `MappableBlockLoaderFactory.java:42-50` picks a pmem loader whose capacity is the pmem volumes' size
  (`PmemMappableBlockLoader.java:124-125`), and `dfs.datanode.max.locked.memory` no longer sets the
  reported capacity. The OS limit RLIMIT_MEMLOCK (`ulimit -l`) bounds the key from above at startup.
  This case assumes the DRAM path (no pmem dirs).

**A2. What it caps.** DataNode memory that is mmapped and `mlock`ed to hold cached HDFS block
replicas (centralized cache management): off-heap, pinned RAM in the DataNode process, visible as
`VmLck` in `/proc/<dn pid>/status`. The quantity compared at the given check is, for one candidate
DataNode, `pendingCapacity = datanode.getCacheRemaining() + (bytes pending uncache) - (bytes pending
cache)` (`CacheReplicationMonitor.java:723-744`), against the size of the block to be cached,
`blockInfo.getNumBytes()`. On the DataNode, the hard check compares `usedBytes + roundUp(blockLength)`
against `maxBytes` (`CacheStats.java:95-101`).

**A3. Mechanism.**
1. A cache directive (`hdfs cacheadmin -addDirective`) marks a path for caching. The NameNode's
   `CacheReplicationMonitor` thread rescans every `dfs.namenode.path.based.cache.refresh.interval.ms`
   (or on directive change) (`CacheReplicationMonitor.java:161-216`, `rescan` at `:289-313`).
2. `rescanCachedBlockMap` (`CacheReplicationMonitor.java:515`) first drops pending-cache entries
   that no longer fit in each DataNode's `getCacheRemaining()` (`:519-541`), then per cached block
   computes how many more cached replicas are needed and calls `addNewPendingCached` (`:616-620`).
3. `addNewPendingCached` (`CacheReplicationMonitor.java:684`) loops over the block's replica holders;
   for each in-service, non-corrupt, not-yet-cached DataNode it computes `pendingBytes` by subtracting
   sizes of blocks already in that node's pending-cached list and adding sizes of blocks pending
   uncache (`:723-742`), then `pendingCapacity = pendingBytes + datanode.getCacheRemaining()` (`:744`).
4. **The check:**
   [`CacheReplicationMonitor.java:745`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/CacheReplicationMonitor.java#L745)
   `if (pendingCapacity < blockInfo.getNumBytes())`.
   - True (block does not fit): the DataNode is skipped (`continue`), `outOfCapacity++` (`:746-753`);
     if no node fits, the block stays under-cached and a DEBUG line "DataNodes have insufficient cache
     capacity" is logged (`:766-773`). No cache command is sent for that node.
   - False (fits): the node joins `possibilities` (`:755`); `chooseDatanodesForCaching` picks up to
     the needed count, weighted by cache-remaining percent (`:757-758`, `:786-855`), and the block is
     added to the node's `pendingCached` list (`:759-764`).
5. `DatanodeManager.addCacheCommands` turns `pendingCached` into a `DNA_CACHE` command on the next
   heartbeat (`DatanodeManager.java:1782-1795`); the DataNode handles it in `BPOfferService` (`:749`,
   `:834`) -> `FsDatasetImpl.cache` (`FsDatasetImpl.java:2587-2590`) -> `FsDatasetCache.cacheBlock`
   (`FsDatasetCache.java:272`).
6. DataNode backstop: `CachingTask.run` calls `cacheLoader.reserve(key, length)`
   (`FsDatasetCache.java:415`) -> `CacheStats.reserve` rounds up to the OS page size and fails with -1
   if `used + count > maxBytes` (`CacheStats.java:95-101`). On failure it logs "could not reserve
   more bytes in the cache" and gives up (`FsDatasetCache.java:417-423`, failure counted in
   `numBlocksFailedToCache`, `:485`). On success the block is mmapped and mlocked
   (`MemoryMappableBlockLoader.java:74-82`). Reserved bytes are released on failure or uncache
   (`FsDatasetCache.java:479-481`, `:563`).
7. The DataNode reports `cacheUsed` (which counts in-flight reservations as used, `CacheStats.java:32-43`)
   in each heartbeat, and the cached-block list in a cache report every `dfs.cachereport.intervalMsec`
   (`BPServiceActor.java:490-500`); a DataNode with capacity 0 sends no cache report (`:492-494`).

Overshoot / bypass paths:
- The NameNode check uses `blockInfo.getNumBytes()` (not page-rounded) and a heartbeat-stale
  `cacheUsed`, so it can assign a block that the DataNode then refuses at `CacheStats.java:100`; the
  DataNode reserve is the hard cap, the NameNode check is the scheduling cap. Neither lets locked
  bytes exceed `maxBytes` (rounded to pages).
- Pending bytes are double-counted for a short window (block cached and in `cacheUsed`, but still in
  NN `pendingCached` until the next cache report) — this under-assigns, never over-assigns.
- Lazy-persist (RAM_DISK) writes reserve from the same `CacheStats` (`FsDatasetImpl.java:1621`,
  comment at `FsDatasetCache.java:185`), shrinking the room left for cached blocks.
- With pmem cache dirs the key does not set capacity (A1).

**A4. Other consumers.** The DataNode JVM heap and other off-heap (direct buffers, metaspace, thread
stacks) are outside this key; so is the OS page cache used for ordinary reads; client-side
short-circuit mmaps of cached blocks (they share the same physical pages, not extra locked memory);
lazy-persist RAM-disk replicas in tmpfs (counted in the same `CacheStats`, A3); any other process on
the host that locks memory.

**A5. Evidence beyond the source.**
- `hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/CentralizedCacheManagement.md:204` (native
  `libhadoop.so` required), `:224` (the key is the max memory a DataNode uses for caching; `ulimit -l`
  must match), `:268-272` (RLIMIT_MEMLOCK startup error and how to raise it). Published as
  https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/CentralizedCacheManagement.html
- Existing tests that exercise the same path with mlock stubbed out:
  `TestCacheDirectives#testExceedsCapacity` (`TestCacheDirectives.java:1525-1548`, asserts
  pending-cached lists stay empty once capacity is full) and `TestFsDatasetCache#testFilesExceedMaxLockedMemory`
  (`TestFsDatasetCache.java:364-424`).
- `hdfs-default.xml:2984-2999`, `:3038-3060`, `:3082-3095`.

## B. Verification solution

**B1. Claim under test.** For a DataNode with `dfs.datanode.max.locked.memory = C` (DRAM cache,
page-aligned blocks of size B), caching a path larger than C leaves exactly `floor(C/B)` blocks
cached on that DataNode, cache used = `floor(C/B)·B ≤ C`, and its locked memory does not exceed C;
the NameNode check at `CacheReplicationMonitor.java:745` is what keeps it from scheduling more, so
the DataNode records no reserve failures. The claim is wrong if cached bytes or locked memory exceed
C, or if they do not change when C changes.

### B2. Unit tier

**B2a. Environment and build.** JDK 8, Maven 3.3+. Copy the tree to local disk first
(`rsync -a <source>/ /mydata/<run>/hadoop-src/`), never build in the shared tree. Build:
`cd /mydata/<run>/hadoop-src && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
Add a new test class
`hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestCacheCapacityCheck.java`
in the copy. Run with
`mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestCacheCapacityCheck`. No native code needed:
the test installs `NativeIO.POSIX.NoMlockCacheManipulator` (`NativeIO.java:311-328`), which skips the
real `mlock`, reports page size 4096 and an effectively unlimited memlock limit. Surefire default JVM
options are fine; set `-Dtest.build.data=/mydata/<run>/test-data` so MiniDFSCluster data stays on
local disk.

> **Amendment A1 (stage 4, 2026-11-25; node specifics, no change to B2f/B2g).** Node `pc82` (Jingsong's
> environment). The copy is made with `copy-source.sh /mydata/jingsong-s4/<stem>-run1/src` (not `rsync`), and the
> `-am install` step is not needed: the node's `~/.m2` holds all 3.4.2 modules from the base build, so the test runs
> with `mvn -B -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestCacheCapacityCheck#testC* -Dtest.build.data=/mydata/jingsong-s4/<stem>-run1/test-data`
> (the mutant: `-Dtest=TestCacheCapacityCheck#mutantC32768`). The test class also sets
> `dfs.namenode.fs-limits.min-block-size = 4096` (B2b) and is the stage-4 harness `TestCacheCapacityCheck.java`.

**B2b. Knobs.** `DFS_DATANODE_MAX_LOCKED_MEMORY_KEY` = C ∈ {16384, 32768, 65536} bytes (4, 8, 16 pages
of 4096), set with `conf.setLong(...)` before building the cluster, one MiniDFSCluster per value
(restart-only knob). Fixed: `dfs.blocksize = 4096` and `dfs.namenode.fs-limits.min-block-size = 4096`
(blocks one page each, no rounding), `dfs.heartbeat.interval = 1`, `dfs.cachereport.intervalMsec = 1000`,
`dfs.namenode.path.based.cache.refresh.interval.ms = 1000` (as `TestCacheDirectives.createCachingConf`,
`TestCacheDirectives.java:124-135`). One DataNode, replication 1, so every block's only candidate is
that node. Plus C = 0 (caching disabled) as a control.

**B2c. Workload.** `DFSTestUtil.createFile(dfs, /big, 32*4096 = 131072 bytes, (short)1, seed)` → 32
blocks of 4096. `dfs.addCachePool(new CachePoolInfo("p"))`, `dfs.addCacheDirective(path=/big,
pool=p, replication=1)`. Needed bytes 131072 > every C (2×–8× over), so the check at line 745 must
return true once C/4096 blocks are cached or pending.

**B2d. Observables and instruments.** After settling (poll every 500 ms until the values are
unchanged for 5 consecutive polls, max 60 s):
- DataNode operand: `dn.getFSDataset().getCacheUsed()`, `getCacheCapacity()`,
  `getNumBlocksCached()`, `getNumBlocksFailedToCache()` (`FSDatasetMBean.java:104-124`).
- NameNode view: under `namesystem.readLock()`, the `DatanodeDescriptor` for the DN:
  `getCacheRemaining()`, `getCached().size()`, `getPendingCached().size()` (pattern of
  `TestCacheDirectives.checkPendingCachedEmpty`, `:1505-1523`); directive stats via
  `dfs.listCacheDirectives(null)` → `getStats().getBytesCached()`, `getBytesNeeded()`.
- Trace the check itself: `GenericTestUtils.setLogLevel(LoggerFactory.getLogger(CacheReplicationMonitor.class), Level.TRACE)`
  and capture with `LogCapturer`; count lines containing "is not a valid possibility because the
  block has size".
- Not observable here: real locked memory (mlock is stubbed). That is the cluster tier's job.

> **Amendment A2 (stage 4, 2026-11-25; settle rule).** "Unchanged for 5 polls" (2.5 s) can settle before the first
> 1-s rescan has scheduled anything, and cache commands are re-sent only every
> `dfs.namenode.path.based.cache.retry.interval.ms` (default 30000, `DatanodeManager.java:1785-1789`). Settled now
> means: the tuple (DN CacheUsed, NumBlocksCached, NumBlocksFailedToCache, NN CacheRemaining, NN cached,
> NN pendingCached, BytesNeeded, BytesCached, FilesCached) unchanged for 10 consecutive 500-ms polls **and** at least
> 35 s after the directive was added; give up at 90 s and record `settled=false`. The maxima of DN CacheUsed and of
> NN pendingCached over all polls are recorded too.
>
> **Amendment A3 (stage 4, 2026-11-25; instrument and outcome rows).** `NumBlocksFailedToCache` is also incremented
> when a cache command names a block the DataNode already holds or is caching (`FsDatasetCache.java:276-281`), not
> only on a reserve failure (`:417-423`). The test therefore also counts, from a `LogCapturer` on `FsDatasetCache`,
> the DataNode WARN lines "could not reserve more bytes" since the directive (the reserve refusal itself), and, from
> the `CacheReplicationMonitor` capture, the TRACE lines "added to PENDING_CACHED on DataNode". Rows added to B2f and
> B2g below.

**B2e. Procedure.**
1. In the test, for each C: set the cache manipulator to `NoMlockCacheManipulator` *before*
   building the cluster (so `CacheStats.PageRounder` sees 4096), build `MiniDFSCluster` with 1 DN,
   `waitActive()`.
2. Create `/big`, add pool and directive.
3. Poll the observables of B2d until stable; record them.
4. Assert/print the B2f values; remove the directive; wait until `getCacheUsed()` returns to 0;
   shut down the cluster; restore the previous cache manipulator.
5. Mutation control (separate run, separate copy of the class file, never committed): in the local
   copy change line 745 to `if (false)` (check disabled), rebuild hadoop-hdfs, rerun C = 32768.

**B2f. Predictions.**

| C (bytes) | blocks cached | DN CacheUsed | BytesCached (directive) | NN pendingCached after settle | NumBlocksFailedToCache | "not a valid possibility" TRACE lines |
|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 0 | ≥ 1 per rescan (remaining 0 < 4096) |
| 16384 | 4 | 16384 | 16384 | 0 | 0 | > 0 |
| 32768 | 8 | 32768 | 32768 | 0 | 0 | > 0 |
| 65536 | 16 | 65536 | 65536 | 0 | 0 | > 0 |
| 32768, `/small` 2 blocks (B2h control; A3) | 2 | 8192 | 8192 | 0 | 0 | 0 |

A3 (2026-11-25): in every unmutated row the DataNode logs 0 "could not reserve more bytes" lines; TRACE
"added to PENDING_CACHED" lines = blocks cached (C/4096; 2 for the control). In the mutant row the TRACE reject
count is 0 (the check is gone) and "could not reserve" lines ≥ 24.

BytesNeeded = 131072 in every row. With line 745 disabled (mutation, C = 32768): DN CacheUsed still
32768 and 8 blocks cached (DataNode reserve backstop), but the NameNode assigns all 32 blocks, so
NumBlocksFailedToCache > 0 (≥ 24 on the first round, growing with resends every
`dfs.namenode.path.based.cache.retry.interval.ms`), pendingCached stays non-empty (24), and DN logs
"could not reserve more bytes".

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Blocks cached = C/4096 and CacheUsed = C for each C, pending empty, failures 0 | Claim holds: usage follows C and the NN check at 745 keeps scheduling within C |
| CacheUsed > C for any C | Claim wrong: neither check caps |
| CacheUsed the same for all C (not 0) | Claim wrong: the key does not set the cap |
| CacheUsed = C but NumBlocksFailedToCache > 0 or pendingCached non-empty after settle (unmutated) | Usage is capped by the DataNode reserve, but the NN check at 745 is not what bounds scheduling (stale or under-counted remaining); partial confirmation |
| Mutated run shows failures > 0 and non-empty pending, unmutated shows 0 | Line 745 is the scheduling cap (confirms its role) |
| Mutated run identical to unmutated | Line 745 has no effect (another check, e.g. `:519-541`, does the work) |
| Fewer blocks cached than C/4096 even with C ≥ 4096 and no TRACE rejections | Caching path broken (setup issue); not a reading of the claim |
| (A3) NumBlocksFailedToCache > 0 in an unmutated row but 0 "could not reserve" lines, CacheUsed = C, pending empty | Duplicate cache commands (a resend before the cache report), not a block scheduled past C; the row reads as the first row ("claim holds") with this noted |
| (A3) "could not reserve" lines > 0 in an unmutated row | The NN check let a block through that did not fit (stale remaining): the "partial confirmation" row above |
| (A3) `/small` control caches fewer than 2 blocks | Caching path broken below the cap; the series is not a reading of the claim |
| (A3) Mutant shows TRACE reject lines > 0 | Mutation not in effect; the mutant row is invalid and is re-run |

**B2h. Controls.** C = 0 shows nothing is cached without the key; a directive on a file smaller than
C (e.g. 2 blocks, C = 32768) must cache all of it (positive control: usage moves with the workload
below the cap); single DataNode and replication 1 remove placement choice; page-aligned blocks remove
rounding; the mutation run isolates line 745 from the DataNode backstop.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, pseudo-distributed: 1 NameNode, 1 DataNode (no YARN
needed). JDK 8 (or 11 to run). Build a distribution from a local copy of the tag:
`mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true` (`BUILDING.txt:364-368`). Native
`libhadoop.so` is mandatory (`DataNode.java:1893-1898`; `CentralizedCacheManagement.md:204`): either
build with `-Pdist,native` (needs CMake, zlib-dev, openssl-dev, protobuf per `BUILDING.txt:4-16`) or
build only hadoop-common native,
`mvn -pl hadoop-common-project/hadoop-common package -Pnative -DskipTests`, and copy
`hadoop-common-project/hadoop-common/target/native/target/usr/local/lib/libhadoop.so*` into
`$HADOOP_HOME/lib/native/`. Check with `$HADOOP_HOME/bin/hadoop checknative -a` (line `hadoop: true`).
Data/log on local disk: `hadoop.tmp.dir=/mydata/<run>/tmp`, `dfs.namenode.name.dir=/mydata/<run>/nn`,
`dfs.datanode.data.dir=/mydata/<run>/dn`, `HADOOP_LOG_DIR=/mydata/<run>/logs`,
`HADOOP_PID_DIR=/mydata/<run>/pids`. Heap: `HADOOP_HEAPSIZE_MAX=1g`.

Configuration:
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir` as above.
- `hdfs-site.xml`: `dfs.replication=1`, `dfs.blocksize=1048576` (1 MiB, equals the default
  `dfs.namenode.fs-limits.min-block-size`, `DFSConfigKeys.java:623-624`),
  `dfs.datanode.max.locked.memory=<C>`, `dfs.namenode.path.based.cache.refresh.interval.ms=3000`,
  `dfs.cachereport.intervalMsec=3000`, name/data dirs as above.

> **Amendment A4 (stage 4, 2026-11-25; node specifics, no change to B3f/B3g).** Node `pc82`. The distribution is a
> copy of the node's base build `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` (no `lib/native`),
> with `libhadoop.so*` from `mvn -B -pl hadoop-common-project/hadoop-common package -Pnative -DskipTests` in the case
> copy; `cmake`, `zlib1g-dev`, `libssl-dev`, `pkg-config` installed with apt for this (as on `pc75` for the
> `CachePoolInfo_limit` case). All run state under `/mydata/jingsong-s4/<stem>-run1/cluster/`. Both files (`/big`
> and `/small`) are written right after the first DataNode start (B3e steps 5 and 8): an uncached file uses no
> locked memory, so this changes no reading. After each DataNode restart the run waits until both the DataNode's
> JMX `CacheCapacity` and the NameNode's `dfsadmin -report` "Configured Cache Capacity" equal C (the NameNode
> otherwise still shows the previous registration).

**B3b. Knobs.** `dfs.datanode.max.locked.memory` C ∈ {0, 2097152 (2 MiB), 4194304 (4 MiB), 6291456
(6 MiB)}; DataNode restart per value (NameNode can stay up). The values fit the common Linux default
`ulimit -l` of 8192 KB; first run `ulimit -H -l` and `ulimit -S -l`: the DataNode must be started from
a shell whose soft limit ≥ C/1024 KB (`ulimit -S -l 8192`, or `unlimited` if the hard limit allows).
Start daemons with `hdfs --daemon start ...` from that shell (not `start-dfs.sh`, which goes through
ssh and gets the PAM limits instead). If the hard limit is ≥ 1 GiB or unlimited, an optional larger
series C ∈ {64, 128, 256} MiB with `dfs.blocksize=16777216` and a 512 MiB file gives a clearer
`VmLck` signal; keep C well under free RAM.

**B3c. Workload.** `dd if=/dev/urandom of=/mydata/<run>/f16 bs=1M count=16`;
`hdfs dfs -put /mydata/<run>/f16 /big` → 16 blocks of 1 MiB. `hdfs cacheadmin -addPool p`;
`hdfs cacheadmin -addDirective -path /big -pool p -replication 1`. Needed 16 MiB > every C (2.7×–8×).
Duration: about 60 s per value after the directive.

**B3d. Observables and instruments.** Sample every 5 s for 60 s after the directive is added:
- Actual resource: `grep VmLck /proc/$(cat /mydata/<run>/pids/hadoop-$USER-datanode.pid)/status`
  (kB of locked memory).
- DataNode counters: `curl -s 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=FSDatasetState*'`
  → `CacheCapacity`, `CacheUsed`, `NumBlocksCached`, `NumBlocksFailedToCache`.
- NameNode view: `hdfs dfsadmin -report` (per-DN "Configured Cache Capacity", "Cache Used", "Cache
  Remaining", `DatanodeInfo.java:410-419`); `hdfs cacheadmin -listDirectives -stats` (BYTES_NEEDED,
  BYTES_CACHED, FILES_CACHED).
- The check: `hadoop daemonlog -setlevel localhost:9870 org.apache.hadoop.hdfs.server.blockmanagement.CacheReplicationMonitor TRACE`
  before the directive; then `grep -c "is not a valid possibility because the block has size" $HADOOP_LOG_DIR/*namenode*.log`.
  DataNode refusals: `grep -c "could not reserve more bytes" $HADOOP_LOG_DIR/*datanode*.log`.
- Not directly observable: which pages are locked per block (only the process total).

> **Amendment A5 (stage 4, 2026-11-25; settle rule and counts).** Sample every 5 s from the directive; stop when at
> least 60 s have passed and the last 4 samples are equal on (CacheUsed, NumBlocksCached, NumBlocksFailedToCache,
> VmLck, BYTES_CACHED); give up at 120 s (`settled=false`). The NameNode reject lines, "added to PENDING_CACHED"
> lines and the DataNode "could not reserve" lines are counted from the log offsets taken just before the
> directive. "VmLck ≈ X kB" in B3f means within 16 kB (4 pages) of X above the per-phase baseline.

**B3e. Procedure.**
1. Copy source to `/mydata/<run>/hadoop-src`, build the distribution and native lib, unpack to
   `/mydata/<run>/hadoop`, `export HADOOP_HOME=...`, write the config above, `hadoop checknative -a`.
2. `hdfs namenode -format -nonInteractive`; `hdfs --daemon start namenode`.
3. For each C (start with 0): edit `hdfs-site.xml`; in a shell with `ulimit -S -l` ≥ C/1024:
   `hdfs --daemon start datanode`; check the DataNode log has "Starting DataNode with maxLockedMemory = C"
   (`DataNode.java:1914`) and the DN is live in `hdfs dfsadmin -report`.
4. Record baseline `VmLck` (expected 0 kB).
5. First value only: put `/big`. Set the TRACE level. Add pool (once) and directive.
6. Sample B3d for 60 s; record final values.
7. `hdfs cacheadmin -removeDirectives -path /big`; wait until `CacheUsed` = 0 and `VmLck` returns
   to baseline (this also checks release); `hdfs --daemon stop datanode`.
8. Positive control (C = 6 MiB): `hdfs dfs -put` a 4 MiB file `/small`, directive on `/small` only.
9. Stop: `hdfs --daemon stop datanode; hdfs --daemon stop namenode`; `jps` shows neither.

**B3f. Predictions.**

| C | DN start | NumBlocksCached | CacheUsed / BYTES_CACHED | VmLck (kB) | NumBlocksFailedToCache | NN "not a valid possibility" lines |
|---|---|---|---|---|---|---|
| 0 | starts | 0 | 0 | baseline (0) | 0 | present (remaining 0) |
| 2 MiB | starts | 2 | 2097152 | ≈ 2048 (+ ≤ a few pages over baseline) | 0 | > 0 |
| 4 MiB | starts | 4 | 4194304 | ≈ 4096 | 0 | > 0 |
| 6 MiB | starts | 6 | 6291456 | ≈ 6144 | 0 | > 0 |
| 6 MiB, `/small` 4 MiB (control) | starts | 4 | 4194304 | ≈ 4096 | 0 | 0 for `/small` blocks |
| (A6) 64 MiB, `/big2` 512 MiB in 16-MiB blocks | starts | 4 | 67108864 | ≈ 65536 | 0 | > 0 |
| (A6) 128 MiB, `/big2` | starts | 8 | 134217728 | ≈ 131072 | 0 | > 0 |
| (A6) 256 MiB, `/big2` | starts | 16 | 268435456 | ≈ 262144 | 0 | > 0 |

A6 (2026-11-25): `ulimit -l` on `pc82` is 16492912 kB (hard and soft), so the optional larger series of B3b is run
after the main series; BYTES_NEEDED for `/big2` = 536870912. In every row the DataNode logs 0 "could not reserve"
lines.

BYTES_NEEDED = 16777216 for `/big`. `VmLck` never exceeds C/1024 kB plus baseline. A C above the
soft `ulimit -l` (e.g. 16 MiB with an 8 MiB limit) makes the DataNode exit at startup with "is more
than the datanode's available RLIMIT_MEMLOCK ulimit" (`DataNode.java:1903-1910`).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| VmLck and CacheUsed step 2 → 4 → 6 MiB with C, BYTES_CACHED < BYTES_NEEDED, failures 0 | Claim holds: locked memory follows the key; NN check keeps scheduling within it |
| VmLck > C/1024 kB + baseline at any C | Claim wrong: the key does not cap locked memory |
| VmLck flat across C while the `/small` control moves it | Claim wrong: cached memory is not governed by the key |
| CacheUsed = C but VmLck ≈ 0 | mlock not happening (native lib missing / stubbed); the tier did not measure the resource — fix native setup |
| VmLck ≤ C but NumBlocksFailedToCache > 0 and DN "could not reserve" lines | Cap holds via the DataNode reserve; the NN check at 745 let through over-assignment (stale remaining) |
| Nothing cached at any C > 0 and control also 0 | Caching path not working (directive, native, ulimit); not a reading of the claim |
| (A7) NumBlocksFailedToCache > 0 with 0 "could not reserve" lines, VmLck and CacheUsed as predicted | Duplicate cache commands (resend before the cache report); reads as the first row with this noted |
| (A7) The main series follows C but a phase did not settle (A5) | The phase's numbers are read at 120 s; if they still move, that value is Not confirmed for that tier |

**B3h. Controls.** C = 0 run (nothing cached, no cache report); the `/small` positive control
(usage follows workload below the cap); baseline `VmLck` before any directive (JVM itself locks
nothing by default); one DataNode with replication 1 (no placement choice); 1 MiB blocks are
page-aligned (no rounding difference between NN and DN accounting); removing the directive returns
`VmLck` to baseline (the locked memory is the cache, not something else).

**B4. Risks and cleanup.** Unit tier: MiniDFSCluster data under `/mydata/<run>/test-data`; delete
after. Cluster tier: all data, logs and pids under `/mydata/<run>` on local disk (about 50 MiB of
HDFS data plus the distribution); ports 9000, 9870, 9864, 9866, 9867 must be free — if another
person's daemons use them on a shared node, move them (`dfs.namenode.rpc-address`,
`dfs.namenode.http-address`, `dfs.datanode.address`, `dfs.datanode.http.address`,
`dfs.datanode.ipc.address`). Locked memory is at most 6 MiB (or the optional series' C), well inside
host RAM; never set C close to free RAM. Do not edit `/etc/security/limits.conf` (no change outside
the run's shell); raise only the soft limit in the launching shell. Cleanup: remove directives and
pool, `hdfs --daemon stop datanode`, `hdfs --daemon stop namenode`, `jps` shows no `NameNode`/`DataNode`,
`rm -rf /mydata/<run>/{tmp,nn,dn,logs,pids}`; the mutated source copy is deleted, never committed.

## C. Sources read

hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/CacheReplicationMonitor.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/DatanodeDescriptor.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/DatanodeManager.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/DatanodeInfo.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java
hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DNConf.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataNode.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/BPServiceActor.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetCache.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/CacheStats.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/MappableBlockLoaderFactory.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/MemoryMappableBlockLoader.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/PmemMappableBlockLoader.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetImpl.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/metrics/FSDatasetMBean.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/nativeio/NativeIO.java
hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/CentralizedCacheManagement.md
hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestCacheDirectives.java
hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/TestFsDatasetCache.java
BUILDING.txt
https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/CentralizedCacheManagement.html (same content as the .md above)

## D. Stage-4 feedback

**D1. Audit amendments (2026-11-25, stage 4, before any reading).** A1 (B2a, node specifics), A2 (B2d, settle rule),
A3 (B2d/B2f/B2g, "could not reserve" and "added to PENDING_CACHED" counts, small-control row, duplicate-command,
failed-control and mutation-not-in-effect rows), A4 (B3a, native build and node specifics), A5 (B3d, settle rule and
"≈" tolerance), A6 (B3f, larger series 64/128/256 MiB), A7 (B3g, duplicate-command and unsettled-phase rows). Frozen
whole-file sha256 `759f0d3ad3f8fce2c5608623f058b9f1f5a4af9d6730add5b336722749e1e2d3`.

**D2. Stage-4 result (2026-11-25, node `pc82`, run 1 only).** Results file `results/dfs.datanode.max.locked.memory-addNewPendingCached-pendingCapacity--autonomous.md`
(at run time `~/writeup-hadoop/out/o23/results.md`).
- Unit: **Confirmed — caps.** Blocks cached 0/4/8/16, CacheUsed = BytesCached = C at C = 0/16384/32768/65536, NN pending 0,
  0 reserve refusals, TRACE reject lines in every over-cap row; `/small` control cached whole. With line 745 disabled the
  NameNode commanded all 32 blocks and the DataNode refused 2000+ reservations (cap held only by the DN reserve).
- Cluster: **Confirmed — caps.** Real `VmLck` 0/2048/4096/6144 kB at C = 0/2/4/6 MiB and 65536/131072/262144 kB at
  C = 64/128/256 MiB, equal to CacheUsed/1024; 0 reserve refusals; `/small` control 4096 kB.
- **Outcome class: true positive.**
- Prediction misses (no effect on the claim): `NumBlocksFailedToCache` is not 0 — the NameNode re-sends pending blocks each
  heartbeat until the cache report, and the DataNode counts a repeat as a failure (`FsDatasetCache.java:276-281`); read
  through A3/A7. The cluster `/small` control logged 2 transient reject lines (B3f said 0): the cached-but-still-pending
  double-count window of A3's overshoot note (under-assigns, never over-assigns). The mutant re-sends came every ~1 s, not
  every 30-s retry interval.

