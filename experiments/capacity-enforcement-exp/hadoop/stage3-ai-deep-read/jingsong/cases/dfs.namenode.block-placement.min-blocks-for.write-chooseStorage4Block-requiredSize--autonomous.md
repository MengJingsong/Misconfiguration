# dfs.namenode.block-placement.min-blocks-for.write — verification solution  <!-- file: cases/dfs.namenode.block-placement.min-blocks-for.write-chooseStorage4Block-requiredSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatanodeDescriptor.java:828`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/DatanodeDescriptor.java#L828) — `if (r >= requiredSize)` in `DatanodeDescriptor.chooseStorage4Block(StorageType, long, int)`. The node-level decision that goes with it is the next check, [`DatanodeDescriptor.java:833`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/DatanodeDescriptor.java#L833) `if (requiredSize > remaining - scheduledSize)`. Both are in the same method and use the same limit-side operand, `requiredSize`. |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive`. When the NameNode places a new block replica (and also for re-replication and EC reconstruction), it skips any DataNode storage whose last reported remaining space is below `requiredSize = blockSize × min-blocks-for.write`. It also refuses the node if the qualifying remaining space, minus blocks already scheduled there, is below that amount. So HDFS block bytes on a DataNode stop growing at about `capacity − N·blockSize`, give or take one block, for N = `dfs.namenode.block-placement.min-blocks-for.write`. The cap is approximate. It is NameNode-side admission based on heartbeat data. It does not cover appends to existing blocks. With the default DataNode setting `dfs.datanode.round-robin-volume-choosing-policy.additional-available-space` = 1 GiB, the DataNode's own check binds first unless N·blockSize > blockSize + 1 GiB. |
| Ground | — |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). Use a permalink at the pinned tag,
> `[`File.java:123`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/<full path under the repository root>#L123)`
> (a range is `#L123-L130`). Check that the line number is the line you mean. Other citations may
> stay plain `file:line`.

Naming parts. `[constraint]` = `dfs.namenode.block-placement.min-blocks-for.write`. This is the configuration key that is declared along the path that sets `requiredSize`, and the one an administrator tunes for this check. `[function]` = `chooseStorage4Block`, the method that directly encloses the given if. `[operand]` = `requiredSize`, the limit-side operand at line 828 (and at line 833).

All paths below are relative to `hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/` unless they start with `hadoop-`.

## A. Constraint trace

**A1. The constraint.**

