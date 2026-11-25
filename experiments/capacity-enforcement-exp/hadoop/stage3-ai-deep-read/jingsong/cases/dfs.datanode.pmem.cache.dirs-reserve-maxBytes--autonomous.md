# dfs.datanode.pmem.cache.dirs — verification solution  <!-- file: cases/dfs.datanode.pmem.cache.dirs-reserve-maxBytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`PmemVolumeManager.java:77`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/PmemVolumeManager.java#L77): `if (next > maxBytes) { return -1; }` in `PmemVolumeManager.UsedBytesCount.reserve(long)` (row unit). The operative gate on the normal path is the identical comparison in `chooseVolume` ([`PmemVolumeManager.java:407`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/PmemVolumeManager.java#L407)); see A3. |
| Pinned source | `rel/release-3.4.2` |
| Session / date | agent, 2026-11-24 |
| Estimate | `positive`: bytes the DataNode writes into its persistent-memory (pmem) cache on each configured directory are reserved against `maxBytes` before any byte is written, and `maxBytes` is the directory's usable space at DataNode start, so the pmem cache on a volume cannot grow past that snapshot. Caveat: the cap is per configured directory, so two directories on one file system double-count the space (A3), and the snapshot is not re-read if others fill the file system later. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**

- **Name:** `dfs.datanode.pmem.cache.dirs` (configuration key), the primary, user-tunable source of the
  limit. The limit value itself is **runtime-queried**: per directory, `maxBytes =
  File.getUsableSpace()` of `<dir>/hdfs_pmem_cache` at DataNode start
  (`PmemVolumeManager.java:243-248`). The user sets the limit by choosing which directory (and so which
  file system, of which size) the key points at. Secondary sources: the static
  `PmemVolumeManager.maxBytesPerPmem` (`PmemVolumeManager.java:129`, default `-1` = "use
  getUsableSpace"), which can only be overridden by the `@VisibleForTesting` `setMaxBytes(long)`
  (`PmemVolumeManager.java:170-173`), not by any configuration; and, with recovery on,
  the bytes of recovered cache files are added back (`PmemVolumeManager.java:305-309`).
- **Kind:** configuration key selecting directories; cap = runtime-queried file-system usable space.
- **Declared:** [`DFSConfigKeys.java:482-483`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java#L482-L483)
  (`DFS_DATANODE_PMEM_CACHE_DIRS_KEY = "dfs.datanode.pmem.cache.dirs"`); no Java default constant.
  `hdfs-default.xml:3001-3008`: value empty, "Multiple directories separated by "," are acceptable."
- **Unit:** the key is a list of paths; the cap is in bytes (per directory).
- **Default:** empty, meaning pmem caching is off and the DRAM loader is used
  (`MappableBlockLoaderFactory.java:42-45`). No conflict between Java and XML (no Java default).
- **How set:** `hdfs-site.xml` on the DataNode. Read once in `DNConf` (`DNConf.java:269-270`); the
  `PmemVolumeManager` is a JVM-wide singleton created once (`PmemVolumeManager.java:148-155`) when the
  `FsDatasetCache` is built (`FsDatasetCache.java:183-186`, `PmemMappableBlockLoader.java:47-51`). Not
  reconfigurable; a change (or a change of the file system's size) needs a DataNode restart.
- **Reader:** DataNode only (the NameNode sees only the resulting cache capacity in heartbeats,
  `BPServiceActor.java:565-566`).

**A2. What it caps.** Bytes of block-replica copies the DataNode writes into the pmem cache
directories (`<dir>/hdfs_pmem_cache/<bpid>/subdirN/subdirM/<blockId>`, `PmemVolumeManager.java:448-469`),
i.e. storage on the pmem device (or, for the pure-Java loader, any mmap-able file system). The quantity
compared is the per-directory `UsedBytesCount.usedBytes`, the sum of the lengths of blocks reserved on
that directory, plus the new block's length (`PmemVolumeManager.java:75-77`).

**A3. Mechanism.**

1. NameNode `CacheReplicationMonitor` picks DataNodes for a cache directive only if
   `pendingBytes + datanode.getCacheRemaining() >= block size` (`CacheReplicationMonitor.java:744-753`);
   the remaining figure derives from the DataNode-reported capacity/used, which here are
   `PmemVolumeManager.getCacheCapacity()` (sum of all `maxBytes`, `PmemVolumeManager.java:142-145`) and
   `getCacheUsed()` (`PmemVolumeManager.java:175-181`). This is a first, NameNode-side gate.
2. The DataNode receives `DNA_CACHE`, `FsDatasetImpl.cache` → `cacheBlock` (`FsDatasetImpl.java:2526-2590`)
   → `FsDatasetCache.cacheBlock` queues a `CachingTask` (`FsDatasetCache.java:272-289`).
3. `CachingTask.run` first calls `cacheLoader.reserve(key, length)` (`FsDatasetCache.java:415`) →
   `PmemMappableBlockLoader.reserve` (`PmemMappableBlockLoader.java:128-131`) →
   `PmemVolumeManager.reserve` (synchronized, `PmemVolumeManager.java:197-210`):
   - `chooseVolume(bytesCount)` walks the directories round-robin and returns the first whose
     `maxBytes - usedBytes >= bytesCount` ([`PmemVolumeManager.java:407`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/PmemVolumeManager.java#L407));
     if none, it throws `IOException("There is no enough persistent memory space ...")`
     (`PmemVolumeManager.java:414-416`), which `reserve` turns into `-1` (`PmemVolumeManager.java:206-208`).
   - Then `UsedBytesCount.reserve` runs the **target check**
     [`if (next > maxBytes)`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/PmemVolumeManager.java#L77)
     in a CAS loop (`PmemVolumeManager.java:73-84`): over the limit → `-1`; otherwise usedBytes is
     advanced atomically and the new total returned.
   - Because `chooseVolume` and the target check apply the same inequality under the same monitor, and
     the only concurrent mutation (`release`, `PmemVolumeManager.java:221-224`, unsynchronized) can only
     lower `usedBytes`, the target check's `-1` branch is defensive on this path: it is reached directly
     only by calling `UsedBytesCount.reserve` (unit tier B2, reflection) or from `recoverCache`, whose
     return value is ignored (`PmemVolumeManager.java:309`).
4. On `-1`, `CachingTask` logs `"Failed to cache <key>: could not reserve more bytes in the cache: <capacity> exceeded ..."`
   and returns before opening the block or creating any cache file (`FsDatasetCache.java:418-423`);
   `finally` increments `numBlocksFailedToCache` and removes the map entry (`FsDatasetCache.java:478-489`).
5. On success, `PmemMappableBlockLoader.load` creates the cache file and copies exactly `length` bytes with
   `transferTo` (`PmemMappableBlockLoader.java:95-97`), verifies checksums, and on any failure deletes the
   file (`PmemMappableBlockLoader.java:107-113`) while `CachingTask` releases the reservation
   (`FsDatasetCache.java:479-481`). Uncaching releases the block's length (`FsDatasetCache.java:562-563`).
6. `maxBytes` is set once, at DataNode start, from `realPmemDir.getUsableSpace()` measured after
   `hdfs_pmem_cache` is created and, if recovery is off, after the directory is cleaned
   (`PmemVolumeManager.java:236-248`, `238-241`).

Paths that bypass or overshoot:

- **Same file system counted twice.** Each configured directory gets its own `maxBytes =
  getUsableSpace()` of its file system (`PmemVolumeManager.java:234-250`), and capacity is their sum
  (`PmemVolumeManager.java:142-145`). Two directories on one file system advertise twice the space; the
  accounting cap then never binds, and the file system itself stops writes with `ENOSPC` inside `load`
  (handled as a failed cache attempt).
- **Snapshot.** `maxBytes` is not re-read. Space taken on that file system by anything else after
  DataNode start is not subtracted; again, only `ENOSPC` stops the copy.
- **Accounting granularity.** Reservations count logical block length, not file-system allocation
  (rounded to file-system blocks) nor the `subdirN/subdirM` directories created per block
  (`PmemVolumeManager.java:456-461`). Overshoot is at most one file-system block per file plus
  directory metadata.
- **Zero-length reservation.** `reserve` stores the volume index only if `usedBytes > 0`
  (`PmemVolumeManager.java:202-204`); not a size overshoot.

**A4. Other consumers.** The DataNode block storage itself (`dfs.datanode.data.dir`) is separate
(the pmem copy is in addition to the on-disk replica). Anything else writing to the same file system
(other processes, a second DataNode with the same directory, a second pmem directory on the same
mount) is outside this accounting. DRAM cache (`dfs.datanode.max.locked.memory`) is disabled when pmem
is used: `initialize` returns `new CacheStats(0L)` (`PmemMappableBlockLoader.java:53-58`). Page cache
from `transferTo` and the DataNode heap are not counted.

**A5. Evidence beyond the source.**
- `hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/CentralizedCacheManagement.md:35-36, 206-230, 262-264`
  (in tree; also https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/CentralizedCacheManagement.html):
  "If this property is configured, the volume capacity will be detected. And there is no need to
  configure `dfs.datanode.max.locked.memory`."; pure-Java implementation is the default, the PMDK one
  is optional.
- Existing test `TestCacheByPmemMappableBlockLoader.java:80-81, 144, 212-305`: sets
  `PmemVolumeManager.setMaxBytes(CACHE_CAPACITY*0.5)` over two bogus directories and checks that a
  further file is not cached once the cache is full. It is skipped unless PMDK is present
  (`TestCacheByPmemMappableBlockLoader.java:108`), although the pure-Java loader needs no PMDK.

## B. Verification solution

**B1. Claim under test.** For each directory in `dfs.datanode.pmem.cache.dirs`, the bytes of cached
block replicas the DataNode holds in that directory (`CacheUsed` per volume and bytes of cache files on
disk) never exceed that directory's `maxBytes`, the usable space measured at DataNode start; requests
beyond it are refused before any byte is written. Corollary to test: with two directories on one file
system, the advertised capacity is about twice the real space, and only `ENOSPC` limits the copies.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 8, Maven 3.3+. Copy the tag to local disk
(`rsync -a <source>/ /mydata/<run>/hadoop-src/`), never build in the shared tree. Build once:
`cd /mydata/<run>/hadoop-src && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
Add a test class `TestPmemCapacityCap.java` in
`hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/`
(same package, so package-private `reserve`, `chooseVolume`, `getBlockKeyToVolume` are callable). Run
with `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestPmemCapacityCap -Dmaven.javadoc.skip=true`.
Default surefire JVM options are enough. Pmem directories: `MiniDFSCluster.getBaseDirectory()+"pmem0"`
etc. (under `target/test/data`, local disk). No native library, no PMDK: the factory then picks the
pure-Java `PmemMappableBlockLoader` (`MappableBlockLoaderFactory.java:46-49`). Each test method starts
and ends with `PmemVolumeManager.reset(); PmemVolumeManager.setMaxBytes(-1);` because the manager and
`maxBytesPerPmem` are static and `init` is a no-op once set (`PmemVolumeManager.java:117, 129, 151`).

**B2b. Knobs.**
- `M` = per-directory cap via `PmemVolumeManager.setMaxBytes(M)` (the only in-JVM way to make the
  runtime-queried value small and exact): `M = 65536` and `M = 131072` (16 and 32 blocks of 4 KiB).
- U2: `setMaxBytes(-1)` (production default path, cap = `getUsableSpace()`), one directory vs two
  directories on the same file system.

**B2c. Workload.**
- **U1 (manager direct).** `PmemVolumeManager.init(new String[]{PMEM0}, false)`; then for
  `i = 1 .. M/4096 + 4`: `r_i = mgr.reserve(new ExtendedBlockId(i, "bp-test"), 4096)`. The first
  `M/4096` reach the cap exactly (16×4096 = 65536); the next 4 are past it. Then
  `mgr.release(new ExtendedBlockId(1,"bp-test"), 4096)` and one more `reserve` of 4096. Then, via
  reflection (`usedBytesCounts` field, `get(0)`, method `reserve(long)` of the nested class
  `PmemVolumeManager$UsedBytesCount`, `setAccessible(true)`), call the target method directly with 1 byte
  while full, to exercise line 77's `-1` branch itself.
- **U2 (runtime-queried cap).** `setMaxBytes(-1)`; `init({PMEM0}, false)`; read
  `getCacheCapacity()` and, immediately after, `new File(PMEM0, "hdfs_pmem_cache").getUsableSpace()`.
  `reset()`; then `init({PMEM0, PMEM1}, false)` with both under the same base directory (same file
  system) and read `getCacheCapacity()` again.
- **U3 (MiniDFSCluster, end-to-end in one JVM).** Configuration as `TestCacheByPmemMappableBlockLoader`
  `setUp` (`:131-151`) but with one pmem directory `PMEM0`, `setMaxBytes(M)`, block size 4096,
  `dfs.namenode.path.based.cache.refresh.interval.ms=100`, `dfs.cachereport.intervalMsec=500`,
  `dfs.heartbeat.interval=1`, `NativeIO.POSIX.setCacheManipulator(new NoMlockCacheManipulator())`, one
  DataNode, no PMDK `assume`. Create `/f1` of 16 blocks (65536 B), replication 1, add pool `p` and a
  directive for `/f1`; wait until `BlocksCached == 16` (30 s timeout). Create `/f2` of 4 blocks (16384 B);
  (a) add a directive for `/f2` and wait 10 s (NameNode gate); (b) bypass the NameNode by calling
  `dn.getFSDataset().cache(bpid, <the 4 block ids of /f2>)` directly and wait 5 s (DataNode gate).

**B2d. Observables and instruments.**
- U1: each `r_i`; `mgr.getCacheUsed()`; `getBlockKeyToVolume().size()`; the reflective call's return.
- U2: `getCacheCapacity()` vs `getUsableSpace()` (bytes).
- U3: `cacheManager.getCacheUsed()` / `getCacheCapacity()` (same as JMX `FSDatasetState` `CacheUsed`,
  `CacheCapacity`, `FsDatasetImpl.java:748-756`); `cacheManager.getNumBlocksFailedToCache()`;
  DataNode metric `BlocksCached`; on-disk bytes: sum of regular-file lengths under
  `PMEM0/hdfs_pmem_cache` (`FileUtils.listFiles(..., TrueFileFilter.INSTANCE, TrueFileFilter.INSTANCE)`),
  sampled every 500 ms during the waits, keep the max; DataNode log lines `could not reserve more bytes`
  (capture with `GenericTestUtils.LogCapturer.captureLogs(FsDatasetCache.LOG)`).
- Not observable directly: whether the NameNode skipped `/f2` for capacity (it logs at TRACE only,
  `CacheReplicationMonitor.java:745-751`); set that logger to TRACE to see `outOfCapacity`.

**B2e. Procedure.**
1. Build (B2a). Write `TestPmemCapacityCap` with methods `u1Direct(M)`, `u2UsableSpace()`,
   `u3MiniCluster(M)`, each wrapped with `reset()`/`setMaxBytes(-1)` before and after, and pmem
   directories created empty with `mkdirs()` and deleted after.
2. Run U1 for `M=65536`, then `M=131072`.
3. Run U2.
4. Run U3 for `M=65536`, then `M=131072` (control, see B2h).
5. Print all readings with `LOG.info` and `assert` the predictions so a failure is visible in the
   surefire report (`target/surefire-reports/...TestPmemCapacityCap-output.txt`).

**B2f. Predictions.**
- U1, `M=65536`: `r_1..r_16 = 4096, 8192, ..., 65536`; `r_17..r_20 = -1`; `getCacheUsed() = 65536`;
  map size 16. After the release: used 61440, next reserve returns 65536. Reflective
  `UsedBytesCount.reserve(1)` when full returns `-1` and `usedBytes` stays 65536.
  `M=131072`: 32 successes, then `-1`; used 131072.
- U2: one directory: `getCacheCapacity()` equals `getUsableSpace()` within 1 MiB on a quiet disk (same
  file system, measured milliseconds apart). Two directories on the same file system:
  `getCacheCapacity()` ≈ 2 × `getUsableSpace()` (within 2 MiB).
- U3, `M=65536`: `BlocksCached = 16`, `CacheUsed = 65536 = CacheCapacity`, on-disk sum = 65536 at
  all samples. (a) after the `/f2` directive: still 16 cached, `CacheUsed` 65536, no new files.
  (b) after the direct `cache()` call: 4 log lines `could not reserve more bytes`,
  `NumBlocksFailedToCache` up by 4, `CacheUsed` 65536, on-disk sum 65536, no file named after any
  `/f2` block id.
  `M=131072` (control): all 16 of `/f1` and the 4 of `/f2` cached; `CacheUsed = 81920`; on-disk sum 81920.
- Claim wrong if: any successful reserve takes `usedBytes` above `M`; `CacheUsed` or on-disk sum ever
  exceeds `M`; a `/f2` cache file appears with `M=65536`; or U2's single-directory capacity differs from
  `getUsableSpace()` by more than ordinary disk churn.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| U1/U3 match B2f (refusal exactly at `M`, used = `M`) | Claim holds at the check: reservation is capped at `maxBytes`. |
| A reserve succeeds with `used + 4096 > M`, or `CacheUsed > M`, or on-disk sum > `M` | Claim wrong: the cap does not bound the pmem cache. |
| U3 (b): `/f2` blocks cached with `M=65536` | DataNode-side gate bypassed; claim wrong. |
| U3 (b): nothing logged and `NumBlocksFailedToCache` unchanged | Direct call did not reach the gate (wrong bpid/ids, or the replica check in `FsDatasetImpl.cacheBlock` rejected it); not confirmed, fix the call. |
| Reflective call returns `-1` when full | Line 77's own refusal works; `-1` returned without state change. |
| U2: one-directory capacity ≈ usable space | Default cap is the runtime-queried usable space, as traced. |
| U2: two-directory capacity ≈ 2 × usable | Double-count path of A3 confirmed (cap overstates the space). |
| U2: two-directory capacity ≈ 1 × usable | The double-count path is wrong; amend A3. |
| `M=131072` control does not move `CacheUsed` to 81920 | Something other than the cap limits caching (thread pool, NameNode); readings for `M=65536` inconclusive. |

**B2h. Controls.**
- `M=131072` run: same workload, cap doubled, caching rises to the full 81920; shows the stop at
  65536 is the cap and not the workload.
- Static-state reset before/after each method (`reset()`, `setMaxBytes(-1)`): otherwise a later
  `init` silently reuses the previous manager and cap.
- On-disk byte count independent of the accounting counters.
- U3 (a) vs (b) separates the NameNode gate from the DataNode gate.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux host, pseudo-distributed: NameNode + one DataNode (HDFS only; YARN not needed). JDK 8 (or 11).
  `sudo` needed only to mount and unmount the small tmpfs used as the pmem directory.
- Build from a local copy: `cd /mydata/<run>/hadoop-src && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`;
  distribution `hadoop-dist/target/hadoop-3.4.2`, copied to `/mydata/<run>/hadoop`. No `-Pnative`
  (the pure-Java pmem loader is used; `dfs.datanode.max.locked.memory` stays `0`, otherwise the DataNode
  refuses to start without native code, `DataNode.java:1892-1897`).
- `etc/hadoop/hadoop-env.sh`: `export JAVA_HOME=...`, `HADOOP_LOG_DIR=/mydata/<run>/logs`,
  `HADOOP_PID_DIR=/mydata/<run>/pid`, `HADOOP_HEAPSIZE_MAX=1g`.
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=/mydata/<run>/tmp`.
- `hdfs-site.xml`: `dfs.replication=1`; `dfs.namenode.name.dir=/mydata/<run>/nn`;
  `dfs.datanode.data.dir=/mydata/<run>/dn`; `dfs.blocksize=33554432` (32 MiB);
  `dfs.datanode.pmem.cache.dirs=/mydata/<run>/pmem0` (runs A/B) or
  `/mydata/<run>/pmem0/a,/mydata/<run>/pmem0/b` (run C); `dfs.datanode.pmem.cache.recovery=false`
  (each restart starts with an empty cache); `dfs.namenode.path.based.cache.refresh.interval.ms=3000`;
  `dfs.cachereport.intervalMsec=3000`; `dfs.datanode.max.locked.memory=0`.
- Pmem stand-in: `sudo mount -t tmpfs -o size=<S>,uid=$(id -u),gid=$(id -g),mode=0755 tmpfs /mydata/<run>/pmem0`
  (RAM-backed; S ≤ 512 MiB). All other data/log directories on local disk under `/mydata/<run>`
  (needs about 2 GiB: 640 MiB input file + 640 MiB block replicas + logs).
- Ports: defaults 9000, 9870, 9864, 9866, 9867; check with `ss -ltn` first and remap
  (`dfs.namenode.http-address`, `dfs.datanode.*address`) if taken.

**B3b. Knobs.** The size `S` of the file system behind the pmem directory, which sets `maxBytes`:
- Run A: `S=256m`; run B: `S=512m` (doubles the cap; 32 MiB blocks give a sharp count boundary).
- Run C: `S=256m` with two configured directories `a`, `b` on the same tmpfs (bypass path).
- Run D (control): `dfs.datanode.pmem.cache.dirs` unset (empty), DRAM cache with locked memory 0.
Each change needs a DataNode restart (`hdfs --daemon stop datanode`, remount, `hdfs --daemon start datanode`);
`maxBytes` is measured only at start.

**B3c. Workload.**
- `head -c 671088640 /dev/urandom > /mydata/<run>/in.bin` (640 MiB = 20 blocks of 32 MiB);
  `hdfs dfs -put /mydata/<run>/in.bin /f`.
- `hdfs cacheadmin -addPool p1` (no pool limit); `hdfs cacheadmin -addDirective -path /f -pool p1 -replication 1`.
- Arithmetic: with `S=256m`, `maxBytes = X ≤ 268435456` (a few KiB less for the `hdfs_pmem_cache`
  directory); 8 blocks need 268435456 > X, so at most `floor(X/33554432) = 7` blocks (234881024 B).
  `S=512m`: `X ≤ 536870912`, at most 15 blocks (503316480 B). The 20-block demand (671088640 B) is past
  the cap in both runs.
- Duration: watch 90 s after the directive (≥ 30 cache rescans at 3 s).

**B3d. Observables and instruments.**
- DataNode log: `grep "Added persistent memory" $HADOOP_LOG_DIR/*datanode*.log` gives `size=<X>` per
  directory (`PmemVolumeManager.java:251-252`) — the cap as measured; `grep -c "could not reserve"`,
  `grep -c "Failed to cache the block"`, `grep -c "No space left"`.
- DataNode JMX every 2 s: `curl -s 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=FSDatasetState-*'`
  → `CacheCapacity`, `CacheUsed`, `NumBlocksCached`, `NumBlocksFailedToCache`.
- Actual bytes on the pmem file system every 2 s: `du -sb --apparent-size /mydata/<run>/pmem0/` (logical),
  `df -B1 /mydata/<run>/pmem0` (Used column, allocated), and `find /mydata/<run>/pmem0 -type f | wc -l`.
- NameNode view: `hdfs cacheadmin -listDirectives -stats` (BYTES_NEEDED, BYTES_CACHED) and
  `hdfs dfsadmin -report` (Configured Cache Capacity, Cache Used).
- Not observable: per-directory `usedBytes` (only the sum is exported); in run C infer per-directory
  use from `du -sb` of `a` and `b`.

**B3e. Procedure.**
1. Build and lay out the distribution and configuration (B3a). `mkdir -p /mydata/<run>/{nn,dn,tmp,logs,pid,pmem0}`.
2. `sudo mount -t tmpfs -o size=256m,uid=$(id -u),gid=$(id -g),mode=0755 tmpfs /mydata/<run>/pmem0`; `df -B1 /mydata/<run>/pmem0`.
3. `hdfs namenode -format -nonInteractive`; `start-dfs.sh` (or `hdfs --daemon start namenode` / `datanode`); `jps`.
4. Record `Added persistent memory ... size=X` and JMX `CacheCapacity`.
5. Start the sampler (JMX + `du` + `df` + file count, every 2 s, to `/mydata/<run>/samples-A.tsv`).
6. Put `/f`, add pool and directive (B3c); wait 90 s; take `hdfs cacheadmin -listDirectives -stats`,
   `hdfs dfsadmin -report`, log counts.
7. `hdfs cacheadmin -removeDirectives -path /f`; wait until `CacheUsed=0` and the pmem directory has no
   block files (uncache works and releases).
8. Run B: `hdfs --daemon stop datanode`; `sudo umount /mydata/<run>/pmem0`; remount with `size=512m`;
   `hdfs --daemon start datanode`; repeat 4–7 (re-add the directive).
9. Run C: stop DataNode; remount `size=256m`; `mkdir /mydata/<run>/pmem0/{a,b}`; set
   `dfs.datanode.pmem.cache.dirs=/mydata/<run>/pmem0/a,/mydata/<run>/pmem0/b`; start DataNode; repeat 4–7.
10. Run D: stop DataNode; remove `dfs.datanode.pmem.cache.dirs`; start; repeat 4–7.
11. Cleanup (B4).

**B3f. Predictions.**
- Run A (`S=256m`): `X` in `[268435456 − 1048576, 268435456]`; `CacheCapacity = X`; final
  `NumBlocksCached = 7`, `CacheUsed = 234881024`; `du --apparent-size` of cache files ≤ X at every sample
  (= 234881024 at the end); BYTES_CACHED 234881024 of BYTES_NEEDED 671088640. No `No space left`.
  Few or no `could not reserve` lines (the NameNode gate normally stops scheduling first).
- Run B (`S=512m`): `X` in `[536870912 − 1048576, 536870912]`; 15 blocks; `CacheUsed = 503316480`;
  ratio B/A of `CacheUsed` = 15/7 ≈ 2.14.
- Run C (two directories on one 256 MiB tmpfs): two `Added persistent memory` lines, each `size≈X`
  (~256 MiB); `CacheCapacity ≈ 2X` (~512 MiB), larger than `df` size. The file system holds at most
  7 complete blocks; further attempts fail inside `load` with `No space left on device` → `Failed to cache
  the block`, `NumBlocksFailedToCache` grows over rescans, `CacheUsed` stays ≤ 7 blocks after releases
  (may transiently show 8 while a failing copy is reserved). Physical use is bounded by the file system,
  not by the advertised cap.
- Run D: `CacheCapacity = 0`, `CacheUsed = 0`, nothing cached.
- Claim wrong if in A or B: `CacheUsed > X`, cache-file bytes > X, or more than `floor(X/32 MiB)` blocks
  cached; or B does not cache more than A.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| A: 7 blocks, B: 15 blocks, cache bytes ≤ X in every sample | Claim confirmed: the pmem cache follows the usable-space cap. |
| A or B: cache bytes or `CacheUsed` > X | Claim wrong: the cap does not bound usage. |
| A and B cache the same count | Something else limits caching (e.g. directive not processed, DataNode cache threads); inconclusive, check logs. |
| A: `No space left` errors appear | Reservations allowed more than the file system had: cap does not bind (or `X` included space not usable by the DataNode user). |
| C: `CacheCapacity ≈ 2X` and ENOSPC failures | Double-count bypass confirmed: the cap is overstated for directories sharing a file system. |
| C: `CacheCapacity ≈ X` | The per-directory double count does not happen; amend A3. |
| D: anything cached | Caching came from another path; runs A–C not attributable to the pmem cap. |

**B3h. Controls.**
- Run B vs A: only `S` changes; the cached amount must move with it.
- Run D: no pmem directory, no locked memory → zero capacity; caching in A–C comes from the pmem path.
- `du --apparent-size` and `df` are independent of the DataNode's own counters.
- Step 7 (uncache to 0) shows releases are accounted, so each run starts from zero.
- `dfs.datanode.pmem.cache.recovery=false` ensures no cache from a previous run is carried into the next
  (the directory is cleaned at start, `PmemVolumeManager.java:238-241`).

**B4. Risks and cleanup.**
- Unit tier: writes only under the local copy's `target/test/data`; static state reset per method;
  `mvn clean` of the module, or delete the copy, afterwards.
- Cluster tier: tmpfs uses RAM up to `S` (≤ 512 MiB); `sudo umount /mydata/<run>/pmem0` at the end.
  Input file and replicas ~1.3 GiB on local disk; `rm -rf /mydata/<run>/{in.bin,nn,dn,tmp}` after.
- Remove the directive and pool (`hdfs cacheadmin -removeDirectives -path /f`, `hdfs cacheadmin -removePool p1`),
  then `stop-dfs.sh` (or `hdfs --daemon stop datanode` / `namenode`); `jps` must show no `NameNode`,
  `DataNode`, `SecondaryNameNode`. Kill the sampler loop.
- Ports: check free before start; nothing on shared storage; no Kerberos.

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/PmemVolumeManager.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/PmemMappableBlockLoader.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/MappableBlockLoaderFactory.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetCache.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetImpl.java (cacheBlock, cache, MBean getters, registerMBean)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetUtil.java (deleteMappedFile)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DNConf.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataNode.java (maxLockedMemory check)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/BPServiceActor.java (cache capacity in heartbeat)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/metrics/FSDatasetMBean.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/CacheReplicationMonitor.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
- hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/CentralizedCacheManagement.md
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/TestCacheByPmemMappableBlockLoader.java
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/nativeio/NativeIO.java (munmap, NoMlockCacheManipulator)
- https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/CentralizedCacheManagement.html (same content as the in-tree markdown; not fetched separately)

## D. Stage-4 feedback

none yet
