# dfs.datanode.pmem.cache.dirs — verification solution  <!-- file: cases/dfs.datanode.pmem.cache.dirs-chooseVolume-availableBytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`PmemVolumeManager.java:407`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/PmemVolumeManager.java#L407) — `if (availableBytes >= bytesCount)` in `PmemVolumeManager.chooseVolume(long)` (row unit, not a helper) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive`: the bytes the DataNode writes as block-cache files into each persistent-memory (SCM) cache directory named by `dfs.datanode.pmem.cache.dirs` are capped per directory at `maxBytes`. That cap is the directory's `File.getUsableSpace()` taken once at DataNode start. `chooseVolume` (line 407) and `UsedBytesCount.reserve` (line 77) refuse a block that does not fit, and the NameNode schedules caching against the same capacity. Two caveats. The cap is a startup snapshot of free space, not a number the user sets. A cancelled caching task can leave a cache file on disk that is no longer counted (A3). |
| Ground | — |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). Use a permalink at the pinned tag,
> `[`File.java:123`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/<full path under the repository root>#L123)`
> (a range is `#L123-L130`). Check that the line number is the line you mean. Other citations may
> stay plain `file:line`.

Paths below are relative to `hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/`
unless given in full. `impl/` means `server/datanode/fsdataset/impl/`.

## A. Constraint trace

**A1. The constraint.**

- **Name.** `dfs.datanode.pmem.cache.dirs` (exact key, no placeholder).
- **Kind.** A configuration key whose *value* is a list of directories. The byte limit is not
  configured. It is queried at runtime from those directories, so the limit has several sources:
  - `dfs.datanode.pmem.cache.dirs` names the cache volumes, and only through which mount/size the
    admin picks for each directory does the user set the cap. This is the primary source, the one
    a user tunes.
  - `File.getUsableSpace()` of `<dir>/hdfs_pmem_cache` is read once per volume at init,
    `impl/PmemVolumeManager.java:244-245`. This gives the actual number.
  - `PmemVolumeManager.maxBytesPerPmem` (`impl/PmemVolumeManager.java:129`, default `-1`) is a
    static test hook settable only through `@VisibleForTesting setMaxBytes(long)`
    (`impl/PmemVolumeManager.java:170-173`). When it is not `-1`, it replaces the usable-space
    value for every volume (`:246-247`). It is not reachable from configuration.
  - `dfs.datanode.pmem.cache.recovery` (`DFSConfigKeys.java:484-487`, default `true`;
    `hdfs-default.xml:3010-3018`) decides whether old cache files are wiped before the usable
    space is measured (`impl/PmemVolumeManager.java:238-241`) or recovered and added onto
    `maxBytes` (`:286-311`).
