# dfs.datanode.reserve-for-archive.default.percentage — verification solution  <!-- file: cases/dfs.datanode.reserve-for-archive.default.percentage-getVolumeByMount-getAvailable--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`FsVolumeList.java:148`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsVolumeList.java#L148) — `if (volume != null && volume.getVolume().getAvailable() > blockSize)` in `FsVolumeList.getVolumeByMount` (row unit; the check is in the method itself, no helper) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive` — with same-disk tiering on, the ARCHIVE volume's capacity is `capacity × ratio` (`FsVolumeImpl.java:448-452`), the ratio defaulting to `dfs.datanode.reserve-for-archive.default.percentage`; `getAvailable()` at the check is that capacity minus the ARCHIVE volume's HDFS bytes, so a same-mount DISK→ARCHIVE move is refused once the ARCHIVE share is full, and the fallback path (`getNextVolume`) refuses too. Caveats: it caps HDFS's accounting of the ARCHIVE share of a mount, not the mount's physical bytes (the move is a hardlink); concurrent moves can pass the check together (small overshoot); blocks already present are not evicted. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- Name: `dfs.datanode.reserve-for-archive.default.percentage` (configuration key). Despite "percentage", it is a **fraction** 0.0–1.0 of the mount's capacity given to the ARCHIVE volume on that mount; the DISK volume on the same mount gets `1 − value`.
- Declared: [`DFSConfigKeys.java:1710-1714`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java#L1710-L1714) (`DFS_DATANODE_RESERVE_FOR_ARCHIVE_DEFAULT_PERCENTAGE`, default constant `0.0`). `hdfs-default.xml:6460-6473`, value `0.0`. Java default and XML agree (0.0), so nothing to resolve.
- Read by: `MountVolumeInfo` constructor `MountVolumeInfo.java:45-58`, clamped to [0, 1] with a warning (`:49-58`). One `MountVolumeInfo` is created per detected mount (`MountVolumeMap.java:69-81`).
- Unit: dimensionless ratio of the volume's capacity (bytes after `dfs.datanode.du.reserved`).
- Only active when `dfs.datanode.same-disk-tiering.enabled=true` (`DFSConfigKeys.java:1705-1708`, default `false`; `hdfs-default.xml:6449-6458`), and only when a DISK and an ARCHIVE volume of `dfs.datanode.data.dir` are detected on the same filesystem mount (`MountVolumeInfo.java:93-100`: `storageTypeVolumeMap.size() > 1`; mount from `DF.getMount()` = `df -k`, `FsVolumeImpl.java:201-206`, `DF.java:110-127`).
- Other sources of the same limit (named here, not the stem): the per-volume override `dfs.datanode.same-disk-tiering.capacity-ratio.percentage` (`DFSConfigKeys.java:1716-1720`, default `""`, `hdfs-default.xml:6475-6488`; parsed in `FsVolumeList.initializeCapacityRatio` `FsVolumeList.java:154-166` → `StorageLocation.parseCapacityRatio` `StorageLocation.java:167-194`; applied in `FsVolumeList.addVolume` `:383-389` → `MountVolumeInfo.setCapacityRatio` `:127-140`); it takes precedence (`MountVolumeInfo.java:79-91`). The capacity the ratio multiplies is the df capacity minus `dfs.datanode.du.reserved` (`FsVolumeImpl.java:436-446`), or a test-only `configuredCapacity`.
- How set: `hdfs-site.xml` on the DataNode. Read once per mount at volume add (DataNode start, or volume hot-swap `dfsadmin -reconfig datanode ... start` for new volumes — `DataNode.java:1240-1260` validates same-disk-tiering on reconfig but notes ratio refresh is a TODO). So in practice a **DataNode restart** is required to change it.
- Process: DataNode (`FsDatasetImpl` / `FsVolumeList` / `FsVolumeImpl`).

**A2. What it caps.** Disk: the number of HDFS bytes the ARCHIVE volume (one of two `dfs.datanode.data.dir` entries on the same mount) may hold — its logical share of the mount. The quantity compared at the entry check is `FsVolumeImpl.getAvailable()` of the ARCHIVE (target) volume, i.e. `min(capacity×ratio − dfsUsed − reservedForReplicas, df.available − remainingReserved − reservedForReplicas)` (`FsVolumeImpl.java:474-482`), against the block's byte length `block.getNumBytes()` (`FsDatasetImpl.java:1095-1097`). For moves in the other direction (ARCHIVE→DISK) the same code caps the DISK volume with `1 − ratio`.

**A3. Mechanism.**
1. A same-host storage move arrives as `OP_REPLACE_BLOCK` whose proxy source is the DataNode itself — this is what `hdfs mover` sends when a block's policy wants ARCHIVE and an ARCHIVE storage exists on the same node (`Mover.java:489-542` `chooseTargetInSameNode`; `Dispatcher.java:320-325` proxy = source when same node; `Dispatcher.java:448-450` sends `storageId = null`, so the receiver sees `""`). `DataXceiver.replaceBlock` → `datanode.data.moveBlockAcrossStorage(block, storageType, storageId)` (`DataXceiver.java:1199-1201`).
2. `FsDatasetImpl.moveBlockAcrossStorage` (`FsDatasetImpl.java:1061-1126`): requires a FINALIZED replica on a different storage type; `shouldConsiderSameMountVolume` (`:1133-1150`) is true when the target storage id is empty, the source volume has a non-empty mount (only when same-disk tiering is on), and source/target types are DISK/ARCHIVE.
3. Under the block-pool **read** lock (`:1092-1093`) it calls `volumes.getVolumeByMount(targetStorageType, sourceMount, block.getNumBytes())` (`:1095-1097`).
4. `getVolumeByMount` (`FsVolumeList.java:140-152`) returns null if tiering is off (`:142-144`), looks up the counterpart volume on the same mount (`:145-146`, `MountVolumeMap.java:48-55`), and then the check
   **[`FsVolumeList.java:148`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsVolumeList.java#L148)** `volume.getVolume().getAvailable() > blockSize`.
   - `getAvailable()` (`FsVolumeImpl.java:474-482`) uses `getCapacity()` (`:434-456`), which multiplies the base capacity by `MountVolumeMap.getCapacityRatioByMountAndStorageType` (`:448-452`, `MountVolumeMap.java:61-67`) → `MountVolumeInfo.getCapacityRatio` (`MountVolumeInfo.java:78-102`): explicit per-volume ratio, else leftover of the counterpart's explicit ratio, else `reservedForArchiveDefault` for ARCHIVE / `1 − reservedForArchiveDefault` for DISK, else 1.
   - `dfsUsed` is the in-memory per-block-pool counter, incremented by block + meta length at finalize (`BlockPoolSlice.java:445-455`) and periodically refreshed by `du` (`fs.du.interval`, 600 s, `core-default.xml:1361-1363`); the df terms are cached for `fs.df.interval` (60 s, `core-default.xml:1355-1357`).
5. Outcomes:
   - **Pass** → returns the ARCHIVE volume reference; `useVolumeOnSameMount = true` (`FsDatasetImpl.java:1098-1100`); `moveBlock(..., true)` → `moveReplicaToVolumeOnSameMount` → `hardLinkBlockToTmpLocation` (`FsDatasetImpl.java:1164-1179, 1233-1241`; `FsVolumeImpl.java:1546-1562`, reserves 0 bytes), then `finalizeNewReplica` adds block+meta to the ARCHIVE `dfsUsed` and `removeOldReplica` subtracts them from DISK. Metrics `ReplaceBlockOpOnSameHost` and `ReplaceBlockOpOnSameMount` are incremented (`FsDatasetImpl.java:1114-1117`).
   - **Fail** (`available ≤ blockSize`, or no counterpart) → null; falls back to `volumes.getNextVolume(targetStorageType, ...)` (`FsDatasetImpl.java:1102-1108`, `FsVolumeList.java:177-186`) → `RoundRobinVolumeChoosingPolicy.chooseVolume`, which needs `getAvailable() > blockSize + additionalAvailableSpace` (`RoundRobinVolumeChoosingPolicy.java:107-128`; `dfs.datanode.round-robin-volume-choosing-policy.additional-available-space`, default 1 GiB, `DFSConfigKeys.java:1189-1193`). With the single ARCHIVE volume being the same one, this is stricter, so the move throws `DiskOutOfSpaceException` ("Out of space: The volume with the most available space ...") and `replaceBlock` returns an error to the Mover. If another ARCHIVE volume on another mount exists, the block is **copied** there instead (not a cap bypass for this volume).
6. Bypasses / overshoot:
   - **Concurrency**: the check runs under a shared read lock and `dfsUsed` is only incremented later in `finalizeNewReplica` after the lock is released (`FsDatasetImpl.java:1092-1113`), with no space reservation on the hardlink path (`FsVolumeImpl.java:1558`). Up to `dfs.datanode.balance.max.concurrent.moves` (default 100, `DFSConfigKeys.java:118`; Mover side `Mover.java:136-138`) concurrent moves can each pass the check against the same `available`, overshooting by up to (concurrency − 1) blocks.
   - **Pre-existing data**: the cap only gates new placement; blocks already on the ARCHIVE volume above `capacity×ratio` stay (documented: "capacity usage might be >100%", `hdfs-default.xml:6468-6471`, `DFSConfigKeys.java:1701-1703`). `getAvailable` then clamps to 0 (`FsVolumeImpl.java:481`).
   - **Strict-ish margin**: the check admits a block when `available > blockSize`, ignoring the meta file (≈ blockSize/128); the last admitted block can overshoot the capacity by up to its meta size.
   - **Logical, not physical**: the hardlink move adds no bytes to the mount; what the check caps is the ARCHIVE share in HDFS accounting (and hence what the NameNode will place on ARCHIVE). Physical bytes on the mount are bounded by df/du.reserved, not by this ratio.
   - **Not this path**: a request with a non-empty target storage id, a RAM_DISK source, or tiering off skips the check (`FsDatasetImpl.java:1079-1084, 1135-1137`); those moves go to `getNextVolume`, which applies the same `getAvailable()` (with the ratio) through the volume-choosing policy.

**A4. Other consumers.** The DISK volume on the same mount (capped by `1 − ratio` through the same `getCapacity`), non-HDFS files on the mount (counted in df terms and `getActualNonDfsUsed`, `FsVolumeImpl.java:484-507`), RBW/re-replication reservations (`reservedForReplicas`), DataNode metadata files (`VERSION`, `scanner.cursor`, `dfsUsed` cache files), and normal client writes to ARCHIVE (policy COLD/WARM) which go through `getNextVolume` and the volume-choosing policy rather than line 148. The Mover itself also reads per-storage-type remaining from NameNode reports (`Mover.java:171-177, 233-243`) but only requires it to be > 0; it does not check it against block size (`Mover.java:526-542`).

**A5. Evidence beyond the source.**
- HDFS-15548 (same-disk tiering), cited in `hdfs-default.xml:6453` and `DFSConfigKeys.java:1697`; MountVolumeMap comment `MountVolumeMap.java:33-35`: https://issues.apache.org/jira/browse/HDFS-15548
- HDFS-12942 referenced for the hardlink move safety (`FsDatasetImpl.java:1224`): https://issues.apache.org/jira/browse/HDFS-12942
- Existing tests: `TestFsDatasetImpl#testMoveBlockSuccessWithSameMountMove` (ratio 0.5, hardlink move succeeds, `TestFsDatasetImpl.java:1368-1412`) and `#testMoveBlockWithSameMountMoveWithoutSpace` (ratio 0.0, `DiskOutOfSpaceException`, `:1415-1454`). They use a 100-byte file and real disk capacity; they do not exercise the boundary.
- Hadoop 3.4.2 docs, ArchivalStorage page (`hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/ArchivalStorage.md`) for the Mover/storage-policy workflow: https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/ArchivalStorage.html (local copy `hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/ArchivalStorage.md` not opened; command names are confirmed in source).

## B. Verification solution

**B1. Claim under test.** With `dfs.datanode.same-disk-tiering.enabled=true` and DISK+ARCHIVE volumes on one mount of effective capacity C, serial same-host DISK→ARCHIVE moves succeed exactly while the ARCHIVE volume's `getAvailable()` exceeds the block size, so the HDFS bytes on the ARCHIVE volume stay ≤ `floor(C × r)` with r = `dfs.datanode.reserve-for-archive.default.percentage`, and the number of blocks moved scales with r. The claim is wrong if ARCHIVE bytes exceed `floor(C × r)` + one meta file in a serial run, or if the moved count does not change with r.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 8, Maven ≥ 3.3. Copy the tree to local disk first: `rsync -a ~/hadoop-3.4.2/ $WORK/hadoop-src/` (`$WORK` on local disk, e.g. `/mydata/<run>`), and work only there.
- `cd $WORK/hadoop-src && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`
- New test file `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/TestArchiveSameMountCap.java` (same package as `FsDatasetImpl`, so package-private `moveBlockAcrossStorage`/`getMountVolumeMap` are reachable).
- Run: `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestArchiveSameMountCap -Dtest.build.data=$WORK/testdata` (the MiniDFSCluster base dir must sit on one local filesystem; `$WORK/testdata` keeps both data dirs on the same mount). Default surefire heap is enough (one NN + one DN, ≤ 128 MiB of data).

> **Amendment D1-1 (2026-11-25, stage-4 audit; environment only, B2f/B2g unchanged).** Source copy by `copy-source.sh` into the run folder `/mydata/jingsong-s4/<stem>-run1/src`; the modules are in `~/.m2` from the node build, so no `install` step: `mvn -B -o -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestArchiveSameMountCap -DfailIfNoTests=false -Dtest.build.data=$MNT/testdata -Dhdfs.minidfs.basedir=$MNT/testdata/minidfs`. `$MNT` is a 12 GiB ext4 loop filesystem (`mkfs.ext4 -m 0`, sparse image in the run folder) so both data dirs sit on one small mount (node rule: same-mount tests on loop volumes, never on `/mydata` itself). The test logs the MiniDFSCluster base dir and each volume's `getMount()`.

**B2b. Knobs.**
- r = `dfs.datanode.reserve-for-archive.default.percentage` ∈ {0.0, 0.1, 0.25, 0.5}: 0.0 is the default (ARCHIVE gets nothing), 0.1 and 0.25 put the boundary inside the 40-block workload, 0.5 puts it beyond (all fit). Set with `conf.setDouble(...)` before building the cluster.
- Fixed: `dfs.datanode.same-disk-tiering.enabled=true`; volume capacity C = 134,217,728 B (128 MiB) per volume via `MiniDFSCluster.Builder.storageCapacities(new long[]{C, C})` (calls `FsVolumeImpl.setCapacityForTesting`, `MiniDFSCluster.java:1895-1902`; the ratio is still applied on top, `FsVolumeImpl.java:445-452`); `dfs.blocksize=1048576`; `dfs.bytes-per-checksum=512` (default); `dfs.datanode.round-robin-volume-choosing-policy.additional-available-space=0` (otherwise the 1 GiB default makes every DISK write fail against a 128 MiB volume; it also makes the fallback threshold equal to line 148's).
- Control knob: `dfs.datanode.same-disk-tiering.enabled=false` (ratio ignored) with r = 0.1.
- Concurrency knob: number of mover threads T ∈ {1 (serial), 8}.

**B2c. Workload.** Write N = 40 files of exactly one 1 MiB block each, replication 1, policy HOT (default → DISK). Then call `fsDataset.moveBlockAcrossStorage(block, StorageType.ARCHIVE, null)` for each block (this is the exact call `DataXceiver.replaceBlock` makes, `DataXceiver.java:1200`).
Arithmetic: per replica on disk = 1,048,576 + meta (7 + 1,048,576/512×4 = 8,199) = 1,056,775 B. ARCHIVE capacity = floor(134,217,728 × r): 0 / 13,421,772 / 33,554,432 / 67,108,864. A move is admitted while `cap − k×1,056,775 > 1,048,576` (k = blocks already moved). 40 blocks = 42,271,000 B, more than the 0.1 and 0.25 capacities and less than 0.5's. DISK capacity (C × (1 − r) ≥ 67,108,864) holds all 40 blocks before the moves.

**B2d. Observables and instruments.**
- The check's operand: `archiveVol.getAvailable()` immediately before each move (archive volume = the `FsVolumeImpl` from `fsDataset.getFsVolumeReferences()` with `getStorageType()==ARCHIVE`), and the move's outcome (returns / throws `DiskOutOfSpaceException`).
- `archiveVol.getDfsUsed()` and `archiveVol.getCapacity()` after each move; number of block files: `find <archive dir>/current -name 'blk_*' ! -name '*.meta' | wc -l` (or count in Java with `FileUtils.listFiles`).
- Path taken: DataNode metrics `ReplaceBlockOpOnSameMount` / `ReplaceBlockOpOnSameHost` via `MetricsAsserts.getLongCounter(name, MetricsAsserts.getMetrics(dn.getMetrics().name()))`.
- Sanity: `vols[DISK].getMount().equals(vols[ARCHIVE].getMount())`, `fsDataset.getMountVolumeMap().hasMount(mount)`, and `getCapacity()` of ARCHIVE = floor(C × r).
- Not directly observable: the private `FsVolumeList` decision itself; it is inferred from the metric `ReplaceBlockOpOnSameMount` (incremented only when line 148 passed).

> **Amendment D1-2 (2026-11-25, stage-4 audit; instruments).** (a) Direct observation of line 148: before each serial move the test calls `FsVolumeList.getVolumeByMount(StorageType.ARCHIVE, <source DISK volume>.getMount(), block.getNumBytes())` on the dataset's private `volumes` field (reflection; the returned reference is closed at once) and logs `probe=pass` (non-null) or `probe=null`. The probe takes no lock and changes nothing; it is skipped in the T = 8 run. (b) After each move the test sums the sizes of all `blk_*` files (block and meta) under the ARCHIVE volume's `current/` (the real-resource reading; no `du` offset). (c) The refusal's exception class and message are logged.

**B2e. Procedure.**
1. Add the test class. Sketch (one helper, five `@Test` methods):
   ```java
   package org.apache.hadoop.hdfs.server.datanode.fsdataset.impl;
   // imports: Configuration, HdfsConfiguration, DFSConfigKeys, MiniDFSCluster, DFSTestUtil,
   // FileSystem, Path, StorageType, ExtendedBlock, DataNode, FsVolumeReferences/FsVolumeSpi,
   // DiskChecker.DiskOutOfSpaceException, MetricsAsserts, java.util.concurrent.*, JUnit 4
   public class TestArchiveSameMountCap {
     static final long C = 128L << 20, BS = 1L << 20; static final int N = 40;
     Result run(double r, boolean tiering, int threads) throws Exception {
       Configuration conf = new HdfsConfiguration();
       conf.setBoolean(DFSConfigKeys.DFS_DATANODE_ALLOW_SAME_DISK_TIERING, tiering);
       conf.setDouble(DFSConfigKeys.DFS_DATANODE_RESERVE_FOR_ARCHIVE_DEFAULT_PERCENTAGE, r);
       conf.setLong(DFSConfigKeys.DFS_BLOCK_SIZE_KEY, BS);
       conf.setLong(DFSConfigKeys.DFS_DATANODE_ROUND_ROBIN_VOLUME_CHOOSING_POLICY_ADDITIONAL_AVAILABLE_SPACE_KEY, 0L);
       try (MiniDFSCluster cl = new MiniDFSCluster.Builder(conf).numDataNodes(1)
             .storagesPerDatanode(2).storageTypes(new StorageType[]{StorageType.DISK, StorageType.ARCHIVE})
             .storageCapacities(new long[]{C, C}).build()) {
         cl.waitActive(); FileSystem fs = cl.getFileSystem(); DataNode dn = cl.getDataNodes().get(0);
         FsDatasetImpl ds = (FsDatasetImpl) dn.getFSDataset();
         FsVolumeImpl arch = /* volume with getStorageType()==ARCHIVE */;
         List<ExtendedBlock> blocks = new ArrayList<>();
         for (int i = 0; i < N; i++) { Path p = new Path("/f" + i);
           DFSTestUtil.createFile(fs, p, 4096, BS, BS, (short) 1, i);
           blocks.add(DFSTestUtil.getFirstBlock(fs, p)); }
         // log arch.getCapacity(), arch.getAvailable(), mounts equal
         // serial: for each block: availBefore = arch.getAvailable(); try ds.moveBlockAcrossStorage(b, ARCHIVE, null) -> moved++ ; catch DiskOutOfSpaceException -> refused++ ; log row
         // threads>1: submit all N moves to Executors.newFixedThreadPool(threads) started by a CountDownLatch; count outcomes
         // after: arch.getDfsUsed(), arch.getAvailable(), ReplaceBlockOpOnSameMount, ReplaceBlockOpOnSameHost, file count in archive dir
       }
     }
     @Test public void r000() ...  run(0.0, true, 1)
     @Test public void r010() ...  run(0.1, true, 1)
     @Test public void r025() ...  run(0.25, true, 1)
     @Test public void r050() ...  run(0.5, true, 1)
     @Test public void controlTieringOff() ... run(0.1, false, 1)
     @Test public void concurrentR010() ... run(0.1, true, 8)
   }
   ```
   Each test logs one line per move (`k, availBefore, outcome`) and a summary line `r, tiering, T, moved, refused, archDfsUsed, archCapacity, archAvailable, sameMount, sameHost`, and asserts nothing beyond the sanity checks (readings are compared to B2f by the operator).
2. Build and run as in B2a; collect `target/surefire-reports/*TestArchiveSameMountCap-output.txt`.
3. `rm -rf $WORK/testdata` afterwards.

**B2f. Predictions.** (per replica 1,056,775 B; serial T = 1)

| r | ARCHIVE capacity | moved / refused | ARCHIVE dfsUsed after | ARCHIVE available after | SameMount / SameHost |
|---|---|---|---|---|---|
| 0.0 | 0 | 0 / 40 (first move throws `DiskOutOfSpaceException`) | 0 | 0 | 0 / 0 |
| 0.1 | 13,421,772 | 12 / 28 | 12,681,300 | 740,472 | 12 / 12 |
| 0.25 | 33,554,432 | 31 / 9 | 32,760,025 | 794,407 | 31 / 31 |
| 0.5 | 67,108,864 | 40 / 0 | 42,271,000 | 24,837,864 | 40 / 40 |
| control (tiering off, r=0.1) | 134,217,728 (ratio ignored) | 40 / 0 | 42,271,000 | ≈ 91.9 M | 0 / 40 (copy path) |
| concurrent, r=0.1, T=8 | 13,421,772 | between 12 and 19 | ≤ 12,681,300 + 7×1,056,775 = 20,078,725 | ≥ 0 (clamped) | = moved |

In every serial row, each successful move has `availBefore > 1,048,576` and each refusal has `availBefore ≤ 1,048,576`; `dfsUsed_after ≤ capacity` always.

> **Amendment D1-3 (2026-11-25, stage-4 audit; source-derived, before any reading).** A volume's `dfsUsed` does not start at 0: `BlockPoolSlice` builds `FSCachingGetSpaceUsed` with `loadDfsUsed()` (`BlockPoolSlice.java:218-222, 338`), which is −1 on a fresh volume, so the first refresh runs `du` of the block-pool directory (directory blocks, `VERSION`, …: a few tens of KB), and the 600 s `du` refresh can add directory blocks later. The "dfsUsed after" columns (B2f, and the ARCHIVE `usedSpace` of B3d) are therefore read as `moved × per-replica + δ`, and "available after" as `predicted − δ`, where δ = ARCHIVE dfsUsed − moved × per-replica (logged; δ ≥ 0). The moved counts are unchanged for δ < 700,000 B (smallest margin: unit r = 0.1 at k = 11, 1,797,247 − 1,048,576 = 748,671 B; cluster margins are > 47 MB). The block+meta file sums (D1-2b; B3d `find`) carry no δ and are compared with `moved × per-replica` exactly. A δ ≥ 700,000 B is recorded as a deviation.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Serial rows match B2f (moved count rises 0→12→31→40 with r; dfsUsed ≤ floor(C×r)) | Claim confirmed at the unit level: the ratio sets the ARCHIVE cap and line 148 enforces it. |
| A serial move succeeds with `availBefore ≤ 1,048,576`, or serial dfsUsed > floor(C×r) + 8,199 | Claim wrong: the check does not bound the ARCHIVE bytes as traced. |
| Moved count identical for all r (e.g. 40 everywhere) | Ratio not applied (check sanity: mounts equal, `hasMount`, tiering flag); if sanity holds, claim wrong. |
| Moves succeed but `ReplaceBlockOpOnSameMount` = 0 with tiering on | Line 148 not reached (copy path via fallback); mechanism different from A3. |
| Control moves all 40 with SameMount = 0 | Confirms the cap comes from the same-disk-tiering ratio, not from capacity C. |
| Concurrent run moves > 12 and dfsUsed > capacity | Confirms the non-atomic check overshoot (A3.6); does not refute the serial claim. Concurrent moved = 12 is also consistent (race not hit). |
| Concurrent moved > 19 | Overshoot larger than the thread bound: unexpected, re-examine locking. |

> **Amendment D1-4 (2026-11-25, stage-4 audit; rows added before run 1, for reasons that do not depend on any reading).** (a) The first row (claim confirmed) also needs the direct disallow evidence of D1-2a: in every serial tiering-on row, `probe=pass` before each successful move and `probe=null` before each refusal, and the moved count equal to `ReplaceBlockOpOnSameMount`. (b) The second row (claim wrong) applies to the block+meta file sum (D1-2b) as well as to `dfsUsed`. (c) Added rows:

| Observation | Meaning |
|---|---|
| A serial move succeeds via the same mount after `probe=null`, or is refused after `probe=pass` | Probe and move disagree: line 148 is not the deciding point as traced; unit tier Not confirmed. |
| Control moves fewer than 40, or its `ReplaceBlockOpOnSameMount` > 0 | Control failed: the cap cannot be attributed to the ratio; unit tier Not confirmed. |
| r = 0.5 moves fewer than 40 | Positive control failed (workload or move call); the unit tier does not test the claim (Not confirmed). |

**B2h. Controls.** Tiering-off control (same workload, ratio ignored → all move). r = 0.5 is a positive control that the workload and move call work. Sanity assertions that both volumes share a mount and ARCHIVE `getCapacity()` equals floor(C×r) rule out a misconfigured mount map. Each test uses a fresh MiniDFSCluster so no state carries over.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux host, pseudo-distributed: NameNode, one DataNode, and the `hdfs mover` client. No YARN.
- Build: `cd $WORK/hadoop-src && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`; unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `$WORK/hadoop`; `export HADOOP_HOME=$WORK/hadoop PATH=$HADOOP_HOME/bin:$HADOOP_HOME/sbin:$PATH JAVA_HOME=<jdk8>`.
- Run dir `RUN=$WORK/run` on **local** disk (e.g. `/mydata`) with **≥ 12 GiB free** (8 GiB effective capacity + 2 GiB data + margin). `export HADOOP_LOG_DIR=$RUN/logs HADOOP_PID_DIR=$RUN/pids HADOOP_HEAPSIZE_MAX=1g`. Passwordless `ssh localhost` for `start-dfs.sh` (or use `hdfs --daemon start namenode|datanode`).
- Effective capacity: C = 8 GiB = 8,589,934,592 B, made by `dfs.datanode.du.reserved` R = (df size of the mount) − C:
  `DFCAP=$(df -B1 --output=size $RUN | tail -1); R=$((DFCAP - 8589934592))`. Each volume's base capacity is then df size − R = C (`FsVolumeImpl.java:436-443`), and with ratio r ARCHIVE = C×r, DISK = C×(1−r). (Requires df available > 8 GiB so non-HDFS usage stays below R; then the df term of `getAvailable` is C − DISK used − ARCHIVE used and never the binding term in this workload.)
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=$RUN/tmp`.
- `hdfs-site.xml`:
  - `dfs.replication=1`
  - `dfs.namenode.name.dir=file://$RUN/nn`
  - `dfs.datanode.data.dir=[DISK]file://$RUN/dn/disk,[ARCHIVE]file://$RUN/dn/archive` (both on the same mount)
  - `dfs.datanode.same-disk-tiering.enabled=true`
  - `dfs.datanode.reserve-for-archive.default.percentage=<r>`
  - `dfs.datanode.du.reserved=<R>`
  - `dfs.blocksize=67108864`
  - `dfs.heartbeat.interval=1` (fresher NN storage reports; Mover sleep = 2×heartbeat + redundancy interval, `Mover.java:655-661`)
  - `dfs.namenode.redundancy.interval.seconds=1`
  - leave `dfs.datanode.round-robin-volume-choosing-policy.additional-available-space` at its 1 GiB default (DISK has room for it; it makes the fallback stricter than line 148, so hardlink moves admitted in the last GiB can only come from line 148).

> **Amendment D1-5 (2026-11-25, stage-4 audit; environment only, B3f/B3g unchanged).** Distribution: a copy of the node's build `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` in the run folder (no rebuild), `HADOOP_CONF_DIR` in the run folder. The two data dirs `dn/disk` and `dn/archive` are on a 12 GiB ext4 loop filesystem (`mkfs.ext4 -m 0`, sparse image in the run folder) mounted at `$RUN/mnt`; the NameNode dir, logs, `hadoop.tmp.dir` and the 64 MiB staging file stay outside it on `/mydata`. R = (df size of `$RUN/mnt`) − 8 GiB (B3a's formula on the loop mount; df available > 8 GiB holds for the empty filesystem). Ports off the defaults: `fs.defaultFS=hdfs://localhost:19000`, NameNode HTTP 19870, DataNode 19866 / 19867 / 19864 (the JMX URLs of B3d use 19864 and 19870). Daemons by `hdfs --daemon` (SSH to localhost does not work on these nodes); process checks by `ps`, not `jps`. The loop filesystem stays mounted across the configurations (each run wipes `dn/` and re-formats) and is unmounted and detached at the end.

**B3b. Knobs.** r ∈ {0.0, 0.1, 0.25, 0.5} (same reasons as B2b); each value needs a DataNode restart, and the runs below re-format so each starts empty. Mover concurrency: `-D dfs.datanode.balance.max.concurrent.moves=1` (serial, main runs) vs default 100 (concurrency runs at r = 0.1 and 0.25). Control: `dfs.datanode.same-disk-tiering.enabled=false` with r = 0.1.

**B3c. Workload.** 32 files × one 64 MiB block = 2 GiB written as HOT (DISK). Per replica = 67,108,864 + meta (7 + 67,108,864/512×4 = 524,295) = 67,633,159 B; 32 replicas = 2,164,261,088 B. DISK capacity C×(1−r) ≥ 4 GiB holds them with the 1 GiB policy margin (worst case r=0.5: 4,294,967,296 − 2,164,261,088 = 2.13 GB left > 64 MiB + 1 GiB). Then policy COLD on the directory and `hdfs mover -p /cold`, which moves each replica to the ARCHIVE volume on the same node through line 148. ARCHIVE capacity floor(C×r) = 0 / 858,993,459 / 2,147,483,648 / 4,294,967,296 B, i.e. below, below, just below and above the 2 GiB data. Duration ≈ 5–10 min per run (writes < 1 min; Mover iterations ~3 s apart, up to 10 retries after the cap is hit).

**B3d. Observables and instruments.**
- ARCHIVE bytes on disk: `find $RUN/dn/archive/current -type f -name 'blk_*' -printf '%s\n' | awk '{s+=$1} END{print s+0}'`; block count `find $RUN/dn/archive/current -type f -name 'blk_*' ! -name '*.meta' | wc -l`; same for `$RUN/dn/disk`. Hardlink check: `find $RUN/dn/archive/current -name 'blk_*' -type f -links +1 | wc -l` should be 0 after the Mover exits (old link removed).
- The check's operand and HDFS accounting: DN JMX `curl -s 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=DataNodeInfo' | python3 -c 'import sys,json; print(json.loads(json.load(sys.stdin)["beans"][0]["VolumeInfo"]))'` → per volume `usedSpace` (= `getDfsUsed`), `freeSpace` (= `getAvailable`, the operand), `numBlocks`, `storageType` (`FsDatasetImpl.java:3296-3332`).
- Path taken: `curl -s 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=DataNodeActivity-*'` → `ReplaceBlockOpOnSameMount`, `ReplaceBlockOpOnSameHost`.
- NameNode view: `curl -s 'http://localhost:9870/jmx?qry=Hadoop:service=NameNode,name=BlockStats'` → `StorageTypeStats` ARCHIVE `capacityTotal`/`capacityUsed`/`capacityRemaining`; `hdfs dfsadmin -report` configured capacity ≈ C.
- Block placement: `hdfs fsck /cold -files -blocks -locations` (storage type per replica in `DatanodeInfoWithStorage[...,DISK|ARCHIVE]`).
- Mover result: exit code and last stderr line; DN log lines `Moved .* from StorageType DISK to ARCHIVE` and `Out of space` in `$RUN/logs/hadoop-*-datanode-*.log`.
- Sample: once before the Mover, every 2 s during it (`watch`-style loop appending the JMX `freeSpace`/`usedSpace` of ARCHIVE and the `find` sum to `$RUN/samples.csv`), and once 10 s after it exits.
- Not observable directly: the individual line-148 decisions; inferred from `ReplaceBlockOpOnSameMount` and the DN log.

> **Amendment D1-6 (2026-11-25, stage-4 audit; reading rule and added observable).** The B3f "Mover" column is informational (no B3g row uses it). The Mover may resubmit refused blocks in later iterations, so `Out of space` lines can be a multiple of the refused blocks; "N refused" means N distinct block ids refused. Added observable for the disallow branch: each DataNode refusal logs the fallback's WARN `The volume[…/archive/] with the available space (=X B) is less than the block size (=67108864 B).` (`RoundRobinVolumeChoosingPolicy.java:120-122`); with tiering on and an empty target storage id this fallback is reached only after line 148 returned null, and X is line 148's operand. Counted per run: DataNode `Moved … from StorageType DISK to ARCHIVE` lines (successes) and the distinct block ids in `Out of space` replies. At r = 0.0 the Mover gets no ARCHIVE target (`Mover.java:173-175`), so no move reaches the DataNode: that row's cap is enforced by the Mover, not by line 148.

**B3e. Procedure.** For each configuration (serial r = 0.0, 0.1, 0.25, 0.5; concurrent r = 0.1, 0.25; control):
1. `mkdir -p $RUN/{logs,pids,tmp}`; compute R (B3a); write `core-site.xml`/`hdfs-site.xml` into `$HADOOP_HOME/etc/hadoop` with this run's r (and tiering flag).
2. Fresh state: `rm -rf $RUN/nn $RUN/dn && mkdir -p $RUN/dn/disk $RUN/dn/archive && hdfs namenode -format -force -nonInteractive`.
3. `hdfs --daemon start namenode && hdfs --daemon start datanode`; wait until `hdfs dfsadmin -report` shows 1 live DN; record configured capacity (≈ 8,589,934,592) and ARCHIVE `capacityTotal` from NN BlockStats (≈ floor(C×r)); confirm in the DN log that both volumes were added and the DN JMX lists both `storageType`s.
4. Data: `head -c 67108864 /dev/urandom > $RUN/blk.bin; hdfs dfs -mkdir /cold; for i in $(seq -w 1 32); do hdfs dfs -put $RUN/blk.bin /cold/f$i; done`. Check `hdfs fsck /cold -files -blocks -locations | grep -c DISK` = 32 and the DISK `find` sum = 2,164,261,088.
5. `hdfs storagepolicies -setStoragePolicy -path /cold -policy COLD`.
6. Start sampler (B3d) in background; run
   serial: `hdfs mover -D dfs.datanode.balance.max.concurrent.moves=1 -D dfs.heartbeat.interval=1 -D dfs.namenode.redundancy.interval.seconds=1 -p /cold; echo "exit=$?"`
   concurrent: same without the first `-D`.
7. After exit: stop sampler; record ARCHIVE/DISK `find` sums and counts, DN JMX VolumeInfo, metrics, NN BlockStats, fsck ARCHIVE count, Mover exit code, `grep -c 'Out of space' datanode log`.
8. `hdfs --daemon stop datanode && hdfs --daemon stop namenode`; `jps` must show neither.

**B3f. Predictions.** (per replica 67,633,159 B; serial runs)

| run | ARCHIVE capacity | replicas on ARCHIVE | ARCHIVE bytes (`find`) | ARCHIVE `freeSpace` after | SameMount | Mover |
|---|---|---|---|---|---|---|
| r = 0.0 | 0 | 0 | 0 | 0 | 0 | no ARCHIVE target (`maxRemaining = 0`, `Mover.java:173-175`) → "Some blocks can't be moved" / non-zero exit |
| r = 0.1 | 858,993,459 | 12 | 811,597,908 | 47,395,551 | 12 | 20 refused with `Out of space`; exits non-zero after 10 retries |
| r = 0.25 | 2,147,483,648 | 31 | 2,096,627,929 | 50,855,719 | 31 | 1 refused; non-zero exit |
| r = 0.5 | 4,294,967,296 | 32 | 2,164,261,088 | 2,130,706,208 | 32 | "Mover Successful", exit 0 |
| control (tiering off, r=0.1) | ≈ C (ratio ignored) | 32 | 2,164,261,088 | > 6 GB | 0 (SameHost 32) | exit 0 |
| concurrent r = 0.1 / 0.25 | as above | ≥ 12 / ≥ 31, possibly more | ≤ capacity + (k−1)×67,633,159 for k in-flight | ≥ 0 | = replicas moved | as above |

In all serial runs ARCHIVE bytes ≤ floor(C×r), DISK + ARCHIVE bytes = 2,164,261,088 throughout, and `df` used on the mount does not grow during the moves (hardlinks); in the control it rises by up to one block per in-flight copy and falls back.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Serial ARCHIVE replica counts 0 / 12 / 31 / 32 and bytes ≤ floor(C×r) | Claim confirmed: the ratio caps the ARCHIVE share of the mount on the real move path. |
| Serial ARCHIVE bytes > floor(C×r) + 524,295 | Claim wrong (cap not enforced or bypassed on this path). |
| Same replica count for every r | Ratio not in effect; check DN log for same-mount detection and NN ARCHIVE `capacityTotal`; if those show the ratio, claim wrong. |
| Moves succeed with `ReplaceBlockOpOnSameMount` = 0 under tiering | Line 148 not the deciding point (copy fallback); mechanism different from A3. |
| Control moves all 32 with SameMount 0 | Confirms the cap is the tiering ratio, not C or the Mover. |
| Concurrent runs exceed the serial count | Confirms the non-atomic check (A3.6) in a real DataNode; bounded overshoot only. |
| ARCHIVE bytes match predictions but `df` used on the mount grows by the moved amount | The move is a copy, not a hardlink: physical-usage reading of A3.6 wrong. |
| r = 0.5 run does not reach 32 | Workload or Mover problem (positive control failed); the run does not test the claim. |

> **Amendment D1-7 (2026-11-25, stage-4 audit; rows added before run 1, for reasons that do not depend on any reading).** (a) The first row (claim confirmed) also needs, in the serial r = 0.1 and 0.25 runs, `ReplaceBlockOpOnSameMount` = replicas moved and a refusal WARN (D1-6) with X ≤ 67,108,864 for each refused block (direct disallow evidence). (b) Added rows:

| Observation | Meaning |
|---|---|
| A block refused under tiering with WARN X > 67,108,864 | The refusal did not come from line 148 (it passed line 148's bound): mechanism different from A3; cluster tier Not confirmed. |
| Control moves fewer than 32, or its `ReplaceBlockOpOnSameMount` > 0 | Control failed: the cap cannot be attributed to the ratio; cluster tier Not confirmed. |

**B3h. Controls.** Tiering-off control (same data and Mover, ratio ignored → all 32 move). r = 0.5 as positive control that the workload can fill ARCHIVE beyond the smaller caps. Fresh format per run (no carry-over of blocks or dfsUsed caches). Concurrency fixed to 1 for the main runs so a race cannot mask or create the cap. `du.reserved` derived from the same df reading the DN uses, recorded per run; NN `capacityTotal` for ARCHIVE checked against floor(C×r) before the Mover starts.

**B4. Risks and cleanup.**
- Disk: unit tier < 200 MiB under `$WORK/testdata`; cluster tier ≈ 2.1 GiB of blocks + 64 MiB staging file + logs under `$RUN` on local disk. Never place `$RUN`, `$WORK` or `test.build.data` on NFS/shared storage. A large `du.reserved` only affects this DataNode's accounting; it reserves nothing physically.
- Other users on the same mount: their writes change df but not the binding term as long as df available stays > C − used; record `df -B1 $RUN` at start and end of each run.
- Ports: 9000 (NN RPC), 9870/9864 (HTTP), 9866/9867 (DN). Check `ss -ltn` first; change ports in `hdfs-site.xml` if taken.
- Processes: after every run `hdfs --daemon stop datanode; hdfs --daemon stop namenode`; `jps` must list no `NameNode`, `DataNode`, `Mover`; kill the sampler loop.
- Cleanup: `rm -rf $RUN $WORK/testdata` (and `$WORK/hadoop-src`, `$WORK/hadoop` if not reused). Never edit the shared source tree.

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsVolumeList.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsVolumeImpl.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/MountVolumeMap.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/MountVolumeInfo.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetImpl.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/BlockPoolSlice.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/ReservedSpaceCalculator.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/RoundRobinVolumeChoosingPolicy.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/StorageLocation.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataNode.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataXceiver.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/metrics/DataNodeMetrics.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/protocol/datatransfer/Receiver.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/datatransfer/Sender.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/mover/Mover.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/balancer/Dispatcher.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/StorageTypeStats.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
- hadoop-common-project/hadoop-common/src/main/resources/core-default.xml
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/DF.java
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/StorageType.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/TestFsDatasetImpl.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/MiniDFSCluster.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/DFSTestUtil.java
- hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/test/MetricsAsserts.java
- https://issues.apache.org/jira/browse/HDFS-15548 (cited from source comments; not fetched)
- https://issues.apache.org/jira/browse/HDFS-12942 (cited from source comments; not fetched)

## D. Stage-4 feedback

**2026-11-25, stage 4 run 1 (Jingsong, `pc91`)** — results: `hadoop/stage4-runtime-verification/jingsong/results/dfs.datanode.reserve-for-archive.default.percentage-getVolumeByMount-getAvailable--autonomous.md`.

- Audit amendments D1-1 to D1-7 (above, dated 2026-11-25) were made before any reading; frozen sha256 `0912dde9899ebba56570ae05d6a60e9e7905453f8ce501e2a1ec844ee3de44bc`. B1 and every predicted number are unchanged.
- **Unit tier: Confirmed — caps.** Serial moved/refused 0/40, 12/28, 31/9, 40/0 for r = 0.0/0.1/0.25/0.5, exactly B2f; ARCHIVE block+meta bytes 0 / 12,681,300 / 32,760,025 / 42,271,000; dfsUsed = those + δ = 24,576 (D1-3); the line-148 probe passed before every success and returned null before every refusal (0 mismatches); every success had `availBefore` > 1,048,576 (smallest 1,772,671) and every refusal ≤ 1,048,576 (largest 769,831). Control (tiering off): 40 moved, SameMount 0. Concurrent T = 8 at r = 0.1: **19 moved**, ARCHIVE block bytes 20,078,725 against a 13,421,772 capacity — the non-atomic check overshoots by exactly T − 1 = 7 blocks (A3.6 confirmed; bounded).
- **Cluster tier: Confirmed — caps.** Serial ARCHIVE replicas 0 / 12 / 31 / 32 with bytes 0 / 811,597,908 / 2,096,627,929 / 2,164,261,088, exactly B3f; `ReplaceBlockOpOnSameMount` = replicas moved; every refusal's fallback WARN showed line 148's operand 47,370,975 (r = 0.1, 20 blocks) or 50,831,143 (r = 0.25, 1 block), both ≤ 67,108,864; `df` used on the mount moved by ≤ 24,576 B during the hardlink moves; control (tiering off) moved all 32 with SameMount 0 and a transient +56 MB copy in `df`. The concurrent Mover runs (default 100) gave the same counts as the serial ones (race not hit).
- Outcome class: **true positive**.
- For stage 3: (1) r = 0.0 is enforced by the Mover (`maxRemaining = 0`, no ARCHIVE target), not by line 148 — as D1-6 notes. (2) The Mover in 3.4.2 never retries: a second iteration throws `MetricsException: Metrics source Mover-<bpid> already exists!` (`Mover.java:685` builds a new `Mover` per iteration, whose constructor registers `MoverMetrics` under the same name, `Mover.java:163`, `MoverMetrics.java:47-50`), so the run exits 255 after one pass whenever a block was refused; B3f's "after 10 retries" does not happen. Upstream candidate (check JIRA). (3) The dfsUsed offset of D1-3 (24,576 B per volume here) belongs in predictions of exact dfsUsed.
