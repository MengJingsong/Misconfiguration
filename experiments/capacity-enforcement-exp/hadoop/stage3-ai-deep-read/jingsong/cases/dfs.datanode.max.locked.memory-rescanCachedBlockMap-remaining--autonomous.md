# dfs.datanode.max.locked.memory — verification solution  <!-- file: cases/dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`CacheReplicationMonitor.java:534`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/CacheReplicationMonitor.java#L534) — `if (blockInfo.getNumBytes() > remaining)` in `rescanCachedBlockMap()` (NameNode) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | agent, 2026-11-24 |
| Estimate | `positive` — `remaining` is the DataNode's reported cache capacity minus cache used, and the capacity is `dfs.datanode.max.locked.memory`; the check drops NameNode-scheduled ("pending cached") blocks that would not fit, so the bytes the NameNode asks a DataNode to mlock stay within that limit, and the DataNode's own `CacheStats.reserve` hard-caps the locked bytes at the same value. Locked DataNode memory for caching follows the key. |
| Ground | — |

Parts of the stem: constraint `dfs.datanode.max.locked.memory`; function `rescanCachedBlockMap` (the
method that directly encloses the given if; the hard enforcement point is DataNode-side, see A3);
operand `remaining`.

## A. Constraint trace

**A1. The constraint.**
- Name: `dfs.datanode.max.locked.memory`. Kind: configuration key.
- Declared: [`DFSConfigKeys.java:155`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java#L155)
  (`DFS_DATANODE_MAX_LOCKED_MEMORY_KEY`), default constant `DFS_DATANODE_MAX_LOCKED_MEMORY_DEFAULT = 0`
  at `DFSConfigKeys.java:156`. `hdfs-default.xml:2984-2999` has value `0` and documents
  that 0 disables in-memory caching and that the key has no effect without native libraries. The
  Java constant and the XML agree (0); the XML value is what a `Configuration` loads, both are 0.
- Unit: bytes; read with `Configuration.getLongBytes` (`DNConf.java:265-267`), so size suffixes such
  as `64m`, `1g` are accepted (as the XML says).
- Set in `hdfs-site.xml` of the **DataNode** (or `-D` on the DataNode command line). Not in the
  DataNode's reconfigurable list (`DataNode.java:350-...` does not contain it), so a change needs a
  DataNode restart. The NameNode never reads the key; it learns the value through each heartbeat.
- Startup guards (`DataNode.java:1892-1913`): if > 0, native code must be able to mlock
  (`verifyCanMlock`) and the value must not exceed the process's `RLIMIT_MEMLOCK` (`ulimit -l`),
  else the DataNode aborts.
- Path to the operand: `DNConf.maxLockedMemory` → `new CacheStats(dnConf.getMaxLockedMemory())`
  (`MemoryMappableBlockLoader.java:48`) → `CacheStats.getCacheCapacity()` returns `maxBytes`
  (`CacheStats.java:154-155`) → `FsDatasetCache.getCacheCapacity()` (`FsDatasetCache.java:605-606`) →
  sent in every heartbeat with `getCacheUsed()` (`BPServiceActor.java:563-566`) → NameNode stores them
  on the `DatanodeDescriptor` (`DatanodeDescriptor.java:458-459`) → `DatanodeInfo.getCacheRemaining()
  = cacheCapacity - cacheUsed` (`DatanodeInfo.java:229-230`, hadoop-hdfs-client) →
  `long remaining = dn.getCacheRemaining()` (`CacheReplicationMonitor.java:520`).
- Other sources of the same capacity: if `dfs.datanode.pmem.cache.dirs` is set, the loader is the
  persistent-memory one (`MappableBlockLoaderFactory.java:41-49`) and the capacity is the pmem
  volumes' usable space (`PmemVolumeManager.java:244-249`), not this key. Lazy-persist (RAM_DISK)
  writes reserve from the same `CacheStats` (`FsDatasetImpl.java:3769-3779`), which lowers
  `cacheUsed`-side headroom.

**A2. What it caps.** DataNode off-heap memory that is mmapped **and mlocked** to hold cached HDFS
block replicas (centralized cache management), shared with lazy-persist memory. Quantity compared at
the target line: the length of a pending-cached block (`blockInfo.getNumBytes()`) against the
DataNode's cache headroom as last reported (`remaining`, decremented by each pending block kept).
On the DataNode the compared quantity is page-rounded used bytes plus the new block's page-rounded
length against `maxBytes` (`CacheStats.java:95-106`).

**A3. Mechanism.**
1. NameNode `CacheReplicationMonitor.rescan()` runs every
   `dfs.namenode.path.based.cache.refresh.interval.ms` (default 30000) under the FSN write lock:
   `rescanCacheDirectives()` then `rescanCachedBlockMap()` (`CacheReplicationMonitor.java:305-307`).
2. At the start of `rescanCachedBlockMap()`, for each DataNode, `remaining = dn.getCacheRemaining()`
   (line 520) and the DataNode's pending-cached list is walked (lines 521-542). Blocks unknown to the
   BlockManager are skipped (526-532). The check
   [`if (blockInfo.getNumBytes() > remaining)`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/CacheReplicationMonitor.java#L534):
   - true → the block is removed from the DataNode's PENDING_CACHED list (`it.remove()`, line 538),
     with a DEBUG log "removing from PENDING_CACHED ... because it cannot fit in remaining cache size";
   - false → kept, `remaining -= blockInfo.getNumBytes()` (line 540).
   Net effect: after this loop, the sum of lengths of a DataNode's pending-cached blocks is ≤ its
   reported headroom (when headroom ≤ 0, every pending block is dropped).
3. Later in the same rescan, `addNewPendingCached` (lines 684-784) only adds a DataNode as a target
   when `pendingCapacity = getCacheRemaining() - Σpending-cached + Σpending-uncached ≥ block length`
   (lines 715-753, check at 745). So new scheduling also respects the headroom.
4. Pending-cached lists are turned into `DNA_CACHE` commands in heartbeat replies
   (`DatanodeManager.java:1782-1795`, `getCacheCommand` 2009-2021). `rescan` resets the resend timer
   after every scan (`CacheReplicationMonitor.java:308`), so a still-pending block is re-sent on the next
   heartbeat after each rescan.
5. DataNode: `FsDatasetImpl.cache` → `FsDatasetCache.cacheBlock` (`FsDatasetCache.java:272-289`) →
   `CachingTask.run` calls `cacheLoader.reserve(key, length)` (line 415) → `CacheStats.reserve`
   rounds up to the OS page size and fails (`-1`) if `used + count > maxBytes`
   (`CacheStats.java:95-106`). On failure the block is not cached ("could not reserve more bytes",
   `FsDatasetCache.java:417-422`) and `numBlocksFailedToCache` increments. On success the block file is
   `mmap`ed and `mlock`ed (`MemoryMappableBlockLoader.java:79-80`). This is the hard cap on the
   actual resource; the target check is a NameNode-side planning filter that keeps the plan within it.
- Gaps / overshoot of the NameNode-side check (not of the memory):
  - `remaining` comes from the last heartbeat (stale by up to `dfs.heartbeat.interval`).
  - The NameNode uses raw block lengths; the DataNode page-rounds. A non-page-aligned block (e.g. a
    file's last block) can pass line 534 and then fail `reserve` on the DataNode.
  - Line 534 does not credit pending-uncached bytes (unlike line 744), so it is conservative.
  - Because the DataNode's `cacheUsed` already includes in-flight reservations, blocks the DataNode is
    caching but has not yet reported in a cache report are counted twice (in `cacheUsed` and still in
    pending) and get dropped from pending at line 534; this is harmless (the DataNode finishes them
    and the next cache report marks them CACHED) and stops redundant `DNA_CACHE` resends.
  - Which pending blocks are dropped depends on list order, not on priority.
  - With `max.locked.memory = 0`, capacity is 0, the DataNode sends no cache reports
    (`BPServiceActor.java:492-494`), and nothing is ever scheduled.

**A4. Other consumers.** Outside this constraint's control: DataNode JVM heap and direct buffers;
non-locked OS page cache for block files; client-side mmaps used for zero-copy/short-circuit reads;
any other process's mlocked memory (bounded only by its own `RLIMIT_MEMLOCK`). Inside the same budget:
lazy-persist RAM_DISK replicas (`FsDatasetImpl.java:3769-3779`). With pmem configured, the pmem
volumes (A1). The cache-pool limit check at `CacheReplicationMonitor.java:403` is a separate,
NameNode-side logical byte budget per pool.

**A5. Evidence beyond the source.**
- `hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/CentralizedCacheManagement.md:222-226` (key
  meaning, shared with lazy persist) and `:268-270` (RLIMIT_MEMLOCK); published as
  https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/CentralizedCacheManagement.html
- `hdfs-default.xml:2984-2999`.
- Test `TestCacheDirectives#testExceedsCapacity`
  (`hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestCacheDirectives.java:1525-1547`)
  asserts pending-cached lists are empty once capacity is used up; its harness (lines 114-180) shows the
  `NoMlockCacheManipulator` pattern used below.
- No JIRA relied on.

## B. Verification solution

**B1. Claim under test.** (1) After a rescan, the bytes a NameNode keeps pending-cached for a DataNode
never exceed that DataNode's reported headroom `cacheCapacity − cacheUsed`, where `cacheCapacity` is
`dfs.datanode.max.locked.memory`; blocks that do not fit are dropped from pending at line 534.
(2) As a result, and enforced again on the DataNode, the bytes the DataNode locks for caching stay
≤ `dfs.datanode.max.locked.memory`, and track it as the key is varied while the workload exceeds it.

### B2. Unit tier

**B2a. Environment and build.** *[Amended 2026-11-25 (A1: node paths, no `install`, surefire counts; A9: node `pc72`, run folder); see D1.]* JDK 8, Maven 3.3+. Copy the tree to local disk
(`rsync -a ~/hadoop-3.4.2/ /mydata/<run>/src/`), never build in the shared tree. Build:
`cd /mydata/<run>/src && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
New test file in the copy:
`hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestCrmPendingFit.java`
(package `org.apache.hadoop.hdfs.server.namenode`). Run:
`mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestCrmPendingFit -DfailIfNoTests=false`.
No native code needed: install `NativeIO.POSIX.NoMlockCacheManipulator` as in `TestCacheDirectives`
(static block and `setup()`), which reports page size 4096, memlock limit ~1 PiB and `verifyCanMlock=true`.
Test resources already set `dfs.namenode.fs-limits.min-block-size=0`
(`hadoop-hdfs/src/test/resources/hdfs-site.xml:30-31`).

Configuration (copy of `TestCacheDirectives.createCachingConf`, lines 124-136, with 1 DataNode):
`dfs.blocksize=4096`, `dfs.datanode.max.locked.memory=C`, `dfs.heartbeat.interval=1`,
`dfs.cachereport.intervalMsec=1000`, `dfs.namenode.path.based.cache.refresh.interval.ms=1000`.
`MiniDFSCluster.Builder(conf).numDataNodes(1)`.

**B2b. Knobs.**
- K1 (the key) `C = dfs.datanode.max.locked.memory` ∈ {16384, 32768, 65536} bytes (4, 8, 16 blocks of
  4096), set in the test `Configuration` before building the cluster (one cluster per value).
- K2 (headroom at the NameNode, drives line 534 directly) with C = 65536: the NameNode's recorded
  `cacheUsed` U ∈ {0, 16384, 32768, 49152, 65536, 81920}, set by
  `descriptor.setCacheUsed(U)` (public setter, `DatanodeInfo.java:302`) under
  `cluster.getNamesystem().writeLock()` / `writeUnlock()`, while the DataNode's heartbeats are disabled
  so no heartbeat overwrites it. Second variant: `descriptor.setCacheCapacity(C')` with
  C' ∈ {65536, 32768, 0} and U = 0.

**B2c. Workload.** One file `/f`, length 131072 (32 blocks of 4096 bytes, page-aligned), replication 1:
`DFSTestUtil.createFile(dfs, new Path("/f"), 4096, 131072, 4096, (short)1, 0xFADED)`. Pool `p`
(default limit unlimited, `CachePoolInfo.java:54-55`), directive path `/f`, replication 1. Demand
131072 > every C, so the cap is always reached.

**B2d. Observables and instruments.** *[Amended 2026-11-25 (A3: line-534 DEBUG lines captured; Test A max and failures recorded; A11: DataNode reserve-refusal lines; A12: DEBUG-capture check); see D1.]*
- NameNode pending bytes for the DataNode: under `readLock`, iterate
  `descriptor.getPendingCached()` and sum `blockManager.getStoredBlock(new Block(id)).getNumBytes()`;
  also its size. `descriptor = datanodeManager.getDatanode(dn.getDatanodeId())`.
- NameNode headroom: `descriptor.getCacheRemaining()`.
- DataNode actual cache accounting: `dn.getFSDataset().getCacheUsed()`, `getCacheCapacity()`,
  `getNumBlocksCached()`, `getNumBlocksFailedToCache()` (FSDatasetMBean).
- Directive stats: `dfs.listCacheDirectives(null)` → `getStats().getBytesCached()`.
- Wait for rescans with `GenericTestUtils.waitFor` (poll 100 ms, timeout 10 s) or sleep 3 s (3 rescan
  intervals). Not observable: real mlocked pages (mlock is stubbed here) — that is B3's job.

**B2e. Procedure.** *[Amended 2026-11-25 (A2: one fresh cluster per K2 value; A10: settle rule for Tests A and C); see D1.]*
1. Test A (cap, per C in K1): build cluster; create `/f`; add pool and directive; wait until
   `getNumBlocksCached()` stops changing for 3 s (≤ 30 s). Record DN `getCacheUsed()`,
   `getNumBlocksCached()`, `getNumBlocksFailedToCache()`, directive bytesCached, NameNode Σpending.
   Shut down.
2. Test B (line 534, per U in K2): build cluster with C=65536; wait until
   `descriptor.getCacheCapacity() == 65536` (first heartbeat in);
   `DataNodeTestUtils.setHeartbeatsDisabledForTests(dn, true)`; create `/f`; add pool and directive; wait
   3 s; record Σpending (P0) and size. Then under writeLock `descriptor.setCacheUsed(U)`; wait 3 s; record
   Σpending (P1), size, `getCacheRemaining()`. Then repeat the wait once more and record P2 (stability).
   For the C' variant, use `setCacheCapacity(C')` instead.
3. Test C (hand-back, same cluster as B with U=49152): `setHeartbeatsDisabledForTests(dn, false)`;
   `DataNodeTestUtils.triggerHeartbeat(dn)`; wait until DN `getNumBlocksCached()` stable 3 s; record DN
   `getCacheUsed()`.
4. Ablation (optional, control for 534 specifically): in a second copy of the tree, change line 534 to
   `if (false && blockInfo.getNumBytes() > remaining)`, rebuild hadoop-hdfs, rerun Test B for U=49152.
5. Shut down every cluster in `@After`; restore the cache manipulator.

**B2f. Predictions.** *[Amended 2026-11-25 (A3: DEBUG-line counts predicted; A11: no reserve refusals); see D1.]*
- Test A: DN `getCacheUsed()` = C exactly (16384 / 32768 / 65536); blocks cached = C/4096 (4 / 8 / 16);
  directive bytesCached = C; NameNode Σpending = 0 at the end; never `getCacheUsed() > C`.
- Test B: P0 = 65536 (16 blocks; line 745 fills pending to headroom). After U:
  | U | headroom | P1 = P2 (bytes / blocks) |
  |---|---|---|
  | 0 | 65536 | 65536 / 16 |
  | 16384 | 49152 | 49152 / 12 |
  | 32768 | 32768 | 32768 / 8 |
  | 49152 | 16384 | 16384 / 4 |
  | 65536 | 0 | 0 / 0 |
  | 81920 | −16384 | 0 / 0 |
  Variant C' = 32768 → 32768 / 8; C' = 0 → 0 / 0. In general P1 = 4096·max(0, ⌊(C−U)/4096⌋).
- Test C: DN `getCacheUsed()` = 65536 (the real headroom is restored by the first heartbeat).
- Ablation: P1 stays 65536 for U=49152 (no other code removes pending entries before a cache report
  marks them cached).

**B2g. Readings.** *[Amended 2026-11-25 (A4: rows added; A11: the A4 failures row replaced; A12: validity row); see D1.]*
| Observation | Meaning |
|---|---|
| Test B P1 equals the table (Σpending ≤ headroom) and P2 = P1 | Line 534 enforces the reported headroom; claim (1) holds |
| Test B P1 = P0 after U is raised | Line 534 is not effective; claim (1) refuted |
| Test B P1 < predicted by more than one block | Over-eager drop (e.g. page rounding or ordering not as traced); claim partly wrong, re-read A3 |
| Test A `getCacheUsed()` = C for all C, blocks = C/4096 | DataNode caching follows the key; claim (2) holds at the accounting level |
| Test A `getCacheUsed()` > C for any C | Cap breached; claim (2) refuted |
| Test A `getCacheUsed()` < C with failures and pending empty | Cap binds but under-fills; note, not a refutation |
| Ablation P1 = 65536 while unpatched P1 = 16384 | The difference is due to line 534 alone |
| Ablation P1 = 16384 too | Some other path removes pending; line 534 is redundant for this scenario |

**B2h. Controls.** Baseline in Test B (U=0) shows that the setter and wait alone do not change the
pending set. Heartbeats disabled during B so `cacheUsed` is exactly the knob, not a DataNode report.
Page-aligned blocks remove the NN/DN rounding difference. Test A with three C values shows a dose
response, not a constant. The ablation isolates line 534 from line 745.

### B3. Cluster tier

**B3a. Environment and build.** *[Amended 2026-11-25 (A5: base distribution + native libhadoop on pc99; memlock check; A9: on `pc72`); see D1.]* One Linux host, pseudo-distributed: 1 NameNode, 1 DataNode (no YARN).
JDK 8, Maven 3.3+, and for native code `build-essential cmake zlib1g-dev pkg-config libssl-dev`
(`BUILDING.txt:64`). Native libhadoop is required (`DataNode.java:1892-1898`).
- Build in a local copy: `cd /mydata/<run>/src && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`
  (`BUILDING.txt:364-368`); then the native library only for hadoop-common:
  `mvn -pl hadoop-common-project/hadoop-common package -Pnative -DskipTests -Dmaven.javadoc.skip=true`
  and copy `hadoop-common-project/hadoop-common/target/native/target/usr/local/lib/libhadoop.so*` into
  `$HADOOP_HOME/lib/native/`, where `HADOOP_HOME=/mydata/<run>/hadoop-3.4.2` (untarred from
  `hadoop-dist/target/hadoop-3.4.2.tar.gz`). Check `hadoop checknative -a` reports `hadoop: true`.
- `hadoop-env.sh`: `HADOOP_LOG_DIR=/mydata/<run>/logs`, `HADOOP_PID_DIR=/mydata/<run>/pids`,
  `HDFS_NAMENODE_OPTS="-Xmx1g"`, `HDFS_DATANODE_OPTS="-Xmx1g"`.
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=/mydata/<run>/tmp`.
- `hdfs-site.xml`: `dfs.replication=1`, `dfs.namenode.name.dir=/mydata/<run>/nn`,
  `dfs.datanode.data.dir=/mydata/<run>/dn`, `dfs.blocksize=16m`, `dfs.heartbeat.interval=1`,
  `dfs.namenode.path.based.cache.refresh.interval.ms=1000`, `dfs.cachereport.intervalMsec=10000`
  (phase 1) or `60000` (phase 2), `dfs.datanode.max.locked.memory=<M>` (knob).
- Memory lock limit: before starting the DataNode, raise the starting shell's limit:
  `sudo prlimit --memlock=unlimited:unlimited --pid $$` (children inherit; nothing changed outside
  this shell). Check `ulimit -l` prints `unlimited`.
- Disk: ≤ 2 GiB under `/mydata/<run>`. Host RAM: NN 1 GiB + DN 1 GiB + up to 1 GiB locked; need ≥ 4 GiB free.

**B3b. Knobs.** `dfs.datanode.max.locked.memory` M ∈ {64m, 128m, 256m} (4, 8, 16 blocks of 16 MiB),
plus controls M = 0 and M = 1g (above demand). Set in `hdfs-site.xml`; DataNode restart required
(`hdfs --daemon stop datanode; hdfs --daemon start datanode` from the prlimit shell). Between values,
remove the directive and wait until CacheUsed is 0, or restart both daemons.

**B3c. Workload.** `hdfs dfs -mkdir /cap`;
`head -c 536870912 /dev/urandom > /mydata/<run>/f512 && hdfs dfs -put /mydata/<run>/f512 /cap/f512`
(512 MiB = 32 blocks of 16 MiB, page-aligned). `hdfs cacheadmin -addPool p`;
`hdfs cacheadmin -addDirective -path /cap/f512 -pool p -replication 1`. Demand 512 MiB > 64/128/256 MiB,
so each cap is reached; 1g is above demand. Duration ≈ 60 s per value (90 s in phase 2).

**B3d. Observables and instruments.** *[Amended 2026-11-25 (A6, A7: sampling cadence, cache-report timing; A9: log time zone; A11: reserve-refusal lines; A12: DEBUG check); see D1.]*
- Actual locked memory: `grep VmLck /proc/$(cat /mydata/<run>/pids/hadoop-$USER-datanode.pid)/status`,
  every 1 s, before the directive (baseline) and for 60 s after.
- DataNode accounting: `curl -s 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=FSDatasetState-*'`
  → `CacheUsed`, `CacheCapacity`, `NumBlocksCached`, `NumBlocksFailedToCache` (bean name from
  `FsDatasetImpl.java:2647`), every 1 s.
- NameNode view: `hdfs dfsadmin -report` (Configured Cache Capacity, Cache Used, Cache Remaining) and
  `hdfs cacheadmin -listDirectives -stats` (BYTES_NEEDED, BYTES_CACHED, FILES_CACHED), every 5 s.
- Line 534 firing (phase 2): before the directive,
  `hadoop daemonlog -setlevel localhost:9870 org.apache.hadoop.hdfs.server.blockmanagement.CacheReplicationMonitor DEBUG`;
  count NameNode log lines containing `because it cannot fit in remaining cache size` and the distinct
  block ids in them. Count DataNode log lines `DatanodeCommand action: DNA_CACHE`
  (`BPOfferService.java:750`) and their block ids.
- Not observable directly: the NameNode's pending-cached list (no metric); inferred from the
  `DNA_CACHE` resend pattern (A3 step 4).

**B3e. Procedure.** *[Amended 2026-11-25 (A6, A7: pool once, plateau rule, phase-2 timing); see D1.]*
1. Build and unpack (B3a); `hdfs namenode -format -force`; open the prlimit shell; `hdfs --daemon start namenode`;
   `hdfs --daemon start datanode`; check `hdfs dfsadmin -report` shows Configured Cache Capacity = M.
2. Phase 1, for each M in {0, 64m, 128m, 256m, 1g}: write `/cap/f512` (once), record baseline VmLck,
   add pool and directive, sample for 60 s, record final VmLck, CacheUsed, NumBlocksCached,
   NumBlocksFailedToCache, BYTES_CACHED. `hdfs cacheadmin -removeDirectives -path /cap/f512`; wait until
   CacheUsed = 0 and VmLck back to baseline; stop DataNode; change M; start DataNode; repeat.
3. Phase 2 (line 534), M = 128m, `dfs.cachereport.intervalMsec=60000`, restart both daemons; set the
   CRM DEBUG level; add the directive; sample 90 s; collect the log counts of B3d.
4. Cleanup: `hdfs cacheadmin -removePool p`; `hdfs --daemon stop datanode`; `hdfs --daemon stop namenode`;
   `jps` shows neither; `rm -rf /mydata/<run>/{nn,dn,tmp,f512}` (keep logs for the record).

**B3f. Predictions.** *[Amended 2026-11-25 (A7: phase-2 window defined; A11: no reserve refusals); see D1.]*
- Phase 1:
  | M | CacheUsed (final) | NumBlocksCached | BYTES_CACHED | VmLck − baseline |
  |---|---|---|---|---|
  | 0 | 0 (no cache reports) | 0 | 0 | ≈ 0 |
  | 64m | 67108864 | 4 | 67108864 | ≈ 65536 kB (± 1 MiB) |
  | 128m | 134217728 | 8 | 134217728 | ≈ 131072 kB |
  | 256m | 268435456 | 16 | 268435456 | ≈ 262144 kB |
  | 1g | 536870912 | 32 | 536870912 | ≈ 524288 kB |
  At no sample CacheUsed > M or VmLck − baseline > M + 1 MiB.
- Phase 2: within ≈ 3 s of the directive, the NameNode logs "cannot fit in remaining cache size" for
  between 1 and 8 distinct block ids (typically all 8: the DataNode's heartbeat reports CacheUsed =
  128 MiB, Cache Remaining = 0, while those blocks are still pending until the 60 s cache report);
  the DataNode logs only 1–3 `DNA_CACHE` lines in the first 60 s, not one per rescan (≈ 60), and no
  block id beyond the first 8; final CacheUsed = 134217728 and VmLck ≈ 131072 kB above baseline.

**B3g. Readings.** *[Amended 2026-11-25 (A8: rows added; A11, A12: rows added); see D1.]*
| Observation | Meaning |
|---|---|
| CacheUsed and VmLck rise to M and stop, for each capped M, and to 512 MiB for M = 1g | Locked memory follows the key; claim (2) holds |
| VmLck − baseline > M + 1 MiB, or CacheUsed > M, for any capped M | Cap breached; claim refuted |
| Same values for all M | The key does not govern usage; claim refuted |
| M = 1g does not exceed 256 MiB | Workload or host limit, not the key, bounded usage; result not confirmed |
| Phase 2: "cannot fit" lines appear and `DNA_CACHE` stops after 1–3 commands | Line 534 drops pending blocks once headroom is used; claim (1) holds |
| Phase 2: no "cannot fit" lines and `DNA_CACHE` repeats about once per second until the cache report | Line 534 not effective in a real cluster; claim (1) refuted |
| Phase 2: `DNA_CACHE` carries more than 8 distinct block ids | NameNode plan exceeded the headroom; claim (1) refuted |

**B3h. Controls.** M = 0 (caching off) and M = 1g (above demand) bracket the capped values and show the
same workload moves locked memory when the cap is not binding. Baseline VmLck before each directive
removes JVM or other locked pages. Page-aligned 16 MiB blocks avoid NameNode/DataNode rounding
differences. Phase 2 with a long cache-report interval separates line 534 (which acts on heartbeat
headroom) from the `numCached >= neededCached` cleanup (which needs a cache report).

**B4. Risks and cleanup.** Unit tier: build output only in the local copy; MiniDFSCluster data under
the module's `target/test/data`; delete the copy afterwards. Cluster tier: up to 1 GiB of mlocked memory
(released on directive removal or DataNode stop); keep M ≤ free RAM − 3 GiB. Ports 9000, 9870, 9864,
9866, 9867 must be free; check with `ss -ltnp` first. The prlimit change applies to one shell only.
Stop all daemons and check `jps`; remove `/mydata/<run>/{nn,dn,tmp,f512}`.

## C. Sources read

hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/CacheReplicationMonitor.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/DatanodeDescriptor.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/DatanodeManager.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/HeartbeatManager.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/DatanodeInfo.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/CachePoolInfo.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DNConf.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataNode.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/BPServiceActor.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/BPOfferService.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetCache.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetImpl.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/CacheStats.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/MemoryMappableBlockLoader.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/MappableBlockLoaderFactory.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/PmemVolumeManager.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/metrics/FSDatasetMBean.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/CacheManager.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/tools/CacheAdmin.java
hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/CentralizedCacheManagement.md
hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestCacheDirectives.java
hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/DataNodeTestUtils.java
hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/DFSTestUtil.java
hadoop-hdfs-project/hadoop-hdfs/src/test/resources/hdfs-site.xml
BUILDING.txt
https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/CentralizedCacheManagement.html (published form of the .md above; content relied on from the tree)

## D. Stage-4 feedback

### D1. Stage-4 audit amendments (2026-11-25, before any harness run or reading)

Made by the stage-4 agent (run 1, node `pc99`) during the design audit, before the freeze. None changes B1, and none depends
on a reading. A1, A2, A5, A6 make the runbook runnable and exact on the node; A3 and A7 make the disallow-branch evidence
and the phase-2 observation window exact; A4 and A8 add the conclusions rows the audit found missing.

- **A1 (B2a).** On `pc99`: the case copy is `/mydata/jingsong-s4/<stem>-run1/src`, made by
  `experiments/capacity-enforcement-exp/hadoop/stage4-runtime-verification/jingsong/copy-source.sh` from the repository's
  `systems/hadoop/source/` (never built in). No `install` step: the node's `~/.m2` holds the 3.4.2 artifacts of the base
  build. `JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64`. Run:
  `mvn -B -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestCrmPendingFit -DfailIfNoTests=false -Dmaven.javadoc.skip=true`;
  surefire counts, not the exit code, are authoritative.
- **A2 (B2e Test B).** One fresh `MiniDFSCluster` per K2 value (six U values; three C' values 65536, 32768, 0), the same
  steps each time, so each instance starts from the same P0 and heartbeats are off for under 15 s (stale interval 30 s).
  Test C runs on the U = 49152 instance. The ablation (step 4) runs the same U = 49152 method in a second copy
  `/mydata/jingsong-s4/<stem>-run1/src-ablate`.
- **A3 (B2d, B2f).** Direct evidence of line 534: the `CacheReplicationMonitor` logger is set to DEBUG and captured
  (`GenericTestUtils.LogCapturer`); counted are the lines `Block <id>: removing from PENDING_CACHED for node <dn> because it
  cannot fit in remaining cache size <r>` and their distinct block ids, in three windows of each Test B instance: before the
  change (pre: directive added → P0), change → P1 (w1), P1 → P2 (w2). Prediction (from A3 steps 2–3 with page-aligned
  blocks): pre = 0 lines; w1 distinct ids = 16 − P1/4096, i.e. 0 / 4 / 8 / 12 / 16 / 16 for U = 0 / 16384 / 32768 / 49152 /
  65536 / 81920 and 0 / 8 / 16 for C' = 65536 / 32768 / 0, each id once; w2 = 0 lines. Ablation: w1 = 0 lines. Test A also
  records the maximum DN `getCacheUsed()` polled every 100 ms during the wait (predicted ≤ C) and `getNumBlocksFailedToCache()`.
- **A4 (B2g), rows added.**
  | Observation | Meaning |
  |---|---|
  | P0 ≠ 65536, or the U = 0 / C' = 65536 rows give P1 ≠ 65536 | Setup invalid; Test B gives no verdict |
  | P1 as in the table but no w1 "cannot fit" lines | Pending removed by another path; claim (1) not confirmed |
  | P1 as in the table, w1 lines present but their distinct ids ≠ 16 − P1/4096 | Line 534 fires, but not as traced; claim (1) partly confirmed, re-read A3 |
  | P2 ≠ P1, or w2 lines > 0 | Pending set not stable; claim (1) not confirmed |
  | Test A not settled within 30 s | Claim (2) not confirmed at the unit tier |
  | Test A `NumBlocksFailedToCache` > 0 with `getCacheUsed()` ≤ C | The DataNode's reserve (A3 step 5) caught a plan beyond its headroom; claim (2) holds, noted against (1) |
  | Test C `getCacheUsed()` ≠ 65536 | Hand-back not shown; note, does not refute (1) |
  A unit-tier confirmation needs Test B as in the table **and** the w1 ids **and** Test A as predicted.
- **A5 (B3a).** No full build in the case copy: the cluster uses a copy of the node's base distribution
  `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` (built 2026-11-24 from the same source) plus
  `libhadoop.so*` from `mvn -pl hadoop-common-project/hadoop-common package -Pnative -DskipTests` in the case copy
  (`cmake`, `zlib1g-dev`, `libssl-dev`, `pkg-config` installed with `apt` on `pc99`, where they were absent; `lib/native`
  created in the copy). Configuration, logs, PIDs and data under `/mydata/jingsong-s4/<stem>-run1/cluster/`; daemons with
  `hdfs --daemon` (SSH to localhost does not work on the node). `ulimit -l` on `pc99` is 16492916 kB (> 1 GiB): the
  `prlimit` step is replaced by the check `ulimit -l` ≥ 1048577 kB; no limit is changed.
- **A6 (B3d, B3e step 2).** Pool `p` is added once, before the first M (a second `-addPool p` would fail); between values
  only the directive is removed, then the run waits until JMX `CacheUsed` = 0 and `VmLck` = baseline, restarts the
  DataNode with the next M and waits until `dfsadmin -report` shows Configured Cache Capacity = M. M = 0 runs first.
  Sampling: `VmLck` and JMX every 1 s; `cacheadmin -listDirectives -stats` and `dfsadmin -report` every 5 s. Plateau: at
  least 60 s and the last 10 s of (CacheUsed, NumBlocksCached, VmLck, BYTES_CACHED) unchanged; at most 120 s (else
  `settled = false`). "Final" is the last sample, "max" the maximum over the phase. The CRM DEBUG level is set from the start
  (also in phase 1).
- **A7 (B3d, B3e step 3, B3f phase 2).** A DataNode sends its first cache report on its first service loop
  (`lastCacheReport = 0`, `BPServiceActor.java:498`), then every `dfs.cachereport.intervalMsec`, and a cache report ends
  pending-cached for the blocks it lists (`CacheManager.java:1065-1066`). The phase-2 window is therefore from the
  directive to the first cache report after it. The directive is added 8 s after the first cache report that follows the
  restart (DataNodeActivity `CacheReportsNumOps`, sampled every 1 s), so the window is about 50 s; the phase samples 90 s.
  B3f's "1–3 `DNA_CACHE` lines in the first 60 s" is read as: DNA_CACHE lines before that cache report; "no block id beyond
  the first 8" as: ≤ 8 distinct block ids in all DNA_CACHE lines of the phase. "Cannot fit" lines are counted from the
  directive on.
- **A8 (B3g), rows added.**
  | Observation | Meaning |
  |---|---|
  | CacheUsed ≤ M but VmLck − baseline > M + 1 MiB for a capped M | Counter capped, real resource not; claim (2) refuted |
  | CacheUsed = M but VmLck − baseline < M − 1 MiB | Instrument gap; claim (2) holds on the counter only (partly) |
  | M = 0: anything cached or locked | Claim refuted (0 disables caching) |
  | A capped M not settled within 120 s | That value not confirmed |
  | Phase 2: window (directive → next cache report) < 20 s | Phase 2 not decisive; re-run it once, else claim (1) not confirmed at this tier |
  | Phase 2: "cannot fit" lines present but more than 3 DNA_CACHE lines in the window | Mixed; claim (1) not confirmed |
  A cluster-tier confirmation needs phase 1 (ceiling follows M, never above it) **and** phase 2's "cannot fit" lines with
  the DNA_CACHE pattern.

### D1b. Stage-4 audit amendments for the retry on `pc72` (2026-11-25, before any harness run or reading)

The first stage-4 attempt (node `pc99`, 2026-11-25) wrote A1–A8 and a harness but never ran (stale node lock). A fresh
stage-4 agent re-audited the design and that harness on 2026-11-25 for a run on `pc72` and made A9–A12 before any test,
daemon or sampler ran (only the source copy, the `apt` install, the native `hadoop-common` build and a test-compile had
run, none of which produces a reading). None changes B1. A9 and A10 make the runbook runnable and exact; A11 replaces
one A4 row whose evidence was not specific (source reason below) and adds the matching prediction and cluster row; A12
adds the instrument check the DEBUG-based rows depend on.

- **A9 (B2a, B3a, A1, A2, A5).** Node `pc72` (`node2.jason92-326665`, Ubuntu 22.04.2, 125 GiB, `ulimit -l` 16492912 kB) in
  place of `pc99`. Run folder `/mydata/jingsong-s4/dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining-run1/`
  in place of `/mydata/jingsong-s4/<stem>-run1/` wherever A1, A2 and A5 name it (`src/`, `src-ablate/`, `cluster/`,
  `logs/`). `cmake`, `zlib1g-dev`, `libssl-dev`, `pkg-config` were absent on `pc72` too and are installed with `apt` (A5).
  The ablation copy runs the whole `testB_U49152` method, so it also prints a Test C line; that line has no prediction
  and is reported only. Daemon log timestamps are in UTC (the JVM reads `/etc/timezone` = `Etc/UTC`) while the node's
  shell clock is MST (`/etc/localtime`); the sampler converts log times to epoch seconds before comparing them with sample
  times (used for the phase-2 window of A7).
- **A10 (B2e steps 1 and 3).** "Wait until `getNumBlocksCached()` stops changing for 3 s (≤ 30 s)" becomes: poll every
  100 ms; settled when at least 10 s have passed since the directive (Test A) or since heartbeats were re-enabled (Test C)
  **and** the count has not changed for the last 3 s; at most 30 s (else `settled = false`). Reason (source, no reading):
  the first `DNA_CACHE` needs a rescan (≤ 1 s, `refresh.interval.ms`) and then a heartbeat (≤ 1 s), and the NameNode
  re-sends pending blocks only after the next rescan (`CacheReplicationMonitor.java:309`), so a 3-s rule can settle at 0
  blocks, or between the first and second command of Test C, before caching has run.
- **A11 (B2d, B2f, B2g, B3d, B3f, B3g).** `NumBlocksFailedToCache` is incremented both for a reserve refusal
  (`FsDatasetCache.java:415-422`, WARN "Failed to cache …: could not reserve more bytes in the cache" at 419, counter at 485) and for a
  `DNA_CACHE` of a block that is already caching or cached (`FsDatasetCache.java:276-282`), which happens whenever the
  NameNode re-sends a still-pending block (A3 step 4). The counter alone therefore does not show a refusal.
  Observable added: the DataNode's "could not reserve more bytes in the cache" lines (unit: `LogCapturer` on the
  `FsDatasetCache` logger for each Test A / B / C instance; cluster: DataNode log lines from each phase's start).
  Prediction added: **0 such lines** in every Test A row, Test B row, Test C, every phase-1 value and phase 2 (the
  NameNode never plans beyond the reported headroom, and with page-aligned blocks it plans no block the DataNode's
  page-rounded reserve would refuse; A3 step 5). `NumBlocksFailedToCache` is recorded and not predicted.
  The A4 row "Test A `NumBlocksFailedToCache` > 0 with `getCacheUsed()` ≤ C" is **replaced** by:
  | Observation | Meaning |
  |---|---|
  | Test A or C: "could not reserve" lines > 0 with `getCacheUsed()` ≤ C | The DataNode's reserve (A3 step 5) caught a plan beyond its headroom; claim (2) holds, noted against (1) |
  | `NumBlocksFailedToCache` > 0 with 0 "could not reserve" lines | Duplicate cache commands (`FsDatasetCache.java:276-282`); no bearing on either claim |
  B3g row added:
  | Observation | Meaning |
  |---|---|
  | "could not reserve" lines > 0 in a phase with CacheUsed ≤ M and VmLck − baseline ≤ M + 1 MiB | The DataNode's reserve caught a NameNode plan beyond the headroom; claim (2) holds; claim (1) not confirmed at this tier |
- **A12 (B2d, B3d), instrument validity.** The rows that read the absence of "cannot fit" lines (Test B pre and w2, the
  ablation's w1, phase 2's "no cannot-fit" row) need the `CacheReplicationMonitor` DEBUG level in effect. Known answer:
  every rescan logs `Scanned <n> directive(s) and <m> block(s) in <t> millisecond(s).` at DEBUG
  (`CacheReplicationMonitor.java:205`), one per second here. Counted in every unit window (pre, w1, w2, Test A, Test C)
  and in every cluster phase (NameNode log from the phase start). Row added to B2g and B3g:
  | Observation | Meaning |
  |---|---|
  | A window or phase with 0 "Scanned" lines | DEBUG capture not in effect there; that row/phase gives no verdict (instrument invalid) |

### D2. Stage-4 result (2026-11-25, run 1 on `pc72`)

Results file: `results/dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining--autonomous.md` (at run time
`~/writeup-hadoop/out/o22/results.md`). Frozen version of this file: sha256 `eb8f21a0…7612b` (sections A–C and D1/D1b
unchanged since; only this D2 was added after run 1).

- **Unit tier: Confirmed — caps.** Test B matched B2f in all 9 instances: P0 = 65536 (16 blocks); after the change
  P1 = P2 = 65536 / 49152 / 32768 / 16384 / 0 / 0 for U = 0 / 16384 / 32768 / 49152 / 65536 / 81920 and 65536 / 32768 / 0
  for C' = 65536 / 32768 / 0; the line-534 DEBUG message fired once per dropped block (0 / 4 / 8 / 12 / 16 / 16 and
  0 / 8 / 16 distinct ids), never before the change or in the second window ("Scanned" DEBUG lines 3 in every window).
  Ablation (line 534 `if (false && …)`, U = 49152): P1 = P2 = 65536, 0 drop lines. Test A: DN CacheUsed = C, blocks = C/4096
  (4 / 8 / 16), bytesCached = C, max ≤ C, NN pending 0, 0 reserve refusals. Test C: 65536. Surefire 12/0/0 and 1/0/0.
- **Cluster tier: Confirmed — caps.** `VmLck` 0 / 65536 / 131072 / 262144 / 524288 kB and CacheUsed = BYTES_CACHED
  0 / 64 / 128 / 256 / 512 MiB at M = 0 / 64m / 128m / 256m / 1g (512 MiB file), never above M; 0 "could not reserve"
  lines. Phase 2 (M = 128m, 60-s cache reports, re-run once under A8 with a ≈ 50-s window): 8 "cannot fit … remaining
  cache size 0" lines for the 8 commanded blocks ≈ 2.8 s after the directive, 2 `DNA_CACHE` commands (same 8 ids), then
  none for ≈ 48 s until the cache report; CacheUsed 128 MiB, `VmLck` 131072 kB.
- **Outcome class:** true positive (estimate `positive`, effect `caps` at both tiers).
- Recommendations for stage 3 (not applied): A3 step 4's citation of the resend reset is `CacheReplicationMonitor.java:309`
  (not 308); predict reserve-refusal lines, not `NumBlocksFailedToCache`, which also counts duplicate commands.
