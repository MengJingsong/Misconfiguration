# dfs.datanode.du.reserved — verification solution  <!-- file: cases/dfs.datanode.du.reserved-chooseStorage4Block-remaining--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatanodeDescriptor.java:833`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/DatanodeDescriptor.java#L833): `if (requiredSize > remaining - scheduledSize)` in `DatanodeDescriptor.chooseStorage4Block(StorageType, long, int)` (NameNode-side block placement) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive`: the check refuses to place a new block replica on a DataNode storage type whose heartbeat-reported free space, less the bytes already scheduled to it, is below `blockSize × min-blocks-for.write`. The reported free space already has `dfs.datanode.du.reserved` subtracted on the DataNode, so the HDFS block bytes written to a volume stop at about `capacity − du.reserved`. The overshoot is bounded by one block per concurrent writer, plus a stale-heartbeat window. |
| Ground | — |

Name parts: constraint = `dfs.datanode.du.reserved` (the key a user tunes to set the limit-side value; see A1 for the other sources), function = `chooseStorage4Block` (the method that directly encloses the given if), operand = `remaining` (the limit-side operand at the check; the comparison is `requiredSize > remaining - scheduledSize`, so `requiredSize` is the demand side).

## A. Constraint trace

**A1. The constraint.**

- **Name:** `dfs.datanode.du.reserved`. It also has two override forms: `dfs.datanode.du.reserved.<dir>` and `dfs.datanode.du.reserved.<storage type>`, and the two can be combined as `dfs.datanode.du.reserved.<dir>.<storage type>`. For this case the operand at the check is `remaining`. This is the per-storage free space that the DataNode reports. The key is the user-tunable input that sets it.
- **Kind:** configuration key, read by the DataNode.
- **Declared at:** [`DFSConfigKeys.java:964`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java#L964): `DFS_DATANODE_DU_RESERVED_KEY = "dfs.datanode.du.reserved"`. The default is `DFS_DATANODE_DU_RESERVED_DEFAULT = 0` (`DFSConfigKeys.java:965`).
- **`hdfs-default.xml` entry:** `hdfs-default.xml:396-417`, value `0`, with the text "Reserved space in bytes per volume. Always leave this much space free for non dfs use." The Java constant and the XML value agree (0).
- **Unit:** bytes per volume. Size suffixes are accepted (`conf.getLongBytes`, `ReservedSpaceCalculator.java:112-118`). The per-dir and per-type forms are read with `getLong`, so they take plain bytes.
- **How it is read:** `ReservedSpaceCalculator.getReservedFromConf` (`ReservedSpaceCalculator.java:112-118`) resolves the key in this order: dir + type, then dir, then type, then the plain key.
- **Calculator:** the default calculator is `ReservedSpaceCalculatorAbsolute` (`DFSConfigKeys.java:962-963`; `hdfs-default.xml:383-394`). It returns this byte value (`ReservedSpaceCalculator.java:131-147`). The other calculators (Percentage, Conservative, Aggressive; `ReservedSpaceCalculator.java:152-240`) combine it with `dfs.datanode.du.reserved.pct`.
- **When it takes effect:** the calculator is built once per volume, in the `FsVolumeImpl` constructor (`FsVolumeImpl.java:172-175`). The DataNode has no reconfiguration hook for this key (`DataNode.java` has no reference to it), so a change needs a **DataNode restart**.
- **Where to set it:** `hdfs-site.xml` on the DataNode.

Other sources that shape the limit-side value `remaining`:

- **The physical volume:** `DF` total, free and usable space (`DF.java:85-97`).
- **HDFS bytes already stored:** `dfsUsed`.
- **Space held for in-progress writes:** `reservedForReplicas`.
- **Same-disk tiering ratios**, if enabled.
- **Demand side:** `requiredSize = blockSize × minBlocksForWrite` (`DatanodeDescriptor.java:818`). `minBlocksForWrite` comes from `dfs.namenode.block-placement.min-blocks-for.write`:
  - Declared at `DFSConfigKeys.java:1299-1302`, with default `HdfsServerConstants.MIN_BLOCKS_FOR_WRITE = 1` (`HdfsServerConstants.java:47`); `hdfs-default.xml:2462-2469` also gives `1`.
  - Read by the NameNode at `BlockPlacementPolicyDefault.java:167-169`.
  - Can be changed at runtime with `hdfs dfsadmin -reconfig namenode` (`NameNode.java:380`, `2380-2381`, `2750-2758`).

**A2. What it caps.** This caps disk space on a DataNode volume: the bytes of HDFS block and meta files written under the volume's `dfs.datanode.data.dir`.

The quantity the check compares is the NameNode's view of the storage type's free space:

- `remaining` is the sum of `DatanodeStorageInfo.getRemaining()` over NORMAL storages of type `t` that each have at least `requiredSize` free (`DatanodeDescriptor.java:822-830`).
- From it the check subtracts `scheduledSize = blockSize × getBlocksScheduled(t)` (`DatanodeDescriptor.java:819`).
- The result is compared against `requiredSize = blockSize × minBlocksForWrite`.

`getRemaining()` holds the `remaining` field of the last heartbeat's `StorageReport` (`DatanodeStorageInfo.java:325-330`). The DataNode fills that field from `FsVolumeImpl.getAvailable()` (`FsDatasetImpl.java:160-184`, at `:173`):

```
getCapacity()  = max(DF.total - reserved, 0)                          (FsVolumeImpl.java:434-460; configuredCapacity only in tests)
getAvailable() = max(min(getCapacity() - dfsUsed - reservedForReplicas,
                         DF.usable - max(reserved - actualNonDfsUsed, 0) - reservedForReplicas), 0)
                                                                      (FsVolumeImpl.java:474-482, 514-521)
actualNonDfsUsed = max(DF.used - dfsUsed, 0)                          (FsVolumeImpl.java:484-506, DF.used = total - free)
```

Assume `reserved > actualNonDfsUsed`. That is the case whenever the reservation is larger than the other data already on the filesystem. Then the second branch is always the smaller one:

```
remaining = T' - reserved - dfsUsed - reservedForReplicas,   where T' = DF.total - (DF.free - DF.usable) = df "used" + df "avail".
```

So setting `dfs.datanode.du.reserved = T' - H` gives HDFS a budget of exactly `H` bytes on that volume. Other users' writes on the same filesystem do not change this, as long as they stay below the reservation. The verification relies on this result.

**A3. Mechanism.**

1. **DataNode side.** Each heartbeat (`dfs.heartbeat.interval`, default 3 s) carries one `StorageReport` per volume. Each report holds `remaining = FsVolumeImpl.getAvailable()` (`FsDatasetImpl.java:169-177`), which already excludes `du.reserved`, as shown in A2.
2. **NameNode records it.** `DatanodeDescriptor.updateHeartbeatState` → `updateStorageStats` → `DatanodeStorageInfo.updateState(r)` sets `remaining = r.getRemaining()` (`DatanodeDescriptor.java:396-404`, `DatanodeStorageInfo.java:325-330`).
3. **The scheduled-bytes counter.** It covers writes the NameNode has allocated but the DataNode has not yet reported received:
   - Incremented at block allocation (`FSDirWriteFileOp.java:778-786` → `DatanodeStorageInfo.java:337-342`).
   - Decremented when the DataNode reports the block received (`BlockManager.java:4508-4516`) or when the block is abandoned (`BlockManager.java:1384`, `FSDirWriteFileOp.java:85`).
   - Rolled every 10 minutes, `curr → prev` (`DatanodeDescriptor.java:69`, `877-883`). As a result, a count that was never decremented ages out after 10–20 minutes.
4. **Placement.** A client `addBlock` → `FSDirWriteFileOp.chooseTargetForNewBlock` → `BlockManager.chooseTarget4NewBlock` (`FSDirWriteFileOp.java:293`) → `BlockPlacementPolicyDefault`:
   - For the local node: `chooseLocalStorage`, `BlockPlacementPolicyDefault.java:641`.
   - For random choice: `chooseRandom`, `BlockPlacementPolicyDefault.java:880`.
   - Both go through `chooseStorage4Block(dnd, blockSize, results, type)` (`:963-976`), which calls `dnd.chooseStorage4Block(type, blockSize, minBlocksForWrite)` (`:968`).
5. **The check:** [`DatanodeDescriptor.java:833`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/DatanodeDescriptor.java#L833), `if (requiredSize > remaining - scheduledSize)`.
   - **True (not enough space):** logs at DEBUG and returns `null` (`:834-838`). The policy records `NOT_ENOUGH_STORAGE_SPACE` (`BlockPlacementPolicyDefault.java:972`, reason text at `:89`) and tries another node.
   - **If no node qualifies:** `chooseRandom` throws `NotEnoughReplicasException`, and the reason map is logged at INFO as `Not enough replicas was chosen. Reason: {NOT_ENOUGH_STORAGE_SPACE=…}` (`BlockPlacementPolicyDefault.java:902-927`). `BlockManager.chooseTarget4NewBlock` then throws `IOException("File … could only be written to 0 of the 1 minReplication nodes. There are N datanode(s) running and … node(s) are excluded in this operation.")` (`BlockManager.java:2469-2476`). The client's write fails.
   - **False:** returns the first NORMAL storage of type `t` (`:824-826`, `:840`).
6. **DataNode-side second gate.** When the pipeline opens, `FsDatasetImpl.createRbw` → `FsVolumeList.getNextVolume` (`FsDatasetImpl.java:1639`) → `RoundRobinVolumeChoosingPolicy.chooseVolume`. This accepts a volume only if `getAvailable() > blockSize + additionalAvailableSpace`, and otherwise throws `DiskOutOfSpaceException("Out of space: …")` (`RoundRobinVolumeChoosingPolicy.java:110-126`).
   - `dfs.datanode.round-robin-volume-choosing-policy.additional-available-space` defaults to **1 GiB** (`DFSConfigKeys.java:1189-1193`, `hdfs-default.xml:2739-2740`).
   - With that default, the DataNode gate binds **before** the NameNode check whenever free space is between `B` and `B + 1 GiB`. So the verification sets it to 0 to isolate the target check, and uses the default as a control.
   - The volume then reserves `blockSize` (`reserveSpaceForReplica`, `FsVolumeImpl.java:620-634`) until the replica is finalized. Finalizing adds `numBytes + meta length` to `dfsUsed` (`BlockPoolSlice.java:444-454`).

Paths that bypass the check or overshoot it:

- **Stale view:** `remaining` is up to one heartbeat old. After a block is received, `scheduledSize` drops at once, but `remaining` only drops at the next heartbeat. A new block allocated in that window can be placed one block too many. The DataNode gate in step 6 then catches it if the volume really has `≤ B` available.
- **Summed free space and the returned storage:** `remaining` is summed over every storage of the type that has at least `requiredSize` free. The storage returned is simply the first NORMAL one, which may itself be full. The DataNode's volume chooser picks the real volume.
- **Rolling of `scheduledSize`:** if many blocks stay scheduled longer than 10–20 minutes (slow writers), the count ages out and the check under-counts.
- **Writes not covered by the check:**
  - Growth of an already-allocated block, via append or `hflush`, up to `blockSize`. Append has its own DataNode check (`FsVolumeImpl.java:1264-1268`).
  - Balancer and Mover target choice (`Dispatcher` uses `maxSize2Move − scheduledSize`, `Dispatcher.java:583-614`).
  - The DataNode's own non-block files.
- **Configured capacity in tests:** `configuredCapacity` (`setCapacityForTesting`, `MiniDFSCluster.Builder.storageCapacities`) replaces `total − reserved` in the first branch (`FsVolumeImpl.java:436-444`). The verification must not use it.

**A4. Other consumers.** Other things that use disk on the same filesystem, outside this constraint's control:

- DataNode and NameNode logs (`HADOOP_LOG_DIR`).
- The NameNode metadata directory, if on the same disk. This is governed by `dfs.namenode.resource.du.reserved`, `DFSConfigKeys.java:1243-1244`, a separate check.
- `hadoop.tmp.dir`.
- Other users' files on the filesystem.
- The filesystem's root-reserved blocks (`DF.free − DF.usable`).

These consume the reservation rather than HDFS's budget; see the A2 algebra. If they grow beyond the reservation, HDFS's remaining shrinks further. HDFS's own meta files and directory blocks count in `dfsUsed`, so they are inside the budget.

**A5. Evidence beyond the source.**

- [`hdfs-default.xml` r3.4.2](https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/hdfs-default.xml): descriptions of `dfs.datanode.du.reserved`, `dfs.datanode.du.reserved.calculator`, `dfs.namenode.block-placement.min-blocks-for.write`, and `dfs.datanode.round-robin-volume-choosing-policy.additional-available-space`. Local copy: `hdfs-default.xml:383-433`, `2462-2469`, `2739-2745`.
- Existing tests:
  - `TestReplicationPolicy.testChooseTarget3` (`src/test/.../blockmanagement/TestReplicationPolicy.java:318-345`) gives a node `remaining = (MIN_BLOCKS_FOR_WRITE − 1) × BLOCK_SIZE` and asserts it is never chosen.
  - `TestReservedSpaceCalculator` covers the calculators.
  - `TestNameNodeReconfigure.java:669-670` covers runtime reconfiguration of min-blocks-for.write.
- No JIRA was relied on.

## B. Verification solution

**B1. Claim under test.** On a single DataNode volume with `dfs.datanode.du.reserved = T' − H` (with the DataNode's own extra-space gate disabled), the NameNode stops placing new blocks there once `remaining − scheduled×B < k×B` (k = `min-blocks-for.write`). So the HDFS bytes on that volume never exceed `H`, and the write that would exceed it fails at the NameNode with `NOT_ENOUGH_STORAGE_SPACE`. The claim is refuted if:

- block bytes on the volume exceed `H`; or
- the number of blocks accepted does not follow `H` and `k` as predicted; or
- writes are refused while `remaining − scheduled×B ≥ k×B`.

### B2. Unit tier

**B2a. Environment and build.** JDK 8, Maven ≥ 3.3, Linux.

1. Copy the tag tree to local disk (never the shared copy): `rsync -a <hadoop-3.4.2 source>/ $WORK/hadoop-src/`.
   *Amendment D1-4 (2026-11-25, environment only): on the stage-4 nodes the copy is made with `copy-source.sh /mydata/jingsong-s4/<stem>-run1/src`, and step 2 is replaced by an offline `mvn -o -pl hadoop-hdfs-project/hadoop-hdfs test-compile`, because every 3.4.2 module is already installed in `~/.m2` by the node build (`environment.md` §3). `$WORK/minidfs` is `-Dtest.build.data=<run>/test-data` (the test puts each cluster under `<test-data>/o25/<tag>`).*
2. Build the dependencies: `cd $WORK/hadoop-src && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
3. Add the test class `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/blockmanagement/TestChooseStorage4BlockReserved.java`. It must be in this package to call the package-private `DatanodeStorageInfo.getRemaining()` and `DatanodeDescriptor.incrementBlocksScheduled(StorageType)`.
4. Run it: `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestChooseStorage4BlockReserved -Dhdfs.minidfs.basedir=$WORK/minidfs`. `$WORK` is on local disk with at least 2 GiB free.
5. Use the default surefire JVM options. Set `log4j` to INFO for `BlockPlacementPolicy` so the `Not enough replicas was chosen` line is captured.

**B2b. Knobs.**

U1 (the check alone, no DataNode):
- `remaining` ∈ {k·B − 1, k·B, k·B + 1, (k+1)·B, (k+2)·B}.
- `scheduled` ∈ {0, 1, 2}: call `dn.incrementBlocksScheduled(StorageType.DISK)` s times.
- `k` ∈ {1, 3}.
- B = 1024.

These values put the boundary on each side by 1 byte and by whole blocks.

U2 (the operand derived from the key, with a real DataNode):
- `H` ∈ {32 MiB, 64 MiB}, and `k` ∈ {1, 3}.
- Set `dfs.datanode.du.reserved = T' − H` in the test `Configuration` before `MiniDFSCluster` starts. Compute T' in the test as `f.getTotalSpace() − (f.getFreeSpace() − f.getUsableSpace())` for `f = new File(baseDir)` (create `baseDir` first).
- Set `k` with `conf.setInt("dfs.namenode.block-placement.min-blocks-for.write", k)`.
- Fixed settings:
  - `dfs.blocksize = 4194304` (B = 4 MiB)
  - `dfs.replication = 1`
  - `dfs.heartbeat.interval = 1`
  - `dfs.datanode.round-robin-volume-choosing-policy.additional-available-space = 0`
- Cluster shape: `numDataNodes(1)`, `storagesPerDatanode(1)`, **no** `storageCapacities`, and the real `FsDatasetImpl` (not `SimulatedFSDataset`).
- Each (H, k) pair is a fresh cluster: four cluster starts.

**B2c. Workload.**

U1: build a descriptor with `DatanodeStorageInfo s = DFSTestUtil.createDatanodeStorageInfos(1)[0]` and take `dn = s.getDatanodeDescriptor()`. For each knob tuple:
1. `s.setUtilizationForTesting(cap=10·B, dfsUsed=0, remaining=R, bpUsed=0)`.
   *Amendment D1-1 (stage 4, 2026-11-25): `s` must be the descriptor's registered storage, `s = dn.getStorageInfo(s0.getStorageID())` with `s0 = DFSTestUtil.createDatanodeStorageInfos(1)[0]`. The object `createDatanodeStorageInfos` returns is a second `DatanodeStorageInfo`, not the one in the descriptor's storage map (`DFSTestUtil.java:1295-1305`, `BlockManagerTestUtil.java:357-375`), so utilization set on it never reaches `chooseStorage4Block`. Use a fresh descriptor per tuple; heartbeat first, then call `incrementBlocksScheduled` s times (the first heartbeat may roll the scheduled counters, `DatanodeDescriptor.java:877-883`).*
2. `dn.updateHeartbeat(BlockManagerTestUtil.getStorageReportsForDatanode(dn), 0, 0, 0, 0, null)`.
3. Call `dn.chooseStorage4Block(StorageType.DISK, B, k)` and record whether it returns null.

U2:
1. Start the cluster.
2. Read `ε = dn.getStorageInfos()[0].getDfsUsed()` after the first heartbeat.
3. Write files `/fill/f<i>`, each exactly B bytes (one block), one at a time.
4. Before each create, `sleep 2500 ms` (≥ 2 heartbeats) so `remaining` is fresh.
5. Write until two consecutive failures, or 40 files.

Arithmetic for U2: each finalized block adds `b' = B + meta` to `dfsUsed`. With CRC32C/512, meta = 7 + B/512×4, so `b' = 4,194,304 + 32,775 = 4,227,079`. After i blocks, `remaining = H − ε − i·b'`. The (i+1)-th block is accepted while `remaining ≥ k·B`. So `N(H,k) = floor((H − ε − k·B)/b') + 1`, and the workload (40 × 4 MiB = 160 MiB) exceeds every H.

**B2d. Observables and instruments.** All read in-JVM. Before each write:
- `remaining = storageInfo.getRemaining()` (the NameNode-side operand)
- `sched = dn.getBlocksScheduled(StorageType.DISK)`
- the predicted outcome `pred = dn.chooseStorage4Block(DISK, B, k) != null`

After each write:
- success or failure, and the exception message
- DataNode-side `FsVolumeImpl.getAvailable()`, `getDfsUsed()` and `getReserved()` (via `cluster.getDataNodes().get(0).getFSDataset().getFsVolumeReferences()`)
  *Amendment D1-2 (2026-11-25): `FsVolumeImpl.getReserved()` is package-private (`FsVolumeImpl.java:556`) and the test lives in the `blockmanagement` package; it is read by reflection (`setAccessible`). The NameNode-side operand is read from the NameNode's own descriptor, `cluster.getNamesystem().getBlockManager().getDatanodeManager().getDatanode(dn.getDatanodeId())`.*
- the bytes of block files on disk (sum of file lengths under the volume's `current/BP-*/current/finalized`)

What cannot be observed directly: the exact moment a heartbeat lands. It is controlled by the sleep.

**B2e. Procedure.**

1. Build (B2a).
2. Run U1. Assert, for every tuple, `null ⇔ k·B > R − s·B`.
3. For each (H, k), run U2:
   1. Create `baseDir`, compute `T'`, and assert `T' − H > (f.getTotalSpace() − f.getFreeSpace())`. That is, the reservation exceeds the current non-HDFS use. Skip with a message if not.
   2. Start the cluster, read `ε`, and assert `getReserved() == T' − H` and `|remaining − (H − ε)| ≤ 1 MiB` on the first heartbeat.
   3. Run the write loop, logging one line per file: `i remaining sched pred outcome finalizedBytes`.
   4. Assert: `outcome == pred` for every i; the number of successes equals `N(H,k)`; and `finalizedBytes ≤ H` throughout.
   5. Shut the cluster down.

**B2f. Predictions** (ε is a few tens of KB of directory blocks and `VERSION`; the values below use ε ≈ 0, and N changes only if ε > 200 KB):

| H | k | N(H,k) accepted blocks | block bytes on disk after last success |
|---|---|---|---|
| 32 MiB (33,554,432) | 1 | floor(29,360,128/4,227,079)+1 = **7** | 7·b' ≈ 29.6 MB ≤ H |
| 32 MiB | 3 | floor(20,971,520/4,227,079)+1 = **5** | ≈ 21.1 MB |
| 64 MiB (67,108,864) | 1 | floor(62,914,560/4,227,079)+1 = **15** | ≈ 63.4 MB ≤ H |
| 64 MiB | 3 | floor(54,525,952/4,227,079)+1 = **13** | ≈ 55.0 MB |

The first failure in every case is a NameNode-side `IOException … could only be written to 0 of the 1 minReplication nodes`, with INFO `Not enough replicas was chosen. Reason: {NOT_ENOUGH_STORAGE_SPACE=1}`.
*Amendment D2-1 (2026-11-25, after unit attempt 1; numbers unchanged, unit tier restarted): the INFO reason map cannot carry `NOT_ENOUGH_STORAGE_SPACE` here. The writer runs on the DataNode's host, so placement first tries `chooseLocalStorage` (`BlockPlacementPolicyDefault.java:630-655`), which calls the check and records the reason, and then falls back to `chooseRandom`, which **clears** the reason map at entry (`:835`) and, with the only node already excluded, records `NO_REQUIRED_STORAGE_TYPE` (`:845-852`). The disallow-branch evidence is therefore the check's own DEBUG line, `The node … does not have enough DISK space (required=k·B, scheduled=…, remaining=R)` (`DatanodeDescriptor.java:834-837`, logger `BlockPlacementPolicy` at DEBUG), logged by a NameNode `IPC Server handler` thread at each refused write with `remaining < required`. Wherever B2f/B2g/B3f/B3g/B3h say "`NOT_ENOUGH_STORAGE_SPACE`" read "that DEBUG line (and the client's `could only be written to 0 of the 1 minReplication nodes`)". The client message alone does not separate the gates: after a DataNode `Out of space` the client excludes the node and the NameNode then gives the same message.* For U1, `null` exactly when `R − s·B < k·B`; for example, R = k·B, s = 0 gives non-null, and R = k·B − 1 gives null.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| U1 truth table matches `k·B > R − s·B` exactly | the check works as traced |
| U1 non-null while `R − s·B < k·B` (or null while ≥) | traced mechanism wrong: claim refuted at the check |
| U2: `remaining ≈ H − ε − i·b'` and successes = N(H,k), failure carries `NOT_ENOUGH_STORAGE_SPACE` | du.reserved sets the operand and the check caps HDFS bytes at ≤ H: claim confirmed |
| U2: successes continue well past N (block bytes > H) | the constraint does not cap usage: claim refuted |
| U2: `remaining` does not track `H − dfsUsed` (e.g. ≈ raw df free) | the operand is not governed by the key (check B2e step 3.1 precondition, `storageCapacities` not set) |
| U2: failures earlier than N with DataNode `DiskOutOfSpaceException: Out of space` and no `NOT_ENOUGH_STORAGE_SPACE` | the DataNode gate bound, not the target check (additional-available-space not 0): not confirmed, fix setup |
| U2: N changes with k as predicted | demand side of the check confirmed too |

**B2h. Controls.**

*Amendment D1-3 (2026-11-25): the `MiniDFSCluster.Builder` constructor itself sets `additional-available-space = 0` (`MiniDFSCluster.java:551-553`). The main runs keep that (as B2b asks); Control B sets the key to its 1 GiB default **after** the Builder is constructed and before `build()`, otherwise Control B would silently run with 0.*

- **Control A (cap absent):** the same loop with `H = 512 MiB` and 40 files of 4 MiB (160 MiB). All 40 should succeed. This shows the refusals come from H, not the workload.
- **Control B (other gate):** `H = 64 MiB` with `additional-available-space` left at its 1 GiB default. The first write should fail at the DataNode (`Out of space`). This shows the main runs isolate the NameNode check.
- **Prediction check:** `pred` recorded before each write lets each outcome be matched to the check's own evaluation.
- **No simulated capacity:** `storageCapacities` must not be set, so the real `total − reserved` path is used.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, pseudo-distributed HDFS: one NameNode and one DataNode, with no YARN and no SecondaryNameNode. JDK 8.

*Amendment D1-5 (2026-11-25, environment only): the distribution is the node's full build `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2`, copied with `cp -a` to `$RUN/hadoop` (`environment.md` §4), instead of rebuilding and untarring. `$RUN = /mydata/jingsong-s4/<stem>-run1/cluster`; each fresh cluster (each H and each control) gets its own `HADOOP_LOG_DIR = $RUN/logs-<label>`, so the B3d log greps count per run. Daemons are started and stopped with `hdfs --daemon` (no SSH to localhost on the nodes).*

Build:
```
cd $WORK/hadoop-src && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true
tar -xzf hadoop-dist/target/hadoop-3.4.2.tar.gz -C $RUN
export HADOOP_HOME=$RUN/hadoop-3.4.2
```
`$RUN` is a local-disk directory, e.g. under `/mydata`, never NFS. It must have `df --output=avail` ≥ 4 GiB.

Environment variables (in `etc/hadoop/hadoop-env.sh` or exported):
- `HADOOP_CONF_DIR=$RUN/conf` (copy `etc/hadoop` there)
- `HADOOP_LOG_DIR=$RUN/logs`
- `HADOOP_PID_DIR=$RUN/pids`
- `HADOOP_HEAPSIZE_MAX=1g`

`core-site.xml`:
- `fs.defaultFS = hdfs://localhost:19000`
- `hadoop.tmp.dir = $RUN/tmp`

`hdfs-site.xml`:

| Key | Value |
|---|---|
| `dfs.namenode.name.dir` | `$RUN/nn` |
| `dfs.datanode.data.dir` | `$RUN/dn` |
| `dfs.replication` | `1` |
| `dfs.blocksize` | `16777216` |
| `dfs.heartbeat.interval` | `1` |
| `dfs.datanode.round-robin-volume-choosing-policy.additional-available-space` | `0` |
| `dfs.namenode.block-placement.min-blocks-for.write` | `1` |
| `dfs.datanode.du.reserved` | (B3b) |

*Amendment D2-1 (cluster): add `log4j.logger.org.apache.hadoop.hdfs.server.blockmanagement.BlockPlacementPolicy=DEBUG` to `$HADOOP_CONF_DIR/log4j.properties`, so the NameNode log carries the check's DEBUG line (see B2f).*

Ports, moved off the defaults to avoid clashes on a shared host:

| Key | Value |
|---|---|
| `dfs.namenode.http-address` | `0.0.0.0:19870` |
| `dfs.datanode.address` | `0.0.0.0:19866` |
| `dfs.datanode.http.address` | `0.0.0.0:19864` |
| `dfs.datanode.ipc.address` | `0.0.0.0:19867` |

**B3b. Knobs.**

Primary knob: `H` ∈ {256 MiB, 512 MiB, 1 GiB}. These give 15–63 blocks, enough to see the cap without much disk. Set the key through `H`:
```
read USED AVAIL < <(df -B1 --output=used,avail $RUN/dn | tail -1)
R=$((USED + AVAIL - H))
```
Then write `dfs.datanode.du.reserved = $R` (plain bytes) into `hdfs-site.xml`. Precondition: `AVAIL > H + 2 GiB`, so the reservation exceeds the non-HDFS use. Recompute R and **restart the DataNode** for each H. Wipe `$RUN/dn` and reformat between runs (B3e).

Secondary knob: `k = dfs.namenode.block-placement.min-blocks-for.write` ∈ {1, 4} at H = 512 MiB. Change it at runtime:
```
hdfs dfsadmin -reconfig namenode localhost:19000 start
hdfs dfsadmin -reconfig namenode localhost:19000 status
```
after editing `hdfs-site.xml`. No restart is needed.

**B3c. Workload.**
```
head -c 16777216 /dev/urandom > $RUN/f16m
hdfs dfs -mkdir /fill
for i in $(seq 1 80); do
  hdfs dfs -put $RUN/f16m /fill/f$i && st=ok || st=fail
  sleep 3
  <record readings>
done
```
Stop after 3 consecutive failures. 80 × 16 MiB = 1.25 GiB is more than every H. Each file is one block; after finalize, `b' = 16,777,216 + 131,079 = 16,908,295` bytes of `dfsUsed`. The `sleep 3` (3 heartbeats at 1 s) keeps `remaining` fresh. A run takes about 4–6 minutes.

**B3d. Observables and instruments.** After each put, record:
- **The actual resource:** `du -sb $RUN/dn/current | cut -f1`, plus the finalized-only sum from `find $RUN/dn/current -path '*finalized*' -type f -printf '%s\n' | awk '{s+=$1} END {print s}'`.
- **The DataNode's reported value:** `curl -s 'http://localhost:19864/jmx?qry=Hadoop:service=DataNode,name=FSDatasetState*'` → `Remaining`, `DfsUsed`, `Capacity`.
- **The NameNode's view:** `hdfs dfsadmin -report` → `DFS Remaining`, `DFS Used`, `Configured Capacity`.
- **Filesystem state:** `df -B1 --output=used,avail $RUN/dn`, to confirm other usage stayed below R.
- **The put outcome and stderr.**

After the run, collect:
- `grep -c 'NOT_ENOUGH_STORAGE_SPACE' $RUN/logs/*namenode*.log`
- `grep -c 'Out of space' $RUN/logs/*datanode*.log`

Not directly observable: the NameNode's `scheduledSize` (not exported per type). It is expected to be 0 between sequential puts.

**B3e. Procedure** (per H, k = 1):

1. Stop any previous daemons: `hdfs --daemon stop datanode; hdfs --daemon stop namenode`. Then `rm -rf $RUN/nn $RUN/dn $RUN/tmp`.
2. Compute R (B3b) and write it to `hdfs-site.xml`.
3. Format and start the daemons:
   ```
   hdfs namenode -format -force -nonInteractive
   hdfs --daemon start namenode
   hdfs --daemon start datanode
   ```
   Wait for `hdfs dfsadmin -safemode get` to show OFF and `-report` to show 1 live DataNode.
4. Check the starting state: `Configured Capacity ≈ H + (DF.free − DF.usable)` and `DFS Remaining ≈ H − ε` (within 1 MiB).
5. Run the workload (B3c) and record readings to `$RUN/readings-H<h>.txt`.
6. Grep the logs (B3d).
7. For H = 512 MiB, add a second pass:
   1. `hdfs dfs -rm -r -skipTrash /fill`, then wait until `DFS Remaining` returns to ≈ H. Block deletion is asynchronous.
   2. Set k = 4 via reconfig and rerun the loop.
8. Run the controls (B3h).
9. Clean up (B4).

**B3f. Predictions** (ε ≈ tens of KB):

| H | k | accepted puts N = floor((H − ε − k·B)/b') + 1 | finalized bytes at stop | first failure |
|---|---|---|---|---|
| 256 MiB (268,435,456) | 1 | floor(251,658,240/16,908,295)+1 = **15** | 15·b' = 253,624,425 ≤ H | put 16, NameNode `could only be written to 0 of the 1 minReplication nodes`, NameNode log `NOT_ENOUGH_STORAGE_SPACE` |
| 512 MiB (536,870,912) | 1 | floor(520,093,696/16,908,295)+1 = **31** | 524,157,145 ≤ H | put 32, same |
| 1 GiB (1,073,741,824) | 1 | floor(1,056,964,608/16,908,295)+1 = **63** | 1,065,222,585 ≤ H | put 64, same |
| 512 MiB | 4 | floor(469,762,048/16,908,295)+1 = **28** | 473,432,260 | put 29, same |

Further predictions:
- In every run, finalized bytes ≤ H.
- After the stop, `DFS Remaining` < k·B. For example, at H = 256 MiB it is ≈ 14.8 MB.
- The DataNode log has no `Out of space` line.
- The relation is exact up to ±1 accepted put, which allows for ε and a stale heartbeat.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| accepted puts = N(H,k) ±1, finalized bytes ≤ H, failure with `NOT_ENOUGH_STORAGE_SPACE` | du.reserved caps HDFS disk use through the target check: claim confirmed |
| accepted puts and bytes scale with H (15/31/63) | usage follows the knob |
| puts continue past N; finalized bytes > H by more than one block | the constraint does not cap usage: claim refuted |
| `Remaining` in JMX ≈ raw `df avail` rather than H − DfsUsed | the key does not set the operand (precondition AVAIL > H + 2 GiB violated, or another calculator configured): not confirmed |
| failures come with DataNode `Out of space` and no NameNode `NOT_ENOUGH_STORAGE_SPACE` | the DataNode gate bound, not the target check: not confirmed for this check (check additional-available-space = 0) |
| k = 4 run gives 28 accepted puts vs 31 at k = 1 | demand side of the check confirmed |
| refusal while `DFS Remaining` ≥ k·B + slack | an unknown gate is binding: claim refuted for the mechanism |
| *(D1-6)* Control 3: `Remaining` unchanged within 1 MiB, `df used` +≈200 MiB | the reservation algebra holds |
| *(D1-6)* Control 3: `Remaining` drops by ≈200 MiB | the budget is not set by H as derived: cluster tier Not confirmed |
| *(D1-7)* Control 1 refuses a put, or Control 2's first put succeeds | the workload or the isolation of the two gates is broken: cluster tier Invalid |

**B3h. Controls.**
- **Control 1 (cap far away):** H = 2 GiB with the same 80-put workload stopped at 64 puts (1 GiB). All 64 succeed and `du` ≈ 64·b' = 1,082,130,880. This shows the workload itself does not fail.
- **Control 2 (DataNode-side gate):** H = 512 MiB with `additional-available-space` removed (1 GiB default). The first put fails, the DataNode log shows `Out of space`, and the NameNode log shows no `NOT_ENOUGH_STORAGE_SPACE`. It separates the two gates.
- **Control 3 (non-HDFS writes):** during the H = 512 MiB run, write a 200 MiB non-HDFS file into `$RUN/scratch` on the same filesystem, and remove it afterwards. Per A2, `Remaining` must not change, because non-HDFS use stays below R. This confirms the reservation algebra.
  *Amendment D1-6 (2026-11-25): exact timing and reading. The file is written right after put 10's readings, with `dd if=/dev/zero bs=1M count=200 conv=fsync`; JMX `Remaining` and the report's `DFS Remaining` are read 3 s before the `dd` and 4 s and 7 s after it, with no put in between, and `df used` is recorded alongside to show the file landed. Conclusion rows (added to B3g): `Remaining` unchanged within 1 MiB while `df used` grows by ≈200 MiB → the A2 algebra holds (other users' files consume the reservation, not HDFS's budget); `Remaining` drops by ≈200 MiB → the budget is not `T' − R − dfsUsed`, the H arithmetic of B3f does not hold, and the verdict is at most Not confirmed for the cluster tier.*
- **Interference checks:** record `df` throughout to rule out other users' activity crossing R. Run `jps` before start to make sure no other NameNode or DataNode of this run is present.

**B4. Risks and cleanup.**

- **Disk:** the unit tier needs ≤ 1 GiB under `$WORK/minidfs`; the cluster tier needs ≤ 2.2 GiB under `$RUN`. Both must be on local disk, not shared storage.
- **A huge `du.reserved` hides space from HDFS only.** It does not reserve the space on the filesystem. Other users of the filesystem are unaffected, and the NameNode's own `dfs.namenode.resource.du.reserved` (100 MB) check stays satisfied as long as the disk has more than 100 MB free.
- **Ports 19000/19864/19866/19867/19870:** check them first with `ss -ltn`.
- **Cleanup:** `hdfs --daemon stop datanode; hdfs --daemon stop namenode`. Confirm with `jps` that no `NameNode` or `DataNode` started by this run is left. Then `rm -rf $RUN/nn $RUN/dn $RUN/tmp $RUN/f16m $RUN/scratch`, keeping logs and readings.
- **Unit tier:** `MiniDFSCluster.shutdown()` in `@After`; delete `$WORK/minidfs`.
- **Source tree:** never build in or add the test class to the shared source tree; use the local copy.

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/DatanodeDescriptor.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/BlockPlacementPolicyDefault.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/DatanodeStorageInfo.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/BlockManager.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirWriteFileOp.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/NameNode.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/common/HdfsServerConstants.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsVolumeImpl.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/ReservedSpaceCalculator.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetImpl.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsVolumeList.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/BlockPoolSlice.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/RoundRobinVolumeChoosingPolicy.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/balancer/Dispatcher.java (grep only)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/mover/Mover.java (grep only)
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/DF.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/blockmanagement/TestReplicationPolicy.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/blockmanagement/BaseReplicationPolicyTest.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/blockmanagement/BlockManagerTestUtil.java (grep only)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/MiniDFSCluster.java (grep only)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestNameNodeReconfigure.java (grep only)
- https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/hdfs-default.xml (cited; content as in the local hdfs-default.xml)

## D. Stage-4 feedback

**2026-11-25, stage 4 run 1 (node `pc75`, Jingsong's share): Confirmed — caps (both tiers); outcome class true positive.** Results: `results.md` beside this file (to be filed as `hadoop/stage4-runtime-verification/jingsong/results/dfs.datanode.du.reserved-chooseStorage4Block-remaining--autonomous.md`).

- Unit tier: U1 30/30 tuples match `null ⇔ k·B > R − s·B`; U2 accepted blocks 7 / 5 / 15 / 13 for (32 MiB, 1) / (32 MiB, 3) / (64 MiB, 1) / (64 MiB, 3), exactly N(H,k); `remaining` fell by exactly b' = 4,227,079 per block; finalized bytes ≤ H throughout; each refusal had the check's DEBUG line from a NameNode IPC thread. Control A 40/40; Control B refused at the DataNode (`Out of space`) with no NameNode check line.
- Cluster tier: accepted puts 15 / 31 / 63 at H = 256 / 512 / 1024 MiB (k = 1) and 28 at H = 512 MiB, k = 4; finalized bytes 253,624,425 / 524,157,145 / 1,065,222,585 / 473,432,260, equal to B3f; `DFS Remaining` at stop < k·B; the check's DEBUG line at every refused put; no DataNode `Out of space`. Control 1 64/64; Control 2 0 accepted with DataNode `Out of space` only; Control 3 left `Remaining` unchanged (to the byte) while `df used` grew by 200 MiB.
- Runbook defect (D2-1): the INFO reason `NOT_ENOUGH_STORAGE_SPACE` never appears with a writer on the DataNode's host (the reason map shows `NO_REQUIRED_STORAGE_TYPE`); the disallow evidence is the check's DEBUG line. Stage 3 should predict log signatures from the whole placement path (`chooseLocalStorage` then `chooseRandom`), not from the check alone.

### D1. Stage-4 audit amendments (2026-11-25, before any reading)

Applied by the stage-4 session (Jingsong's share, queue order 25) before run 1; none changes B1's claim or the B2f/B3f numbers.

| Id | Where | What | Why |
|---|---|---|---|
| D1-1 | B2c U1 step 1 | set utilization on the descriptor's registered storage | the returned storage object is not the one the check iterates |
| D1-2 | B2d | read `getReserved()` by reflection; NameNode-side values from the NameNode's descriptor | package-private accessor |
| D1-3 | B2h | Control B sets `additional-available-space` after the Builder | the Builder forces it to 0 |
| D1-4 | B2a | per-case copy by `copy-source.sh`, offline test-compile | node environment |
| D1-5 | B3a | node's built distribution copied per run; per-run log dirs; `--daemon` | node environment |
| D1-6 | B3h, B3g | exact timing and conclusion rows for Control 3 | the control had no reading rule |
| D1-7 | B3g | rows for a failed Control 1 / Control 2 | unstated outcomes |
| D2-1 | B2f, B2g, B3a, B3d, B3f, B3g, B3h | disallow-branch evidence is the check's DEBUG line from a NameNode IPC thread, not the INFO `NOT_ENOUGH_STORAGE_SPACE` reason | runbook defect found in unit attempt 1: with a co-located writer the reason map is cleared by `chooseRandom` (source fact, `BlockPlacementPolicyDefault.java:630-655, 835, 845-852`); counts and claim unchanged; unit tier restarted |

Recommendations not applied (for stage 3): the knob's default (`du.reserved = 0`, H = the whole 750 GB disk) is not run, because filling the disk is not allowed on the shared node; Controls A and 1 (cap far away) stand in for it. The unit tier has two H values (plus Control A at 512 MiB); a third would make "follows H" a three-point relation in-JVM too.