- **Declared.**
  [`DFSConfigKeys.java:482`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java#L482)
  (`DFS_DATANODE_PMEM_CACHE_DIRS_KEY = "dfs.datanode.pmem.cache.dirs"`, line 482-483). It has no
  Java default constant.
- **`hdfs-default.xml` entry.** `hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml:3001-3008`,
  value empty: "persistent memory directory used for caching block replica. Multiple directories
  separated by ','". Empty means the pmem cache is off, and the DRAM loader is used
  (`impl/MappableBlockLoaderFactory.java:42-45`).
- **Unit.** The key is a list of paths. The derived cap is in bytes, per volume.
- **Default.** Empty, so there is no pmem cache. When it is set, cap per volume =
  `getUsableSpace()` of `<dir>/hdfs_pmem_cache` at DataNode start. Total capacity = sum over the
  volumes (`impl/PmemVolumeManager.java:142-145`).
- **How set.** In `hdfs-site.xml` on the DataNode. It is read once in the `DNConf` constructor
  (`server/datanode/DNConf.java:269-270`), and `PmemVolumeManager` is a JVM singleton created once
  (`impl/PmemVolumeManager.java:148-155`), so a change needs a **DataNode restart**. It is not in the
  DataNode's reconfigurable set. The capacity is not re-measured while the DataNode runs.
- **Reader.** The DataNode only, through `FsDatasetCache` → `MappableBlockLoaderFactory` →
  `PmemMappableBlockLoader.initialize` (`impl/PmemMappableBlockLoader.java:47-58`), or
  `NativePmemMappableBlockLoader` when libhadoop is built with PMDK
  (`impl/MappableBlockLoaderFactory.java:46-49`). The NameNode sees the derived capacity only as
  the `cacheCapacity` the DataNode reports in heartbeats (`server/datanode/BPServiceActor.java:565-566`).

**A2. What it caps.**

- **Resource.** Disk, or persistent memory exposed as a file system, in each configured pmem cache
  directory. Each cached HDFS block replica is copied there as a file of exactly the replica's
  length (`impl/PmemMappableBlockLoader.java:95-97`, file `<dir>/hdfs_pmem_cache/<bpid>/subdirN/subdirM/<blockId>`,
  `impl/PmemVolumeManager.java:448-462`).
- **Quantity compared.** At line 407 the limit-side operand is `availableBytes =
  maxBytes - usedBytes` of one volume (`impl/PmemVolumeManager.java:105-107`). The usage side is
  `bytesCount`, the replica length that `FsDatasetCache.CachingTask` asks to reserve
  (`impl/FsDatasetCache.java:415`). There is no page rounding on the pmem path: the reserve goes
  straight to `PmemVolumeManager.reserve` (`impl/PmemMappableBlockLoader.java:128-131`).
- **Not capped.** DataNode heap and DRAM. The DRAM cache is disabled, `CacheStats(0)`
  (`impl/PmemMappableBlockLoader.java:58`).

**A3. Mechanism.**

1. **Volume setup.** At DataNode start, `FsDatasetCache` creates the loader and calls `initialize`
   (`impl/FsDatasetCache.java:183-186`). `PmemVolumeManager.loadVolumes` runs once per directory:
   - It checks the directory and creates `hdfs_pmem_cache`, then writes and maps a test file
     (`:319-371`).
   - When recovery is off, it empties the directory (`:238-241`).
   - It sets `maxBytes = realPmemDir.getUsableSpace()`, or the test hook value (`:243-249`).
   - A bad directory is skipped (`:253-259`). With no good directory, startup fails (`:262-265`).
2. **Recovery.** With `dfs.datanode.pmem.cache.recovery=true`, `initCache` runs
   `recoverCache` (`impl/FsDatasetCache.java:194-210`). It adds the bytes of the files it finds back
   onto `maxBytes` and reserves them (`impl/PmemVolumeManager.java:305-309`). The free space was
   measured with those files present, so the per-volume total stays "free at start + recovered".
3. **NameNode pre-filter.** The NameNode's `CacheReplicationMonitor` picks a DataNode for a cached
   block only if the DataNode's reported `cacheCapacity - cacheUsed`, net of pending
   cache/uncache bytes, is at least the block size
   (`server/blockmanagement/CacheReplicationMonitor.java:723-755`). It also drops pending blocks
   that no longer fit (`:515-535`). This filter sees only the *total* over all pmem volumes
   (`hadoop-hdfs-client/.../protocol/DatanodeInfo.java:229-231`).
4. **DataNode reserve.** A `DNA_CACHE` command reaches `FsDatasetImpl.cacheBlock` →
   `FsDatasetCache.cacheBlock` → `CachingTask.run`, which calls
   `cacheLoader.reserve(key, length)` (`impl/FsDatasetCache.java:415`). `PmemVolumeManager.reserve`
   is `synchronized` (`impl/PmemVolumeManager.java:197-210`) and calls `chooseVolume(bytesCount)`
   (`:395-417`). Round robin over the volumes, it returns the first volume where
   [`if (availableBytes >= bytesCount)`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/PmemVolumeManager.java#L407)
   holds.
   - **True.** That volume's index is returned. `UsedBytesCount.reserve` re-checks
     `next > maxBytes` with a CAS loop (`:73-84`, check at line 77) and adds the bytes. The block
     key is mapped to the volume (`:202-204`). The file is written (`impl/PmemMappableBlockLoader.java:95-97`).
   - **False on every volume.** `chooseVolume` throws `IOException("There is no enough persistent
     memory space for caching. The current max available space is <max>, but <n>is required.")`
     (`:414-416`). `reserve` logs it at WARN and returns `-1` (`:206-209`). `CachingTask` then
     logs "Failed to cache … could not reserve more bytes in the cache: <capacity> exceeded …",
     writes nothing, removes the entry and increments `numBlocksFailedToCache`
     (`impl/FsDatasetCache.java:418-423`, `:478-489`).
   - The check is per volume. A block never spans volumes, so free bytes left over on several
     volumes can add up to more than one block while every volume refuses it. In that case the
     NameNode (which sees only the total) keeps sending the command and the DataNode keeps
     refusing it at line 407.
5. **Release.**
   - **Uncache.** `UncachingTask` closes the block, which deletes the file
     (`impl/PmemMappedBlock.java:63-74`), then calls `release` (`impl/FsDatasetCache.java:558-563`,
     `impl/PmemVolumeManager.java:221-224`).
   - **Failed load.** `load` deletes the partial file itself (`impl/PmemMappableBlockLoader.java:107-114`),
     and `CachingTask` releases the reservation (`impl/FsDatasetCache.java:478-481`).

**Bypass and overshoot paths.**

- **Stale snapshot.** `maxBytes` is the free space at start. Later writes to the same file system
  by anything else lower the real free space without lowering `maxBytes`. The cache then reports
  more room than exists. A cache write that hits ENOSPC fails in `load` (`transferTo` throws
  `IOException`), is caught (`impl/FsDatasetCache.java:448-450`) and released. Real usage is still
  bounded by the file system, but the cap no longer describes it.
- **Cancelled caching leaks a file.** If an uncache arrives while a block is CACHING, the state
  becomes `CACHING_CANCELLED` (`impl/FsDatasetCache.java:308-313`). `CachingTask` then finishes the
  load, sees the cancel and returns with `success=false` (`:458-461`). Its `finally` block:
  1. calls `cacheLoader.release(key, length)` first (`:479-481`). That removes the key from
     `blockKeyToVolume` (`impl/PmemVolumeManager.java:222`).
  2. Only then calls `IOUtils.closeStream(mappableBlock)` (`impl/FsDatasetCache.java:484`).
     `PmemMappedBlock.close` asks `getCachePath(key)`, which now returns `null`
     (`impl/PmemVolumeManager.java:467-472`). `deleteMappedFile(null)` throws
     (`impl/FsDatasetUtil.java:226-229`), and `close` only logs a WARN (`impl/PmemMappedBlock.java:71-73`).

  The cache file stays on the pmem volume while its bytes are counted as free again. So the bytes
  on the volume can exceed `usedBytes`, though never what the file system can hold. Before
  `release` there was room on the file system for the leaked bytes, but `maxBytes` was not lowered
  to match. With recovery on, a restart counts the orphan as cached (`:286-311`). With recovery off,
  a restart deletes it (`:238-241`).
- **File-system overhead.** Directory entries (`subdirN`) and allocation rounding of file sizes are
  not counted; this is small.
- **Recovery and multiple block pools.** `recoverCache` raises `maxBytes` once per block pool by
  that pool's recovered bytes. The usable-space snapshot already excluded every pool's files, so
  the per-volume sum stays consistent.

**A4. Other consumers.** Anything else on the same mount takes the same bytes without being counted:
- other files on the directory (the DataNode's own data or log directories placed there by mistake,
  other processes);
- the leaked cancelled-caching files (A3);
- for the native loader, PMDK mapping metadata.

The NameNode's per-pool limit (`hdfs cacheadmin -addPool -limit`) and directive replication cap
caching at the logical level. They are separate constraints and not part of this check.
`dfs.datanode.max.locked.memory` (the DRAM cache) is not used when pmem is configured
(`impl/PmemMappableBlockLoader.java:53-58`).

**A5. Evidence beyond the source.**

- **Docs.** `hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/CentralizedCacheManagement.md:35-36, 206-214, 228-230`:
  "If this property is configured, the volume capacity will be detected. And there is no need to
  configure `dfs.datanode.max.locked.memory`."
  Published at https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/CentralizedCacheManagement.html.
- **Test.** `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/TestCacheByPmemMappableBlockLoader.java:80-81, 140-144, 212-301`
  uses `setMaxBytes` with two bogus pmem directories. It fills 64 KiB with 4 KiB blocks and asserts
  that one more file is not cached. It is skipped without PMDK (`:108`).
- **JIRA.** The SCM cache feature is the HDFS-13762 umbrella
  (https://issues.apache.org/jira/browse/HDFS-13762), background only. No measured numbers are
  relied on.

## B. Verification solution

**B1. Claim under test.** With `dfs.datanode.pmem.cache.dirs` set, the bytes of block-cache files
the DataNode keeps in each pmem cache directory never exceed that directory's usable space measured
at DataNode start. A block that does not fit in any single volume is refused at
`PmemVolumeManager.java:407` and not written. So the total cached bytes follow the volume sizes,
and fragmentation across volumes can leave unused room. The claim is false if cached bytes in a
volume exceed its startup `maxBytes`, or if a block is cached into a volume whose `availableBytes`
was below its length.

### B2. Unit tier

**B2a. Environment and build.**
- **Host and build.** A Linux host with JDK 8 and Maven 3.3+. Make a local copy of the tag on
  local disk, never the shared tree, for example `$SRC=/mydata/o31/hadoop-3.4.2`. Build with
  `cd $SRC && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
- **New test class.**
  `$SRC/hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/TestPmemCapO31.java`.
  It goes in the same package as `PmemVolumeManager`, because `reserve`, `chooseVolume`, `release`,
  `getBlockKeyToVolume` and the `PmemMappedBlock` constructor are package-private.
- **Run.** `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestPmemCapO31 -Dsurefire.failIfNoSpecifiedTests=false`.
  Use the default surefire JVM options. Test resources set `dfs.namenode.fs-limits.min-block-size=0`
  (`src/test/resources/hdfs-site.xml:29-32`), so 4 KiB blocks are allowed.
- **Native code.** Not needed. Without PMDK the factory picks the pure-Java `PmemMappableBlockLoader`.
  Record which loader was used from the log line "Initializing cache loader: …".
- **Directories.** Pmem directories go under `MiniDFSCluster.getBaseDirectory()`, which is
  `target/test/data/...` on local disk. Every test calls `PmemVolumeManager.reset()` and
  `PmemVolumeManager.setMaxBytes(-1)` in `@Before` and `@After`, because both are static.

**B2b. Knobs.**
- **U1, direct manager.** Test-hook `setMaxBytes(M)` with M ∈ {65536, 131072} bytes per volume, two
  volumes. Request sizes B ∈ {4096 (divides M), 12288 (does not divide M)}. M and B are set in code.
  These values give exact, hand-checkable boundaries.
- **U1-real.** `setMaxBytes(-1)` (production path). Shows that `maxBytes` equals the directory's
  `getUsableSpace()` at init.
- **U2, MiniDFSCluster end to end.** `setMaxBytes(30720)` per volume, two volumes, `dfs.blocksize=4096`.
  30720 = 7.5 blocks per volume, so the NameNode's total view (60 KiB = 15 blocks) is larger than
  what fits per volume (7 + 7 = 14). This forces the line-407 refusal.
- **U2-control.** `setMaxBytes(32768)` per volume (8 blocks per volume, total 16, no fragmentation).
- **U3, cancel-path accounting.** No knob. It is a fixed sequence.

**B2c. Workload.**
- **U1.** Loop i = 1, 2, …: `long r = mgr.reserve(new ExtendedBlockId(i, "BP-o31"), B)` until
  `r == -1`. Then call `mgr.chooseVolume(B)` once more and catch the `IOException`.
  - M=65536, B=4096: 16 per volume, 32 in total.
  - M=65536, B=12288: floor(65536/12288)=5 per volume, 10 in total, 4096 left per volume.
  - M=131072, B=4096: 64 in total.
  - M=131072, B=12288: 10 per volume (122880 used, 8192 left), 20 in total.
- **U2.**
  - Configuration as in `TestCacheByPmemMappableBlockLoader.setUp`
    (`dfs.namenode.path.based.cache.refresh.interval.ms=100`, `dfs.cachereport.intervalMsec=500`,
    `dfs.heartbeat.interval=1`, `dfs.datanode.fsdatasetcache.max.threads.per.volume=10`,
    `dfs.datanode.pmem.cache.dirs=<base>/pmem0,<base>/pmem1`, `dfs.datanode.pmem.cache.recovery=false`).
  - One DataNode. `DFSTestUtil.createFile(fs, /o31, 24*4096, (short)1, 0xbeef)` makes 24 blocks.
  - `fs.addCachePool(new CachePoolInfo("o31"))`, then a directive on `/o31` with replication 1.
  - Expected: 14 blocks (57344 B) fit; the NameNode's view leaves 61440 − 57344 = 4096 ≥ 4096, so it
    sends a 15th block, which the DataNode refuses.
  - U2-control: 16 blocks (65536 B), then the NameNode stops scheduling.
- **U3.**
  1. `setMaxBytes(65536)`, one volume, `init`.
  2. `reserve(k, 4096)`; write 4096 bytes to `mgr.getCachePath(k)`; `PmemMappedBlock b = new PmemMappedBlock(4096, k)`.
  3. Replay the `finally` order of `FsDatasetCache.java:479-484`: `mgr.release(k, 4096)`, then `b.close()`.
  4. For comparison, the uncache order: `reserve(k2, 4096)`, write file, `new PmemMappedBlock(4096, k2).close()`, then `release(k2, 4096)`.

**B2d. Observables and instruments.**
- **U1.** Number of successful reserves; `mgr.getCacheUsed()`, `mgr.getCacheCapacity()`;
  `mgr.getBlockKeyToVolume()` counted per volume; the exception message from `chooseVolume`.
- **U1-real.** `mgr.getCacheCapacity()` against
  `new File(PmemVolumeManager.getRealPmemDir(d)).getUsableSpace()` for each directory, read right
  after `init`.
- **U2.**
  - DataNode metric `BlocksCached` via `MetricsAsserts.getLongCounter("BlocksCached", getMetrics(dn.getMetrics().name()))`.
  - `cacheManager.getCacheUsed()`, `getCacheCapacity()`, `getNumBlocksFailedToCache()`.
  - The sum of `File.length()` of every regular file under each `<dir>/hdfs_pmem_cache/<bpid>`
    (`FileUtils.listFiles`).
  - The count of log lines containing "There is no enough persistent memory space", captured with
    `GenericTestUtils.LogCapturer.captureLogs(LoggerFactory.getLogger(PmemVolumeManager.class))`.
  - Poll every 500 ms for 20 s after `BlocksCached` stops rising.
- **U3.** `mgr.getCacheUsed()`, `new File(path).exists()` and `.length()`, and a WARN
  "Failed to delete the mapped File: null" captured from the `PmemMappedBlock` logger.
- **Not observable here.** Real pmem hardware behavior, and the native PMDK path unless libhadoop
  has PMDK.

**B2e. Procedure.**
1. Copy the tree, build as in B2a, then add `TestPmemCapO31` with methods `u1Direct` (parameterized
   over the 4 (M,B) pairs), `u1Real`, `u2Fragmented`, `u2Control` and `u3CancelOrder`. Use the
   B2c workloads, plus `assert`s that print the values in B2d before asserting them. Each method
   creates fresh directories under `MiniDFSCluster.getBaseDirectory()+"o31/<method>/pmem{0,1}"`.
2. `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestPmemCapO31`.
3. Save `hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports/*TestPmemCapO31*` (the `.txt` and
   `-output.txt` files).
4. Check that no test JVM is left with `jps | grep surefire`, then remove `target/test/data/o31`.

**B2f. Predictions** (stated before any run).

| Case | Successful reserves | getCacheUsed | Per-volume | Refusal |
|---|---|---|---|---|
| U1 M=65536 B=4096 | 32 | 131072 | 16 / 16 | `chooseVolume` throws, "max available space is 0, but 4096is required" |
| U1 M=65536 B=12288 | 10 | 122880 | 5 / 5 | "max available space is 4096, but 12288is required" |
| U1 M=131072 B=4096 | 64 | 262144 | 32 / 32 | max available 0 |
| U1 M=131072 B=12288 | 20 | 245760 | 10 / 10 | max available 8192 |
| U1-real | — | 0 | capacity = Σ getUsableSpace at init (± any concurrent writes to that file system; tolerance 1 MiB on a busy disk, exact on a dedicated tmpfs) | — |
| U2 fragmented (30720/vol) | BlocksCached = 14 | 57344 | file bytes 28672 / 28672 | ≥ 1 "There is no enough persistent memory space … max available space is 2048, but 4096is required" and `numBlocksFailedToCache` ≥ 1 and rising, one per NameNode rescan |
| U2-control (32768/vol) | 16 | 65536 | 32768 / 32768 | 0 line-407 refusals expected: the NameNode filter stops at 16 |
| U3 cancel order | — | 0 after release | — | file for k still exists with 4096 bytes, WARN "Failed to delete … null". The uncache order (k2) leaves no file. |

The file bytes on disk in every case equal `getCacheUsed` per volume, except in U3.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Reserves and cached bytes match B2f, refusal at the predicted point | Mechanism works as traced; the claim holds at unit level |
| A volume's file bytes or `usedBytes` > its `maxBytes` | Claim refuted: the cap is bypassed |
| U2 caches 15 or 16 blocks with 30720/vol | Claim refuted: blocks are placed without the per-volume check (or a block was split) |
| U2 caches < 14 | Something other than this cap limits caching (thread pool, NameNode filter). Check the logs; not confirmed |
| U2 shows no line-407 refusal but 14 cached | The NameNode filtered instead (its view differed from 61440); the cap holds, but line 407 was not exercised. Rerun with a longer wait |
| U1-real capacity ≠ Σ usable space beyond the tolerance | The source of the cap is mis-traced |
| U3 file remains while used = 0 | The accounting leak on the cancel path is confirmed (A3) |
| U3 file deleted | The leak is not real (re-read the `getCachePath` behavior) |

**B2h. Controls.**
- U2-control (no fragmentation) shows that the NameNode's own filter alone gives exactly 16, so the
  14 in U2 comes from the per-volume check.
- U1 with B dividing M against B not dividing M separates the per-volume check from total capacity.
- `reset()`/`setMaxBytes(-1)` in `@Before` keeps static state from leaking between methods.
- A fresh directory per method rules out recovered files.
- The loader class is logged.

### B3. Cluster tier

**B3a. Environment and build.**
- **Host and daemons.** One Linux host, pseudo-distributed: one NameNode and one DataNode, no YARN.
  JDK 8 (or 11).
- **Build.** From a local copy of the tag:
  `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`. Unpack
  `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `$HH=/mydata/o31/hadoop-3.4.2` (local disk).
  No `-Pnative` is needed: the Java pmem loader is used.
- **Environment.** In `$HH/etc/hadoop/hadoop-env.sh`: `export HADOOP_LOG_DIR=/mydata/o31/logs`,
  `export HADOOP_PID_DIR=/mydata/o31/pids`, `export HADOOP_HEAPSIZE_MAX=1g`.
- **Pmem stand-ins.** tmpfs mounts on local paths (needs sudo):
  `sudo mkdir -p /mydata/o31/pmem0 /mydata/o31/pmem1`, then
  `sudo mount -t tmpfs -o size=<S>,mode=1777 tmpfs /mydata/o31/pmem0` (and `pmem1` for K3).
  - tmpfs uses at most 264 MiB of RAM here.
  - Without tmpfs, use a loop-mounted ext4 image of the same size
    (`fallocate -l <S> /mydata/o31/img0 && mkfs.ext4 -q img0 && sudo mount -o loop img0 /mydata/o31/pmem0 && sudo chmod 1777 /mydata/o31/pmem0`).
    On ext4, journal and metadata overhead lowers `getUsableSpace`, so re-derive the predictions
    from `df -B1 --output=avail` taken just before DataNode start.
- **`core-site.xml`.**
  - `fs.defaultFS=hdfs://localhost:9000`
  - `hadoop.tmp.dir=/mydata/o31/tmp`
- **`hdfs-site.xml`.**
  - `dfs.replication=1`
  - `dfs.namenode.name.dir=/mydata/o31/nn`
  - `dfs.datanode.data.dir=/mydata/o31/dn` (needs at least 1 GiB free)
  - `dfs.datanode.pmem.cache.dirs=/mydata/o31/pmem0` (K3: `/mydata/o31/pmem0,/mydata/o31/pmem1`)
  - `dfs.datanode.pmem.cache.recovery=false`
  - `dfs.namenode.path.based.cache.refresh.interval.ms=2000`
  - `dfs.cachereport.intervalMsec=2000`
  - `dfs.heartbeat.interval=1`
  - `dfs.datanode.max.locked.memory`: leave at the default 0.
- **Ports.** If 9000, 9870, 9864, 9866 or 9867 are busy (`ss -ltn`), move them with `fs.defaultFS`,
  `dfs.namenode.http-address`, `dfs.datanode.http.address`, `dfs.datanode.address` and
  `dfs.datanode.ipc.address`.
- **Start.** `$HH/bin/hdfs namenode -format -force` once, then `$HH/bin/hdfs --daemon start namenode`
  and `$HH/bin/hdfs --daemon start datanode`. No ssh `start-dfs.sh` is needed.

**B3b. Knobs.** Each knob value needs the DataNode stopped, the tmpfs re-mounted at the new size
and the DataNode started again. The key is read only at start.

| Run | pmem dirs | tmpfs sizes | Why |
|---|---|---|---|
| K1 | pmem0 | 136m | 8.5 blocks of 16 MiB: the boundary falls mid-block |
| K2 | pmem0 | 264m | 16.5 blocks: shows usage follows the volume size (positive control for K1) |
| K3 | pmem0, pmem1 | 44m, 204m | 2.75 + 12.75 blocks, total 15.5 blocks: the NameNode sees room for 15, but the per-volume check at line 407 allows only 2 + 12 = 14 |
| K4 | pmem0 | 264m, then 100 MiB filler written into pmem0 (outside `hdfs_pmem_cache`) *after* DataNode start and *before* the directive | stale snapshot: the cap does not follow the shrunk free space |
| K5 | pmem0 | 264m, 100 MiB filler written *before* DataNode start | cap = free space at start (164 MiB → 10 blocks) |

**B3c. Workload.**
- **File.** `head -c 402653184 /dev/urandom > /mydata/o31/in.bin` (384 MiB), then
  `$HH/bin/hdfs dfs -D dfs.blocksize=16777216 -put /mydata/o31/in.bin /o31.bin`, which gives
  24 blocks of 16 MiB.
- **Caching.** `$HH/bin/hdfs cacheadmin -addPool o31pool` (no limit), then
  `$HH/bin/hdfs cacheadmin -addDirective -path /o31.bin -pool o31pool -replication 1`.
- **Arithmetic.** 24 blocks × 16 MiB = 384 MiB, more than every cap (≤ 264 MiB), so every run
  reaches the limit.
- **Duration.** Wait until `BytesCached` is flat for 60 s (about 2–3 min per run). In K3, keep
  sampling for another 60 s to count repeated refusals.
- **Between runs.**
  1. `hdfs cacheadmin -removeDirectives -path /o31.bin`
  2. Stop the DataNode.
  3. `sudo umount` and re-mount the tmpfs.
  4. Start the DataNode.
  5. Re-add the directive.

  The HDFS file is reused.

**B3d. Observables and instruments.** Sample every 5 s into a CSV.
- **DataNode JMX.** `curl -s 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=FSDatasetState*'`,
  fields `CacheCapacity`, `CacheUsed`, `NumBlocksCached`, `NumBlocksFailedToCache`.
- **Disk.** `du -sb /mydata/o31/pmem0/hdfs_pmem_cache /mydata/o31/pmem1/hdfs_pmem_cache` and
  `find … -type f | wc -l`, the actual bytes and number of cache files. Also
  `df -B1 --output=used,avail /mydata/o31/pmem0`.
- **NameNode view.** `hdfs dfsadmin -report`, lines "Configured Cache Capacity" and "Cache Used".
  `hdfs cacheadmin -listDirectives -stats`, columns BYTES_NEEDED and BYTES_CACHED.
- **DataNode log** (`/mydata/o31/logs/hadoop-*-datanode-*.log`):
  - `grep -c "There is no enough persistent memory space"` (line-407 refusals);
  - `grep "Added persistent memory"`, which gives the per-volume `maxBytes` at start
    (`PmemVolumeManager.java:251-252`);
  - `grep -c "could not reserve"`;
  - `grep "Initializing cache loader"`.
- **Not observable directly.** Which check refused a block on the NameNode side (TRACE only). The
  NameNode's "outOfCapacity" decisions are inferred from BYTES_CACHED staying below BYTES_NEEDED with
  no DataNode refusal lines.

**B3e. Procedure.**
1. Build and unpack (B3a). Write the configuration files. Mount pmem0 at 136m (K1).
   Format the NameNode, start the NameNode and the DataNode, and wait for `hdfs dfsadmin -report`
   to show 1 live DataNode.
2. Record "Added persistent memory … size=" from the DataNode log and `CacheCapacity` from JMX.
3. Create and put the file (B3c), add the pool and the directive, and start the 5 s sampler.
4. Wait until settled (B3c). Record the final JMX values, `du`, the file count, the dfsadmin report,
   the directive stats and the log grep counts.
5. For K2 to K5, repeat the steps in "Between runs" (B3c), changing the mounts per B3b.
   - K4: after the DataNode is up and before adding the directive, write the filler
     `head -c 104857600 /dev/zero > /mydata/o31/pmem0/filler`.
   - K5: write the filler before starting the DataNode.
   - Remove the filler before the next run.
6. Clean up per B4.

**B3f. Predictions** (stated before any run; 1 block = 16777216 B; tmpfs usable ≈ size, within a few
pages).

| Run | DataNode `maxBytes` (log) | NumBlocksCached | CacheUsed = `du` of cache files | Line-407 refusals |
|---|---|---|---|---|
| K1 | ≈ 142606336 (136 MiB) | 8 | 134217728 (± dir overhead in `du`, < 64 KiB) | 0 expected: NameNode remaining ≈ 8 MiB < 16 MiB, so it stops scheduling |
| K2 | ≈ 276824064 (264 MiB) | 16 | 268435456 | 0 expected |
| K3 | ≈ 46137344 and ≈ 213909504 | 14 (2 in pmem0, 12 in pmem1) | 234881024 (pmem0 33554432, pmem1 201326592) | ≥ 1 and rising with each rescan; message "max available space is ≈12582912, but 16777216is required"; `NumBlocksFailedToCache` rising; BYTES_CACHED stays at 234881024 |
| K4 | ≈ 276824064 (unchanged by the filler) | < 16: about 10 (164 MiB real room, so 10 blocks); the rest fail in `load` with ENOSPC ("Failed to cache the block"), not at line 407 | ≈ 167772160, never above what tmpfs holds; `CacheCapacity` still ≈ 264 MiB | 0 |
| K5 | ≈ 171966464 (164 MiB) | 10 | 167772160 | 0 expected |

Relation under test: cached bytes per volume = floor(`maxBytes_v` / 16 MiB) × 16 MiB ≤ `maxBytes_v`,
so they follow the tmpfs size at DataNode start.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| K1 = 8, K2 = 16, K5 = 10 blocks, `du` ≤ log `maxBytes` per volume | Claim confirmed: usage follows the volume size at start |
| `du` of a volume > its `maxBytes`, or K3 caches ≥ 15 | Claim refuted |
| K3 = 14 with refusal lines | Per-volume enforcement at line 407 confirmed, including the fragmentation loss |
| K3 = 14 but no refusal lines | Cap held, but via the NameNode filter; line 407 was not exercised (check that the NameNode's reported capacity is ≥ 15 blocks) |
| K4 caches 16 (`du` > tmpfs free) | Impossible on tmpfs; would mean the measurement is wrong |
| K4 ≈ 10 with ENOSPC failures and `CacheCapacity` unchanged | Confirms the stale-snapshot caveat: the cap does not track later free space, and the file system is what stops usage |
| K2 not > K1 (the positive control did not move) | Something else limits caching (pool limit, threads, NameNode filter); the run is not valid |
| Fewer blocks than predicted in K1/K2 with "could not reserve" lines | `maxBytes` is smaller than the tmpfs size (overhead); recompute from the log value before judging |

**B3h. Controls.**
- K2 against K1 is the positive control: the same workload, and the cap moves with the volume size.
- K5 against K2 ties the cap to free space at start rather than mount size.
- K4 separates "the cap follows free space dynamically" from "it is a snapshot".
- K3 isolates the per-volume check from the NameNode's total-capacity filter.
- `dfs.datanode.pmem.cache.recovery=false` plus a fresh mount per run rules out recovered files.
- The pool is created without `-limit`, so the pool cap is not the binding one.
- Replication 1 with one DataNode rules out placement on other nodes.
- Record the loader class (Java expected).

**B4. Risks and cleanup.**
- **Unit tier.** Writes only under `$SRC/.../target/test/data`. Remove `target/test/data/o31`.
  Make sure no surefire JVM remains (`jps`).
- **Cluster tier.**
  - About 384 MiB of HDFS data plus 384 MiB of input on `/mydata/o31`, and up to 264 MiB of RAM in
    tmpfs.
  - Stop and clean in this order:
    1. `hdfs cacheadmin -removeDirectives -path /o31.bin`
    2. `$HH/bin/hdfs --daemon stop datanode`
    3. `$HH/bin/hdfs --daemon stop namenode`
    4. Check `jps` shows no NameNode or DataNode, and kill leftover PIDs from `/mydata/o31/pids`.
    5. `sudo umount /mydata/o31/pmem0 /mydata/o31/pmem1` (or detach the loop devices with
       `losetup -d` and delete the images).
    6. `rm -rf /mydata/o31/{nn,dn,tmp,logs,pids,in.bin}`.
  - Use only local disk; nothing goes on shared storage.
  - Check that the ports are free before starting, so no other user's daemons are disturbed.
  - Never point `dfs.datanode.pmem.cache.dirs` at a directory holding other data: with recovery
    off, the DataNode empties `<dir>/hdfs_pmem_cache` at start (it cleans only that subdirectory,
    `PmemVolumeManager.java:238-241, 268-274`).

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/PmemVolumeManager.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/PmemMappableBlockLoader.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/NativePmemMappableBlockLoader.java (load, lines 82-115)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/MappableBlockLoaderFactory.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetCache.java (140-338, 395-610)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/PmemMappedBlock.java (close)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/NativePmemMappedBlock.java (close)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetUtil.java (deleteMappedFile)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetImpl.java (cacheBlock, getCacheCapacity/Used, MBean registration)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DNConf.java (pmem keys)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataNode.java (maxLockedMemory check)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/BPServiceActor.java (cacheReport, heartbeat)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/CacheReplicationMonitor.java (505-535, 700-760)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/DatanodeInfo.java (getCacheRemaining)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java (482-487)
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml (pmem keys, min-block-size, cache intervals, http address)
- hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/CentralizedCacheManagement.md
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/TestCacheByPmemMappableBlockLoader.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/resources/hdfs-site.xml
- BUILDING.txt (PMDK options)
- https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/CentralizedCacheManagement.html (cited, same text as the markdown)
- https://issues.apache.org/jira/browse/HDFS-13762 (cited as feature background)

## D. Stage-4 feedback

none yet