- **Name:** `dfs.namenode.block-placement.min-blocks-for.write`. This is exact; the key has no placeholder.
- **Kind:** configuration key (int).
- **Declared at:** [`DFSConfigKeys.java:1299`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java#L1299), as `DFS_NAMENODE_BLOCKPLACEMENTPOLICY_MIN_BLOCKS_FOR_WRITE_KEY = "dfs.namenode.block-placement.min-blocks-for.write"` (lines 1299-1300). The Java default, `DFS_NAMENODE_BLOCKPLACEMENTPOLICY_MIN_BLOCKS_FOR_WRITE_DEFAULT = HdfsServerConstants.MIN_BLOCKS_FOR_WRITE` (`DFSConfigKeys.java:1301-1302`), comes from the constant `MIN_BLOCKS_FOR_WRITE = 1` (`server/common/HdfsServerConstants.java:47`).
- **`hdfs-default.xml` entry:** `hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml:2462-2469`, value `1`. It is described as "used to calculate the space required for write operations". The Java default and the XML value agree, so there is no conflict. When the XML file is on the classpath (it always is in a distribution), the XML value is what `conf.getInt` returns.
- **Unit:** a count of blocks. The bytes compared are `requiredSize = blockSize * minBlocksForWrite` (`DatanodeDescriptor.java:818`).
  - `blockSize` is the second source of `requiredSize`. It is the file's preferred block size (`INodeFile.getPreferredBlockSize()`, taken at `server/namenode/FSDirWriteFileOp.java:189` for `addBlock`).
  - The file's preferred block size is set by the client from `dfs.blocksize` (`DFSConfigKeys.java:43`, default 128 MiB), or per call. The NameNode floor is `dfs.namenode.fs-limits.min-block-size`, 1 MiB (`hdfs-default.xml:475-476`).
- **Where it is read:** `BlockPlacementPolicyDefault.initialize` reads it into the volatile field `minBlocksForWrite` (`server/blockmanagement/BlockPlacementPolicyDefault.java:116`, `:167-169`). This covers the default policy and its subclasses: rack-fault-tolerant, upgrade-domain, node-group and available-space.
- **How to set it:** in `hdfs-site.xml` of the NameNode. It is **reconfigurable at runtime**, with no restart.
  - The key is in the NameNode's reconfigurable list (`server/namenode/NameNode.java:380`).
  - It is handled by `reconfigureMinBlocksForWrite` (`NameNode.java:2380-2381`, `:2753-2763`), which calls `BlockManager.setMinBlocksForWrite` (`server/blockmanagement/BlockManager.java:5809-5814`). That method rejects values ≤ 0 (`ensurePositiveInt`) and sets the value on both the CONTIGUOUS and the STRIPED policy (`BlockPlacementPolicyDefault.java:1397-1398`).
  - Procedure: edit the NameNode's `hdfs-site.xml`, then run `hdfs dfsadmin -reconfig namenode <host:rpc-port> start`.
- **Which daemon reads it:** the NameNode only.

**A2. What it caps.**

- **Resource:** disk used by HDFS block replicas on DataNode volumes. It works by keeping a headroom of about N blocks on each DataNode/storage type: the NameNode stops choosing that DataNode as a write target.
- **Quantities compared:**
  - Per storage (line 828), `r = s.getRemaining()`. This is the storage's remaining bytes as last reported by the DataNode heartbeat (`DatanodeStorageInfo.updateState`, `server/blockmanagement/DatanodeStorageInfo.java:325-330`). The DataNode computes it as `FsVolumeImpl.getAvailable()` (`server/datanode/fsdataset/impl/FsDatasetImpl.java:173`), which is `min(capacity − dfsUsed − reservedForReplicas, dfAvailable − remainingReserved − reservedForReplicas)` floored at 0 (`FsVolumeImpl.java:474-482`). `capacity` = disk total − `dfs.datanode.du.reserved`, or a test-configured capacity (`FsVolumeImpl.java:434-455`).
  - Per node (line 833): the sum of the `r` values that passed line 828, minus `scheduledSize = blockSize × getBlocksScheduled(t)` (`DatanodeDescriptor.java:819`). This sum is compared with `requiredSize`.

**A3. Mechanism.**

1. **Client asks for a block.** The client calls `addBlock`. `FSDirWriteFileOp.chooseTargetForNewBlock` (`server/namenode/FSDirWriteFileOp.java:267-293`) calls `BlockManager.chooseTarget4NewBlock` (`BlockManager.java:2450-2467`). That calls `BlockPlacementPolicyDefault.chooseTarget` with `blocksize = preferredBlockSize`.
2. **Policy picks candidates.** For each candidate DataNode, `chooseLocalOrFavoredStorage` (`BlockPlacementPolicyDefault.java:641`) or `chooseRandom` (`:880`) calls the wrapper `chooseStorage4Block(dnd, blocksize, results, type)` (`:963-975`). The wrapper calls `dnd.chooseStorage4Block(storageType, blockSize, minBlocksForWrite)` (`:968`). `isGoodDatanode` (`:1090`) does not check space; space is checked only here.
3. **The checks in `DatanodeDescriptor.chooseStorage4Block` (`DatanodeDescriptor.java:816-841`):**
   - `requiredSize = blockSize * minBlocksForWrite` (`:818`), and `scheduledSize = blockSize * getBlocksScheduled(t)` (`:819`).
   - For each storage in state NORMAL of the requested type, the first one seen is kept as the return candidate (`:823-826`). Its remaining `r` (`:827`) is added to `remaining` **only if** [`if (r >= requiredSize)`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/DatanodeDescriptor.java#L828) holds (`:828-830`). A storage with less than N blocks' worth of space counts as zero.
   - [`if (requiredSize > remaining - scheduledSize)`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/DatanodeDescriptor.java#L833) (`:833-839`): the method logs at DEBUG and returns `null`.
   - Otherwise it returns the storage.
4. **Outcome at the limit (null returned).**
   - The wrapper logs reason `NOT_ENOUGH_STORAGE_SPACE` (`BlockPlacementPolicyDefault.java:972`) and the node is not a target.
   - If no node qualifies, `chooseRandom` logs `Not enough replicas was chosen. Reason: {...NOT_ENOUGH_STORAGE_SPACE=...}` at INFO (`:925`) and throws `NotEnoughReplicasException`.
   - For a contiguous file with fewer targets than `minReplication`, `chooseTarget4NewBlock` throws `IOException("File %s could only be written to %d of the %d minReplication nodes ...")` (`BlockManager.java:2469-2476`). The client's write fails, and no bytes go to that DataNode.
5. **Outcome below the limit.** The node is chosen, and `DatanodeStorageInfo.incrementBlocksScheduled` (`BlockManager.java:2400`, `FSDirWriteFileOp.java:785`) adds 1 to the scheduled count. The count is decremented when the DataNode reports the block as received (`BlockManager.addBlock`, `BlockManager.java:4516`). It is also rolled away every 10 min (`DatanodeDescriptor.java:69`, `rollBlocksScheduled` `:877-883`).

**Expected steady state with sequential full-block writes.**

- The last block is accepted while `remaining ≥ N·B`. After that block, remaining is about `N·B − (B + meta)`, which lies in `[(N−1)·B − meta, N·B)`.
- The next block is refused.
- So stored bytes on that DataNode ≈ `capacity − (N−1)·B` at most.

**Bypasses and overshoot.**

- **(a) Stale remaining.** `remaining` is updated only by heartbeats (`dfs.heartbeat.interval`, 3 s, `hdfs-default.xml:941`). In the window after a block is reported received (scheduled −1) and before the next heartbeat, the NameNode sees neither the new bytes nor the scheduled block. Concurrent writes can then over-admit by up to the number of blocks admitted in that window.
- **(b) Partial blocks.** `requiredSize` uses the preferred block size, not actual bytes. Short files are over-reserved; that is conservative.
- **(c) Appends.** Appends to an existing last block reuse that block's pipeline (`server/namenode/FSDirAppendOp.java:128-140`). No `chooseTarget` runs, so up to `blockSize − lastBlockLength` more bytes per file land without this check.
- **(d) Multiple storages.** With several storages of one type, the returned storage is the *first* NORMAL one (`:823-826`), even if that one failed line 828 while another passed. The DataNode then picks the real volume itself (`RoundRobinVolumeChoosingPolicy`, below), so the per-storage filter only decides the node, not the volume.
- **(e) DataNode-side check.** The DataNode volume choice applies its own condition: `availableVolumeSize > blockSize + additionalAvailableSpace` (`server/datanode/fsdataset/RoundRobinVolumeChoosingPolicy.java:110-111`). Here `blockSize` is the new replica's current length (`FsDatasetImpl.java:1639`, `b.getNumBytes()`). `additionalAvailableSpace` defaults to 1 GiB (`DFSConfigKeys.java:1192-1193`, `hdfs-default.xml:2739-2740`). With defaults, the DataNode refuses (DiskOutOfSpaceException) once a volume has ≤ about 1 GiB available. That is earlier than this check whenever `N·blockSize ≤ ~1 GiB`, for example N = 1 with 128 MiB blocks. The verification sets that DataNode key to 0 to isolate the NameNode check.

**A4. Other consumers.** These use the same DataNode disk outside this constraint:

- the DataNode-side volume choice and its 1 GiB headroom (A3 e);
- `dfs.datanode.du.reserved`, which lowers capacity and remaining;
- RBW reservations (`FsVolumeImpl.reservedForReplicas`, `:127-128`, `:632`);
- appends (A3 c);
- block metadata files (`.meta`, about 4 bytes per 512 data bytes);
- the balancer and mover;
- everything non-HDFS on the same filesystem: DataNode logs, other users. These reduce `dfAvailable` and are seen only through `remaining`.

**A5. Evidence beyond the source.**

- `hdfs-default.xml:2462-2469` describes the key.
- Tests:
  - `TestReplicationPolicy.testChosenFailureForNotEnoughStorageSpace` (`hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/blockmanagement/TestReplicationPolicy.java:1738-1758`) sets remaining = 1 block, `setMinBlocksForWrite(2)`, and expects 0 targets and a `NOT_ENOUGH_STORAGE_SPACE` log.
  - `testChooseTarget3` (`:320-325`) makes a node unqualified with remaining = `(MIN_BLOCKS_FOR_WRITE−1)·BLOCK_SIZE`.
  - `TestNameNodeReconfigure.testReconfigureMinBlocksForWrite` (`hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestNameNodeReconfigure.java:666-709`) shows that reconfiguration works and that values ≤ 0 are rejected.
- No JIRA was consulted. The copy has no git history.

## B. Verification solution

**B1. Claim under test.** For a DataNode receiving sequential full-block writes, the NameNode stops placing new replicas on it once its reported remaining space falls below `N × blockSize`, with N = `dfs.namenode.block-placement.min-blocks-for.write`. As a result:

- the number of blocks stored before writes are refused falls by one for each +1 in N, `K(N) ≈ K(1) − (N − 1)`;
- the free space left on the DataNode at refusal grows by one block for each +1 in N, and lies in `[(N−1)·B, N·B)`;
- raising or lowering N at runtime moves the stopping point the same way.

### B2. Unit tier

**B2a. Environment and build.**

- Software and module: JDK 8, Maven 3.3+, module `hadoop-hdfs-project/hadoop-hdfs`.
- Source copy: copy the tag source to local disk first. Never build in the shared tree:
  ```
  rsync -a <source-tag-copy>/ $RUN/src/
  cd $RUN/src
  ```
  Here `$RUN` is a run directory on local disk, for example `/mydata/<run-dir>/o24`.
- Build: `mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
- New test file: `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/blockmanagement/TestMinBlocksForWriteCap.java`, in the copy only. It is in package `...blockmanagement` so it can call the package-private `incrementBlocksScheduled`, `updateStorage` and `setUtilizationForTesting`.
- Run: `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestMinBlocksForWriteCap -DtrimStackTrace=false`. The JVM needs no special options; surefire's default heap is enough.

**B2b. Knobs.** N = `minBlocksForWrite` ∈ {1, 4, 8, 16}. These values make the predicted change (1 block per +1) far larger than the meta and directory slack, and 16 still leaves half of a 32-block capacity.

- U1 sets N with the method argument.
- U2 sets N with `conf.setInt("dfs.namenode.block-placement.min-blocks-for.write", N)` before the MiniDFSCluster starts. U2's control also changes it at runtime with `cluster.getNameNode().reconfigurePropertyImpl(key, "1")`.
  - *Amendment 2026-11-25 (stage-4 audit, before run 1):* `reconfigurePropertyImpl` is `protected` in `NameNode` (`NameNode.java:2338`) and cannot be called from package `...blockmanagement`. Use the public `cluster.getNameNode().reconfigureProperty(key, "1")` (`ReconfigurableBase.java:224`), which checks that the key is reconfigurable and then calls `reconfigurePropertyImpl`. Same effect; B2f and B2g unchanged.

Fixed:

- `dfs.blocksize` = 1048576 (B = 1 MiB, the NameNode minimum).
- `dfs.replication` = 1.
- `dfs.datanode.round-robin-volume-choosing-policy.additional-available-space` = 0, so the DataNode-side check (A3 e) does not bind.
- `dfs.namenode.redundancy.considerLoad` = false.
- `dfs.heartbeat.interval` = 1.

**B2c. Workload.**

- **U1, pure placement, no I/O.** Build a DatanodeDescriptor with `DFSTestUtil.createDatanodeStorageInfo("s1", "1.1.1.1")`, then `.getDatanodeDescriptor()`. Call `storage.setUtilizationForTesting(cap, used, r, used)` and `dn.chooseStorage4Block(StorageType.DISK, B, N)`, with B = 1024 and N = 4 (requiredSize = 4096).
  - U1a: sweep r ∈ {4095, 4096, 4097, 8192}.
  - U1b: r = 8192, then call `dn.incrementBlocksScheduled(DISK)` k = 0..5 times. The node is accepted iff `8192 − 1024·k ≥ 4096`, that is k ≤ 4.
  - U1c: a second storage, `dn.updateStorage(new DatanodeStorage("s2"))`. Both storages get r = 3072 (each < 4096, sum 6144 ≥ 4096). This shows the per-storage filter of line 828.
  - U1d: storages with r = {4096, 1000}. Accepted, and the returned storage is s1 if s1 is the first iterated.
- **U2, MiniDFSCluster, real block files.**
  - Cluster: `new MiniDFSCluster.Builder(conf).numDataNodes(1).storagesPerDatanode(1).storageCapacities(new long[][]{{C}}).build()` with C = 32 MiB = 33554432. The builder applies `FsVolumeImpl.setCapacityForTesting` (`MiniDFSCluster.java:1898-1900`).
  - Loop i = 1, 2, …: `DFSTestUtil.createFile(fs, new Path("/fill/f"+i), B, (short)1, i)`, which writes one full 1 MiB block and closes the file.
  - After each file: `DataNodeTestUtils.triggerHeartbeat(dn)`, then `GenericTestUtils.waitFor(() -> nnDesc.getRemaining() == vol.getAvailable(), 100, 10000)`. Here `nnDesc = cluster.getNamesystem().getBlockManager().getDatanodeManager().getDatanode(dn.getDatanodeId())` and `vol` = the single `FsVolumeImpl`.
  - Stop at the first `IOException`; K = i − 1.
- **Arithmetic.** meta per block m = 1048576/512·4 + 7 = 8199 B, so each file costs B + m = 1056775 B. Let d0 = the initial dfsUsed (a few KiB of directories). Then `K(N) = floor((C − d0 − N·B)/(B+m)) + 1`, which gives K = 31, 28, 24, 16 for N = 1, 4, 8, 16, valid for any d0 < 800 KB. Real disk use is at most about 33 MiB.

**B2d. Observables and instruments.**

- U1: the return value (null or storage ID), and the DEBUG line `does not have enough DISK space (required=…, scheduled=…, remaining=…)` (`DatanodeDescriptor.java:834-837`). Enable it with `GenericTestUtils.setLogLevel(BlockPlacementPolicy.LOG, Level.DEBUG)`.
- U2, for each i:
  - `nnDesc.getRemaining()`, the operand `r` as the NameNode sees it;
  - `vol.getDfsUsed()`;
  - `vol.getAvailable()`;
  - the exception message (must contain `could only be written to 0 of the 1 minReplication nodes`).
- U2 at the end: `FileUtils.sizeOfDirectory(new File(vol.getBaseURI()))`, the actual bytes in the volume directory, and the count of `blk_*` files without `.meta`. Print all of these as one CSV line per i.
- Cannot be observed directly: the transient `scheduledSize` inside the call. The DEBUG line shows it.

**B2e. Procedure.**

1. Copy the tree and build (B2a).
2. Write `TestMinBlocksForWriteCap`:
   - `@Test u1aThreshold`, `u1bScheduled`, `u1cPerStorageFilter`, `u1dFirstStorageReturned`;
   - `@Test u2Fill` (parameterised over N ∈ {1, 4, 8, 16}; a fresh cluster per N, shut down in `finally`);
   - `@Test u2Reconfigure` (N = 16 fill until refused, then `reconfigurePropertyImpl(key,"1")`, continue the loop until refused again). *(Amendment 2026-11-25: called through the public `reconfigureProperty`, see B2b.)*
   - *Amendment 2026-11-25:* `@Test u2DnSideControl` runs the B2h side control (additional-available-space left at its 1 GiB default, N = 1, C = 32 MiB; expected K = 0 with a DataNode-side refusal). U1d also prints a supplementary variant (b) with the two `r` values swapped between the first- and second-iterated storage, to show bypass (d); it is a reading only, not a B2f prediction.
3. Run with `-Dtest=TestMinBlocksForWriteCap`. Save `target/surefire-reports/*-output.txt`.
4. Collect the CSV lines. Do not assert the exact K inside the test; print it, so a mismatch is a reading, not a crash.

**B2f. Predictions.**

| Case | Prediction |
|---|---|
| U1a | null for r = 4095; storage for r = 4096, 4097 and 8192. |
| U1b | Accepted for k = 0..4; null for k = 5. |
| U1c | null, even though the node total is 6144 ≥ 4096. |
| U1d | Non-null; returns s1. |
| U2 | K = 31 / 28 / 24 / 16 for N = 1 / 4 / 8 / 16 (±1 if d0 is unexpectedly large). `nnDesc.getRemaining()` at refusal lies in `[(N−1)·B − m, N·B)`: about 0.78 / 3.78 / 7.78 / 15.78 MiB. Bytes in the volume dir ≈ K·1056775 + d0. |
| u2Reconfigure | 16 files, then refusal. After reconfiguring to 1, 15 more, so 31 total, matching N = 1. |
| All U2 | The DataNode never throws DiskOutOfSpaceException. |

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| K(N) = 31, 28, 24, 16 (±1) and refusal-time remaining in `[(N−1)B, NB)` | Claim confirmed: the check bounds the stored bytes, and N moves the bound one block per step. |
| K the same for every N | Claim refuted: N does not govern placement. Look for another binding check (DataNode-side, considerLoad). |
| K falls with N but not one-for-one (for example a step of 2 per +1) | Mechanism differs from the trace (scheduled not decremented, stale remaining). Partly confirmed. |
| Refusal comes from a DataNode `DiskOutOfSpaceException` and not from the NameNode `could only be written` message | The DataNode check bound, not this one. The run is not a test of the claim: check that additional-available-space = 0. |
| U1a accepts r = 4095, or U1c accepts | The code does not behave as traced at line 828. Refuted at the unit level. |
| u2Reconfigure: no writes after reconfiguring to 1 | Refusal was not caused by N. Refuted. |
| u2Reconfigure: resumes to 31 total | Positive control: same workload, cap moves with N. |

**B2h. Controls.**

- N = 1 is the baseline (default).
- u2Reconfigure changes only N on the same running cluster, with the same disk state, so disk, DataNode and data are held fixed.
- additional-available-space = 0 removes the DataNode-side headroom. A side run with it left at the 1 GiB default and C = 32 MiB should give K = 0 with a DataNode `Out of space` warning, which shows that this check is distinct from the NameNode check.
- Heartbeat and remaining are synchronised after each write, which removes staleness (A3 a).
- considerLoad = false removes load-based exclusion.

### B3. Cluster tier

**B3a. Environment and build.**

- **Host and daemons:** one Linux host with JDK 8, pseudo-distributed. One NameNode and one DataNode only. No YARN, and no SecondaryNameNode is started.
- **Build:**
  ```
  cd $RUN/src
  mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true
  ```
  Unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `$RUN/hadoop`, or reuse an existing built distribution of the tag. Set `export HADOOP_HOME=$RUN/hadoop HADOOP_CONF_DIR=$RUN/conf HADOOP_LOG_DIR=$RUN/logs HADOOP_PID_DIR=$RUN/pids`. In `hadoop-env.sh`: `HADOOP_HEAPSIZE_MAX=1g`.
- **Disk of known size, without root.** Point `dfs.datanode.data.dir` at `$RUN/dn` on a local filesystem with ≥ 2 GiB free. Set `dfs.datanode.du.reserved` = (filesystem total bytes) − 268435456, computed as `R=$(( $(df -B1 --output=size $RUN | tail -1) - 268435456 ))`.
  - Then capacity = 256 MiB. While non-HDFS use stays below `R`, `getAvailable` reduces to `256 MiB − dfsUsed` (`FsVolumeImpl.java:474-482`, `:514-521`): other activity on the shared disk cancels out.
  - Check before the run: `df -B1 --output=used $RUN` < R, and free ≥ 1 GiB.
  - *Amendment 2026-11-25 (stage-4 audit, before run 1; runbook defect 1).* The method above fails on a filesystem with root-reserved blocks. `DF.getAvailable()` is `File.getUsableSpace()` (blocks available to non-root) and `DF.getUsed()` is total − free (`hadoop-common .../fs/DF.java:85-97`), so the second operand of `getAvailable` is `usable + used − R − dfsUsed = 256 MiB − rootReserve − dfsUsed`. On the stage-4 nodes `/mydata` is ext4 with the default 5 % root reserve (about 41 GB on `pc91`: size 807902732288, used 12248985600, avail 754539712512), so remaining would be 0 from the start and every write would be refused at N = 1. **Use a loop filesystem without a root reserve instead, and keep the du.reserved arithmetic so the capacity is exactly 256 MiB:** `truncate -s 512M $RUN/vol.img; mkfs.ext2 -F -q -m 0 $RUN/vol.img; sudo mount -o loop $RUN/vol.img $RUN/dnfs; sudo chown $USER $RUN/dnfs`; `dfs.datanode.data.dir = $RUN/dnfs/dn`; `R=$(( $(df -B1 --output=size $RUN/dnfs | tail -1) - 268435456 ))`. With no root reserve, usable = free, so both operands of `getAvailable` reduce to `256 MiB − dfsUsed`. (*Second amendment, same day, at the setup check before any put:* ext4 even with `-m 0` keeps reserved clusters for delayed allocation, 2 % of the blocks capped at 4096 clusters, which `statfs` counts as free but not available; on the 512 MiB image that is 2621 × 4096 = 10735616 B, and the setup check read `DFS Remaining` 257675264 instead of 268410880. That would lower every K by about 2.5 blocks. ext2 has no such reserve; with it the setup check reads `DFS Remaining` = 268410880 = 256 MiB − d0.) The loop filesystem holds only this run's DataNode data, so other users of `/mydata` cannot move it. `du -sb` and the block count below read `$RUN/dnfs/dn`. Unmount in cleanup (B4 step 3). B3f and B3g are unchanged.
  - Alternative with sudo: a loop file `truncate -s 256M $RUN/vol.img; mkfs.ext4 -F -m 0 $RUN/vol.img; sudo mount -o loop $RUN/vol.img $RUN/dn`, `chown`, with du.reserved = 0.
- **`core-site.xml`:**
  - `fs.defaultFS = hdfs://localhost:29820`
  - `hadoop.tmp.dir = $RUN/tmp`
- **`hdfs-site.xml`:**
  - `dfs.namenode.name.dir = $RUN/nn`
  - `dfs.datanode.data.dir = $RUN/dn`
  - `dfs.replication = 1`
  - `dfs.blocksize = 4194304` (B = 4 MiB)
  - `dfs.datanode.du.reserved = R`
  - `dfs.datanode.round-robin-volume-choosing-policy.additional-available-space = 0`
  - `dfs.namenode.redundancy.considerLoad = false`
  - `dfs.heartbeat.interval = 1`
  - `dfs.namenode.block-placement.min-blocks-for.write = N`
  - non-default ports: `dfs.namenode.http-address = localhost:29870`, `dfs.datanode.address = localhost:29866`, `dfs.datanode.http.address = localhost:29864`, `dfs.datanode.ipc.address = localhost:29867`, `dfs.namenode.secondary.http-address = localhost:29868`. Check first that they are free with `ss -ltn`.

**B3b. Knobs.** N ∈ {1, 8, 16, 32}. With B = 4 MiB and 256 MiB capacity, these give headrooms of 4 / 32 / 64 / 128 MiB, so the cap moves visibly up to half the disk.

- Set N in the NameNode's `hdfs-site.xml`, then `hdfs dfsadmin -reconfig namenode localhost:29820 start`. Confirm with `hdfs dfsadmin -reconfig namenode localhost:29820 status`, which must show the key's old → new value. No restart is needed.
- Between values of N, empty HDFS: `hdfs dfs -rm -r -skipTrash /fill`. Wait until `hdfs dfsadmin -report` shows `DFS Used` < 1 MiB, because the DataNode deletes blocks asynchronously.

**B3c. Workload.**

- Make a source file: `head -c 4194304 /dev/urandom > $RUN/blk4m`, one full block.
- For each N, run sequentially:
  ```
  i=0
  while hdfs dfs -put $RUN/blk4m /fill/f$((i+1)) 2>>$RUN/put-N.err; do
    i=$((i+1))
    sleep 3
  done
  echo $i
  ```
  `sleep 3` is greater than two heartbeats, so the NameNode sees fresh remaining. `hdfs dfs -mkdir -p /fill` comes first.
- Arithmetic: per file B + m = 4194304 + 32775 = 4227079 B. `K(N) = floor((268435456 − d0 − N·B)/4227079) + 1`, which gives K ≈ 63 / 56 / 48 / 32 for N = 1 / 8 / 16 / 32, i.e. K ≈ 64 − N.
- Duration: about 5 s per put, so ≤ about 6 min per N and about 25 min in all.

**B3d. Observables and instruments.**

| What | Tool |
|---|---|
| K (files written before the first failure) | The loop counter |
| The failure text | `put-N.err`. Expect `could only be written to 0 of the 1 minReplication nodes. There are 1 datanode(s) running and ...` |
| NameNode reason | `grep "NOT_ENOUGH_STORAGE_SPACE" $RUN/logs/hadoop-*-namenode-*.log`, from the INFO line `Not enough replicas was chosen` |
| *Amendment 2026-11-25 (stage-4, before cluster run 1):* NameNode disallow evidence | With the writer on the DataNode's host (pseudo-distributed, and MiniDFSCluster), `NOT_ENOUGH_STORAGE_SPACE` is never logged: `chooseLocalStorage` adds the local node to `excludedNodes` before calling `chooseStorage4Block` (`BlockPlacementPolicyDefault.java:635`), and `chooseRandom` then clears the reason map (`:835`) and, the only node being excluded, logs `{NO_REQUIRED_STORAGE_TYPE=1}` (`:851`, `:925`); the client message ends `... and 1 node(s) are excluded in this operation`. The direct evidence that line 828/833 refused is the DEBUG line `The node ... does not have enough DISK space (required=N·B, scheduled=…, remaining=…)` (`DatanodeDescriptor.java:834`), so `log4j.logger.org.apache.hadoop.hdfs.server.blockmanagement.BlockPlacementPolicy=DEBUG` is **required**, not optional. Found in the unit tier's log (it applies to U2 as well) and checked in the source. |
| DataNode side must be silent | `grep -c "Out of space\|less than the block size" $RUN/logs/*datanode*.log` must be 0 |
| Actual bytes on disk | `du -sb $RUN/dn` after each N, and `find $RUN/dn -name 'blk_*' ! -name '*.meta' \| wc -l` |
| Reported remaining and used | `hdfs dfsadmin -report` (Configured Capacity, DFS Used, DFS Remaining), and `curl -s 'http://localhost:29864/jmx?qry=Hadoop:service=DataNode,name=FSDatasetState*'` (Capacity, DfsUsed, Remaining). Sample both after each put (append to a CSV) and at refusal. |

Cannot be observed directly: the NameNode's blocks-scheduled count. Infer it from the DEBUG line, by setting `log4j.logger.org.apache.hadoop.hdfs.server.blockmanagement.BlockPlacementPolicy=DEBUG` in `$HADOOP_CONF_DIR/log4j.properties` if needed.

**B3e. Procedure.**

1. Check the ports and free disk, and compute R.
2. Write the configuration. Run `hdfs namenode -format -nonInteractive`.
3. Start the daemons with `hdfs --daemon start namenode` and `hdfs --daemon start datanode`. Run `hdfs dfsadmin -safemode wait`. Check `hdfs dfsadmin -report`: Configured Capacity should be ≈ 268435456.
4. For N in 1, 8, 16, 32:
   - set N and reconfigure (B3b);
   - empty `/fill` and wait;
   - run the loop;
   - record K, `du -sb $RUN/dn`, `dfsadmin -report`, the DataNode JMX output and the log greps.
5. Positive control, without emptying: with N = 32 at its refusal point, reconfigure to N = 1. Continue the loop from the current i until it fails again. Record the new total.
6. Optional DataNode-side control:
   - stop the DataNode;
   - set additional-available-space back to the 1 GiB default (remove the key);
   - start the DataNode and set N = 1, with `/fill` emptied;
   - run the loop. Expect K = 0, with a DataNode `Out of space` / `less than the block size` warning and a client pipeline error instead of the NameNode message.
7. Clean up (B4).

**B3f. Predictions.**

| N | K (±1) | `DFS Remaining` at refusal | `du -sb $RUN/dn` (≈ K·4227079 + d0) |
|---|---|---|---|
| 1 | 63 | [0, 4 MiB) | ≈ 266 MB |
| 8 | 56 | [28, 32) MiB | ≈ 237 MB |
| 16 | 48 | [60, 64) MiB | ≈ 203 MB |
| 32 | 32 | [124, 128) MiB | ≈ 135 MB |

- Every refusal is a NameNode `could only be written` message with `NOT_ENOUGH_STORAGE_SPACE` in the NameNode log, and the DataNode log has no `Out of space` line.
- Positive control (step 5): after reconfiguring to 1, about 31 more files are written, for 63 in total (±1), and `du` rises to ≈ 266 MB.
- DataNode control (step 6): K = 0.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| K ≈ 64 − N, refusal-time remaining in `[(N−1)B, NB)`, `du` falling about 4.2 MB per +1 N | Claim confirmed: N governs the bytes really stored on the DataNode. |
| K identical for all N (≈ 63) | Claim refuted: N does not cap usage. |
| Refusals come from the DataNode (`Out of space`), or the NameNode log has no `NOT_ENOUGH_STORAGE_SPACE` | Another check bound. Not a test of the claim; fix the configuration and repeat. |
| *Amended 2026-11-25:* read the row above as: refusals come from the DataNode (`Out of space` / `less than the block size`), or the NameNode log has no DEBUG `does not have enough DISK space` line from `DatanodeDescriptor.java:834` at the refusal (with `remaining` < `required` = N·B) | Another check bound. Not a test of the claim. An INFO reason `NO_REQUIRED_STORAGE_TYPE` with that DEBUG line is the expected NameNode refusal for a local writer (B3d amendment). |
| K larger than predicted by several blocks | Over-admission (stale remaining or scheduled counts). The cap exists but is loose; report the overshoot. |
| Step 5 does not resume | The refusal was not caused by N. Refuted. |
| Step 5 resumes to about 63 | Positive control: the same workload moves usage when only N changes. |
| `dfsadmin -report` Configured Capacity ≠ 256 MiB | Setup error (du.reserved). Readings are invalid. |

**B3h. Controls.**

- All N values run against the same daemons, disk, block size and file source. Only N changes, and it changes by live reconfiguration.
- Step 5 changes N with the disk state fixed.
- Step 6 shows what a DataNode-side refusal looks like, so the two kinds of refusal can be told apart.
- `sleep 3` between puts removes the stale-remaining effect. A variant with `sleep 0` (back-to-back puts) may show the overshoot of A3 a; report it separately, not as a refutation.
- The du.reserved arithmetic is checked through Configured Capacity.

**B4. Risks and cleanup.**

- **Disk.** Unit tier: ≤ about 40 MB in the surefire test dir; the full module build uses several GB in `$RUN/src` and `~/.m2`. Cluster tier: ≤ 256 MiB in `$RUN/dn`, plus about 50 MB of logs. Keep everything under `$RUN` on local disk, never on NFS or shared project storage. With the du.reserved method, other users filling the same disk to within 256 MiB of full would end the run early. Check `df` before the run.
- **Ports.** 29820 / 29864 / 29866-29870 must be free; change them if they are in use.
- **Cleanup.**
  1. `hdfs --daemon stop datanode; hdfs --daemon stop namenode`.
  2. `jps` must show no `NameNode` or `DataNode` started from `$RUN`. Check `ps -ef | grep $RUN`, and `kill` any leftover.
  3. If the loop alternative was used: `sudo umount $RUN/dn` (*amended 2026-11-25:* `sudo umount $RUN/dnfs`, then `rm $RUN/vol.img`).
  4. `rm -rf $RUN/dn $RUN/nn $RUN/tmp $RUN/logs $RUN/pids` once the readings are saved.
  5. Unit tier: MiniDFSCluster is shut down in `finally`. Check `jps` for a surefire JVM left running.

## C. Sources read

```
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/DatanodeDescriptor.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/BlockPlacementPolicyDefault.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/BlockPlacementPolicy.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/BlockManager.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/DatanodeStorageInfo.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/BlockUnderConstructionFeature.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/ReplicationWork.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/ErasureCodingWork.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/common/HdfsServerConstants.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/NameNode.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirWriteFileOp.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirAppendOp.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsVolumeImpl.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsVolumeList.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetImpl.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/RoundRobinVolumeChoosingPolicy.java
hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/HdfsClientConfigKeys.java
hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/blockmanagement/TestReplicationPolicy.java
hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/blockmanagement/BaseReplicationPolicyTest.java
hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestNameNodeReconfigure.java
hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/DFSTestUtil.java
hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/MiniDFSCluster.java
hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/DataNodeTestUtils.java
hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/SimulatedFSDataset.java
~/writeup-hadoop/playbook-autonomous.md
~/writeup-hadoop/_TEMPLATE-autonomous.md
```

## D. Stage-4 feedback

**2026-11-25, stage 4 run 1 (Jingsong's share, node `pc91`): unit Confirmed — caps; cluster Confirmed — caps. Outcome class: true positive.** Results: `results/dfs.namenode.block-placement.min-blocks-for.write-chooseStorage4Block-requiredSize--autonomous.md`.

- Unit (B2): U1a–U1d as predicted; U2 K = 31 / 28 / 24 / 16 for N = 1 / 4 / 8 / 16 (exactly B2f), refusal-time remaining 769831 / 3940156 / 8167256 / 16621456 B, each in `[(N−1)·B − m, N·B)`; u2Reconfigure 16 → +15 = 31; DataNode-side control K = 0. Each NN refusal has the DEBUG line of `DatanodeDescriptor.java:834`.
- Cluster (B3, amended): K = 63 / 56 / 48 / 32 for N = 1 / 8 / 16 / 32 (exactly B3f); `DFS Remaining` at refusal 2.01 / 29.83 / 62.08 / 126.58 MB, each in `[(N−1)·B, N·B)`; `du -sb` 266.3 / 236.8 / 202.9 / 135.3 MB; step 5 32 → +31 = 63; step 6 K = 0 with a DataNode `Out of space`. No DataNode out-of-space line in any N run.
- Supplementary U1d(b) shows bypass (d): with storages r = {1000 (first iterated), 4096} the node is accepted and the returned storage is the one that failed line 828.
- Amendments made by the audit (dated 2026-11-25, above): B2b/B2e (`reconfigureProperty`; extra U2 DataNode-side control; U1d(b)); B3a (loop ext2 filesystem instead of du.reserved on the root-reserved `/mydata`); B3d/B3g (the NameNode reason for a local writer is `NO_REQUIRED_STORAGE_TYPE`; the disallow evidence is the DEBUG line at `:834`). For stage 3: B2c should say to set utilization on the descriptor's registered storage (`dn.getStorageInfo("s1")`), not on the object `DFSTestUtil.createDatanodeStorageInfo` returns, and that `MiniDFSCluster.Builder` forces additional-available-space = 0 (`MiniDFSCluster.java:551-553`).
