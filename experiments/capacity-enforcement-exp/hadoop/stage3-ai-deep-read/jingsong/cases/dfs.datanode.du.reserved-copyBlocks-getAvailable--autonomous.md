# dfs.datanode.du.reserved — verification solution  <!-- file: cases/dfs.datanode.du.reserved-copyBlocks-getAvailable--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DiskBalancer.java:1138`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DiskBalancer.java#L1138), `if (dest.getAvailable() > item.getBytesToCopy())` in `DiskBalancer.DiskBalancerMover.copyBlocks` (row unit; this is also the main and only space guard on the disk-balancer write path) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous agent, 2026-11-24 |
| Estimate | `positive`: the disk balancer moves a block onto the destination volume only while that volume's HDFS-available space, which is `DF` space minus `dfs.datanode.du.reserved` minus RBW reservations, is above the step's **total** `bytesToCopy`. So the destination stops with at least `bytesToCopy - (one block + meta)` of headroom above the reserve, and the copied amount shrinks byte-for-byte as the reserve grows. The only overshoot into the reserve is bounded by one block. It happens when a plan's `bytesToCopy` is smaller than a block, which a high per-step `tolerancePercent` allows, or when concurrent client writes race the check. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `dfs.datanode.du.reserved`, a configuration key. It is declared at
  [`DFSConfigKeys.java:964-965`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java#L964-L965)
  (`DFS_DATANODE_DU_RESERVED_KEY = "dfs.datanode.du.reserved"`, `DFS_DATANODE_DU_RESERVED_DEFAULT = 0`).
  - The `hdfs-default.xml` entry is at `hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml:397-418`, with value `0`.
  - The Java default and the XML default agree (0 bytes).
- **Unit:** bytes per volume. `conf.getLongBytes` reads it, so size suffixes such as `10g` are accepted (`ReservedSpaceCalculator.java:112-118`).
- **Variants, most specific first** (`ReservedSpaceCalculator.getReservedFromConf`, `ReservedSpaceCalculator.java:112-118`; documented in `hdfs-default.xml:399-415`):
  1. `dfs.datanode.du.reserved.<dir>.<storage_type>`
  2. `dfs.datanode.du.reserved.<dir>`
  3. `dfs.datanode.du.reserved.<storage_type>`
  4. `dfs.datanode.du.reserved`

  `<dir>` is the volume's root: the configured data directory, i.e. the parent of `current/`, from `FsVolumeImpl.java:173-176`. The storage type is lower-case (`disk`, `ssd`, ...).
- **Calculator:** which keys are used depends on `dfs.datanode.du.reserved.calculator` (`DFSConfigKeys.java:959-963`, `hdfs-default.xml:383`).
  - The default, `ReservedSpaceCalculatorAbsolute`, reads only this key (`ReservedSpaceCalculator.java:135-146`).
  - The Percentage, Conservative and Aggressive calculators also use `dfs.datanode.du.reserved.pct` (`DFSConfigKeys.java:966-968`).
- **Other inputs to the limit-side value `dest.getAvailable()`:** these are what the check actually compares.
  - The runtime-queried filesystem totals, through `DF`: `File.getTotalSpace/getFreeSpace/getUsableSpace` (`hadoop-common/.../fs/DF.java`).
  - The volume's `dfsUsed`.
  - The volume's `reservedForReplicas` (RBW reservations).
  - `dfs.datanode.fixed.volume.size` (cached capacity), which defaults to off.
- **How to set it:** in `hdfs-site.xml` on the DataNode. The value is read once, when each `FsVolumeImpl` is constructed (`FsVolumeImpl.java:172-177`). It is not in the DataNode's reconfigurable list (`DataNode.java` has no `DU_RESERVED` reference), so a change needs a **DataNode restart**.
- **Reader:** the DataNode process. Its `FsVolumeImpl.getCapacity/getAvailable` values are also reported to the NameNode, and `hdfs diskbalancer -plan` reads them through `DBNameNodeConnector.java:139-141`.

**A2. What it caps.**
- **Resource:** local disk on each DataNode volume. The reserve keeps `R` bytes of each volume's filesystem out of HDFS's reach.
- **Quantity compared at the target:** `dest.getAvailable()`, the destination volume's HDFS-available bytes, against `item.getBytesToCopy()`, the total bytes this work item (source/destination volume pair) is planned to move. The block is copied only if available > bytesToCopy.
- **What is capped here:** how much the disk balancer writes onto the destination volume.
  - `dest.getAvailable()` already has `R` subtracted, so the move stops before HDFS data reaches the reserve.
  - Because the comparison uses the step's whole `bytesToCopy`, it actually stops while at least about `bytesToCopy` of headroom remains.

**A3. Mechanism.**
1. **Reserve.**
   - `FsVolumeImpl` builds a `ReservedSpaceCalculator` from the configuration (`FsVolumeImpl.java:172-177`).
   - `getReserved()` returns `reserved.getReserved()`, i.e. the configured bytes (`FsVolumeImpl.java:556-558`; `ReservedSpaceCalculator.java:139-146`).
2. **Capacity.** `getCapacity()` = `DF total - reserved` (or `cachedCapacity - reserved`), floored at 0, unless a test fixed `configuredCapacity` (`FsVolumeImpl.java:434-455`).
3. **Available**, at `FsVolumeImpl.java:474-482`:
   - `remaining = getCapacity() - getDfsUsed() - getReservedForReplicas()`
   - `available = DF.getAvailable() (usable) - getRemainingReserved() - getReservedForReplicas()`, where `getRemainingReserved() = max(R - actualNonDfsUsed, 0)` and `actualNonDfsUsed = max(DF used - dfsUsed, 0)` (`FsVolumeImpl.java:484-522`).
   - The method returns `max(min(remaining, available), 0)`.
   - When `R >= actualNonDfsUsed` (R reaches past the non-HDFS data), the `available` arm equals `total - g - dfsUsed - R - rfr`, where `g = free - usable` is the filesystem's root-reserved space. This is never larger than the `remaining` arm, so **`getAvailable() = total - g - R - dfsUsed - rfr`** decreases 1:1 with both R and HDFS bytes on the volume.
4. **Plan to work item.**
   - `submitPlan`, then `createWorkPlan`, turns each plan `MoveStep` into a `DiskBalancerWorkItem(bytesToMove, 0)`, summing steps that have the same volume pair (`DiskBalancer.java:179-199`, `DiskBalancer.java:605-628`).
   - The per-step `bandwidth`, `tolerancePercent` and `maxDiskErrors` are copied over.
   - A single thread runs `copyBlocks` for each pair (`DiskBalancer.java:578-596`).
5. **Loop in `copyBlocks`** (`DiskBalancer.java:1052-1186`). Per iteration:
   - It stops on too many errors (`:1101`).
   - It stops when "close enough" (`:1109`, `isCloseEnough`: `bytesToCopy < copied*(1+tol/100)`, `:882-886`).
   - It picks the next block of size ≤ `(bytesToCopy - copied)*(1+tol/100)` (`getNextBlock`/`getBlockToCopy`/`isLessThanNeeded`, `:1007-1028`, `:952-981`, `:855-861`).
   - Then comes **the check**,
     [`DiskBalancer.java:1138`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DiskBalancer.java#L1138):
     `if (dest.getAvailable() > item.getBytesToCopy())`.
6. **True branch:** `dataset.moveBlockAcrossVolumes(block, dest)` (`:1139-1142`).
   - It copies block and meta into the destination's `tmp` dir (`FsDatasetImpl.java:1207-1214`, `FsVolumeImpl.moveBlockToTmpLocation`).
   - It finalizes on the destination: `BlockPoolSlice.addFinalizedBlock` increments the destination `dfsUsed` by `numBytes + meta length` (`BlockPoolSlice.java:445-455`, through `FsDatasetImpl.java:2009-2053`).
   - It then deletes the source replica (`FsDatasetImpl.java:1164-1196`).
   - `moveBlockAcrossVolumes` itself has **no space check** (`FsDatasetImpl.java:1277-1300`), so line 1138 is the only guard.
   - After the move, the thread sleeps to honor the bandwidth (`:1164-1165`), and `bytesCopied`/`blocksCopied` are updated (`:1170-1171`).
7. **False branch:** the "Destination volume ... does not have enough space to accommodate a block" error is logged, followed by `break` (`:1143-1153`, message at `:1148`).
   - The work item ends with no `errMsg` set and no error counted.
   - The plan still finishes as `PLAN_DONE`.
8. **Resulting bound.** Let `A_k` be the destination's available bytes before move k and `c` the per-block on-disk cost (block plus meta). With no concurrent writers, `A_{k+1} = A_k - c`.
   - Moves happen while `A_k > B` (B = bytesToCopy), so the number of moves is `n = ceil((A0 - B)/c)` when `A0 > B`, capped by the close-enough count.
   - The final headroom is `A0 - n·c` in `(B - c, B]`.
   - So **if B ≥ c the reserve is never entered**, and every extra byte of R removes one byte of copied data (within one block).
9. **Overshoot and bypass paths.**
   - (a) **B < c.** A step whose `bytesToMove` is smaller than a block can still pick a full block if `tolerancePercent` is high, because `isLessThanNeeded` accepts `b ≤ B·(1+tol/100)`. The check then only requires `A > B`, so a block of size up to `B·(1+tol)` plus meta can land with `A < c`. That intrudes into R by up to `c - B`, at most one block, because `isCloseEnough` is then true.
   - (b) **Concurrent writers.** Client or replication writes to the same volume between the check and the copy (the code comment at `:1136-1137` admits the race). The RBW reservations they hold are subtracted through `reservedForReplicas`, but only once they exist.
   - (c) **Meta file not counted** in `block.getNumBytes()`. This is irrelevant to the check, which uses B, but it is part of `c`.
   - (d) **`getAvailable()` clamps at 0**, so the JMX value cannot show an intrusion. It has to be computed from `usedSpace`.
   - (e) **Hand-edited or generated plans.** The planner (`GreedyPlanner.computeMove`, `planner/GreedyPlanner.java:168-208`) sizes `bytesToMove` from the NameNode-reported capacity, which already excludes R. Nothing re-checks R except line 1138.
10. **Over-conservative side effect.** The check compares against total B, not the block size or the remaining bytes. So when `A0 ≤ B` the balancer moves nothing, even though most of B would fit (cf. HDFS-13892 in A5).

**A4. Other consumers.**
- Client writes and re-replication to the same volume, chosen by the volume choosing policy and limited by the same `getAvailable()` elsewhere.
- RBW reservations (`reservedForReplicas`).
- Non-HDFS files on the same filesystem. They count against R first (`getRemainingReserved`).
- The filesystem's own root-reserved blocks (`g`).
- `DU` refresh of `dfsUsed` every `fs.du.interval` (600000 ms, `core-default.xml:1361`). It can re-baseline `dfsUsed` (directory overhead).
- The disk balancer's plan and `before.json` files, which are written into HDFS and may land on any volume.
- DataNode logs, if `HADOOP_LOG_DIR` shares the filesystem.
- The source volume's space is only freed, not consumed.

**A5. Evidence beyond the source.**
- `hdfs-default.xml:397-418`: documents the key and its directory and storage-type variants, and warns that the reserve does not account for `tune2fs` reserved blocks. That matches `g` above.
- `hadoop-hdfs/src/site/markdown/HDFSDiskbalancer.md`: describes the plan, execute and query commands, the `thresholdPercentage`, `bandwidth` and tolerance settings, and the query output fields `bytesToCopy` and `bytesCopied`.
- [HDFS-13892](https://issues.apache.org/jira/browse/HDFS-13892): a DataNode log shows this exact "does not have enough space to accommodate a block" exit, at block size 268435456, while executing a plan onto a newly added non-empty disk. The execute command still returned 0. This shows the false branch firing in practice.
- [HDFS-15440](https://issues.apache.org/jira/browse/HDFS-15440): the tolerance-percent semantics in `isCloseEnough`.
- [HDFS-13728](https://issues.apache.org/jira/browse/HDFS-13728): the planner failing when volume used is greater than capacity. Background only.
- Existing tests: `TestDiskBalancer.java` (MiniDFSCluster and `DataMover` harness, and the spied `moveBlockAcrossVolumes` pattern at `:640-700`) and `DiskBalancerTestUtil.moveAllDataToDestVolume` (`:360-372`). None of them tests the space check.

## B. Verification solution

**B1. Claim under test.** In each disk-balancer work item, the destination volume receives blocks only while its `getAvailable()` (which has `dfs.datanode.du.reserved` subtracted) exceeds `bytesToCopy`. This has three consequences:
- With headroom `A0 = total - g - R - dfsUsed_dest` before the step, the number of blocks copied is `min(n_close, max(0, ceil((A0 - B)/c)))`.
- The destination's headroom above the reserve never ends below `B - c`.
- Raising R by ΔR lowers the bytes written to the destination by ΔR (±1 block).

The claim is refuted if the copied amount is unchanged by R, or if the headroom ends below `B - c` (into the reserve) when B ≥ c.

### B2. Unit tier

**B2a. Environment and build.**
- **Toolchain:** JDK 8 and Maven 3.3+.
- **Source copy:** a private copy of the tag on local disk, e.g. `rsync -a <source>/ /mydata/<runner>/hadoop-src-o26/`. Never use the shared tree.
- **Build:** `cd /mydata/<runner>/hadoop-src-o26 && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
- **New test file:** `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/diskbalancer/TestDiskBalancerDestReserve.java`, in the same package as `TestDiskBalancer`, reusing its imports.
- **Run:** `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestDiskBalancerDestReserve -DfailIfNoTests=false`. The surefire defaults are fine (MiniDFSCluster heap is under 1 GB).
- **Filesystem:** the MiniDFSCluster base dir, `target/test/data/...` under the copy, must be on a **local** filesystem with more than 1 GB usable. Both volumes then share that filesystem, which the arithmetic below assumes.
- *Amendment D1-1 (2026-11-25, stage-4 audit; environment only):* the source copy is made with the stage-4 environment's
  `copy-source.sh` into `/mydata/jingsong-s4/dfs.datanode.du.reserved-copyBlocks-getAvailable-run1/src`; nothing is
  installed (the node's `~/.m2` already holds every 3.4.2 module from the node build); the run is
  `mvn -o -B -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestDiskBalancerDestReserve -DfailIfNoTests=false` with
  `JAVA_HOME` = JDK 8. Readings come from the surefire report and the test's own log lines, not the Maven exit code.

**B2b. Knobs.** `dfs.datanode.du.reserved`, global key, set in the `Configuration` given to the **second** MiniDFSCluster (restart semantics). R is not chosen as a round number. It is computed so that the destination's starting headroom `A0` hits a target:
`R = S·(blocks_total - blocks_free + blocks_avail) - U_dest - A0_target`,
where `S, blocks_*` come from `stat -f`, equivalent to `File.getTotalSpace()`, `getFreeSpace()` and `getUsableSpace()` on the data dir. That is, `R = total - g - U_dest - A0_target`. This follows from A3 step 3. The condition `R ≥ actualNonDfsUsed` holds whenever `usable ≥ A0_target`.

Settings, with B = 40 MiB = 41943040 and c = 1048576 + 8199 = 1056775 (1 MiB block, 512-byte CRC32C chunks, so meta = 7 + 4·2048):

| Run | R | A0 target | Why |
|---|---|---|---|
| U0 (positive control) | 0 | n/a (≈ usable, GBs) | cap not binding; close-enough governs |
| U1 | computed | B + 10.5c = 53039178 | check binds after about 11 blocks |
| U2 | computed | B + 20.5c = 63606928 | check binds after about 21 blocks (shift of about 10 blocks per 10.5c of ΔR) |
| U3 | computed | B − c = 40886265 | A0 < B: zero moves |
| U4 (overshoot probe) | computed | 800000, with B = 600000 and item `tolerancePercent = 100` | B < c: one block passes the check and lands with A0 < c |

Other settings, kept fixed:
- `dfs.blocksize=1048576`
- `dfs.disk.balancer.enabled=true`
- `dfs.disk.balancer.max.disk.throughputInMBperSec=1000`, so the bandwidth sleep is about 1 ms per block
- `dfs.disk.balancer.block.tolerance.percent=10` (the default)
- `dfs.heartbeat.interval=1`
- `fs.du.interval=3600000`, so no DU refresh during the test

**B2c. Workload.**
- Write one 64 MiB file (64 blocks, replication 1) with `DFSTestUtil.createFile(fs, new Path("/f"), 64L<<20, (short)1, 0L)`.
- Gather every block onto volume 0 with `DiskBalancerTestUtil.moveAllDataToDestVolume(dataset, vol1, vol0)`.
- The source then holds 64 MiB, more than B = 40 MiB, so the source never runs out before the check or close-enough stops the copy.
- **Close-enough count:** copying stops after `n_close = 37` blocks, because `36·1.1 = 39.6 MiB < 40` and `37·1.1 = 40.7 MiB > 40`.
- **Binding count:** with R binding, `n = ceil((A0 - B)/c)`. That is 11 for U1, 21 for U2, 0 for U3.
- **U4:** `isLessThanNeeded` accepts a 1 MiB block because `1048576 ≤ 600000·2`. The check passes because `800000 > 600000`. After one block, `isCloseEnough` is true, because `600000 < 1048576·2`.

**B2d. Observables and instruments.**
- **Operand at every pass:** a Mockito `spy` of `FsDatasetSpi`, using the pattern in `TestDiskBalancer.java:640-700`.
  - `doAnswer` on `moveBlockAcrossVolumes(any(), any())` records `((FsVolumeSpi)arg1).getAvailable()` into a list.
  - It then calls the real `node.getFSDataset().moveBlockAcrossVolumes(...)`.
  - This captures `dest.getAvailable()` before each move, which equals the value the check just compared.
- **Destination state before and after:** `dataset.getVolumeInfoMap()`, which is public on `FsDatasetImpl` (`:3319-3333`). For the destination volume it gives `usedSpace` (= `getDfsUsed`), `freeSpace` (= `getAvailable`, clamped at 0), `reservedSpace` (= R) and `numBlocks`.
- **Headroom including any negative part:** `H = total - g - R - usedSpace`, with total and g from the `File` APIs on the data dir.
- **Work item:** `item.getBytesCopied()`, `getBlocksCopied()`, `getErrMsg()`, `getErrorCount()`.
- **Log:** the test log, checked for the line 1148 message ("does not have enough space to accommodate a block") or the line 1110 message ("Copy from ... done").
- **Not observable directly:** the exact physical block allocation of the filesystem. `usedSpace` counts block plus meta bytes, not filesystem blocks or directory inodes. Physical `du` is not needed here because the check uses `dfsUsed`.

**B2e. Procedure.** These steps form one JUnit method per run, or one parameterized method.
1. Set up `conf = new HdfsConfiguration()` with the fixed settings from B2b.
2. Build cluster 1: `cluster1 = new MiniDFSCluster.Builder(conf).numDataNodes(1).storagesPerDatanode(2).storageTypes(new StorageType[]{DISK, DISK}).build(); waitActive()`.
3. Write `/f` as in B2c. Gather all blocks onto volume 0 with `moveAllDataToDestVolume(ds, refs.get(1), refs.get(0))`. Record `srcId = refs.get(0).getStorageID()`, `dstId = refs.get(1).getStorageID()`, the destination path `D = new File(refs.get(1).getBaseURI()).getAbsolutePath()`, and `U_dest = usedSpace(dst)`.
4. Shut down without deleting data: `cluster1.shutdown(false)`. (`MiniDFSCluster.shutdown(boolean deleteDfsDir)` is at `MiniDFSCluster.java:2173`.)
5. Compute R from `File(D)`: `total = getTotalSpace()`, `free = getFreeSpace()`, `usable = getUsableSpace()`, `g = free - usable`, `R = total - g - U_dest - A0_target`. For U0, R = 0. Set `conf.setLong("dfs.datanode.du.reserved", R)`.
6. Build cluster 2 on the same data: `cluster2 = new MiniDFSCluster.Builder(conf).format(false).numDataNodes(1).storagesPerDatanode(2).storageTypes(...).build(); waitActive()`. Resolve `src` and `dst` by storage ID.
   *Amendment D1-2 (2026-11-25, stage-4 audit; procedure detail):* each run sets `hdfs.minidfs.basedir`
   (`MiniDFSCluster.HDFS_MINIDFS_BASEDIR`, `MiniDFSCluster.java:169, 234-241`) to its own fresh directory under
   `target/test/data/o26/<run>` in the one `conf` object used for both clusters, so cluster 1 formats a fresh base dir and
   cluster 2 reopens exactly that dir. Each run (U0–U4) is its own test method with its own two clusters.
7. Assert the reserve took effect: `reservedSpace(dst) == R`. Record `A0 = dst.getAvailable()` and `U0 = usedSpace(dst)`, and log both.
8. Run the mover:
   - `mover = new DiskBalancer.DiskBalancerMover(dsSpy, conf); mover.setRunnable();`
   - `item = new DiskBalancerWorkItem(B, 0)`. For U4 only, also `item.setTolerancePercent(100)`.
   - `pair = new DiskBalancer.VolumePair(srcId, src.getBaseURI().getPath(), dstId, dst.getBaseURI().getPath())`.
   - `mover.copyBlocks(pair, item)`. The call is synchronous.
9. Record `blocksCopied`, `bytesCopied`, the per-move `getAvailable()` list, and `usedSpace`, `freeSpace` and H for the destination after the move. Log them all.
10. Shut down with `cluster2.shutdown(true)`.

**B2f. Predictions.** Stated before any run. `A0` is the value measured in step 7, and `n = min(37, max(0, ceil((A0 - B)/c)))`.

| Run | blocksCopied | Δ usedSpace(dst) | final headroom H | log |
|---|---|---|---|---|
| U0 | 37 (bytesCopied 38797312) | 37c = 39100675 | GBs | "Copy from ... done" |
| U1 (A0 ≈ 53039178) | 11 | 11c = 11624525 | A0 − 11c ≈ 41414653, in (B − c, B] = (40886265, 41943040] | "does not have enough space" |
| U2 (A0 ≈ 63606928) | 21 | 21c = 22192275 | ≈ 41414653, in (B − c, B] | same |
| U3 (A0 ≈ 40886265) | 0 | 0 | = A0 | same, on the first pass |
| U4 (A0 ≈ 800000, B = 600000) | 1 | c = 1056775 | A0 − c ≈ −256775 (freeSpace reads 0) | "Copy from ... done" on the next pass |

- **Every recorded pre-move `getAvailable()`** is greater than B, and successive values differ by exactly c.
- **U1 vs U2:** the difference in copied blocks equals `(A0_U2 - A0_U1)/c`, which is 10. Equivalently, `ΔR = -(A0_U2 - A0_U1)` maps 1:1 to copied bytes within one block.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| U1 and U2 copy n blocks as predicted; final H in (B − c, B]; U3 copies 0 | Claim confirmed: the reserve-adjusted availability caps the destination writes, with a margin of B − c |
| U1, U2 or U3 copy 37 blocks like U0 | Claim refuted: R does not govern the copy |
| Final H < B − c in U1 or U2 (B ≥ c) | Claim refuted: the destination went deeper than the check allows. Look for another writer or a stale `dfsUsed` |
| Pre-move `getAvailable()` values do not fall by c per move | The trace of `dfsUsed` accounting (A3 step 6) is wrong. Revisit `addFinalizedBlock` |
| `reservedSpace(dst) ≠ R` in step 7 | Not confirmed: the knob did not reach the volume. Fix the configuration and re-run |
| U4 copies 1 block and H < 0 | Bounded overshoot confirmed (A3 step 9a). This does not refute the main claim, but it qualifies it |
| U4 copies 0 blocks | The `isLessThanNeeded` and tolerance trace is wrong. Re-read `:855-861` |
| U0 copies fewer than 37 blocks | The positive control failed (source short of blocks, or errors). Results are not interpretable |
| *D1-5 (2026-11-25):* U1, U2 or U3 match the counts, but the test log of that run lacks the line-1148 message, or shows a line-1110 ("Copy from ... done"), line-1121 ("No source blocks") or line-1102 ("Exceeded the max error count") stop | Not confirmed: the stop is not shown to come from the check |
| *D1-5 (2026-11-25):* any other reading (e.g. a binding run's `blocksCopied` ≠ n but ≠ 37, with H ≥ B − c) | Not confirmed (no matching row) |

*Amendment D1-5 (2026-11-25, stage-4 audit, before any reading; group B "direct disallow evidence"):* the first row
("Claim confirmed") additionally requires, in each of U1, U2 and U3, the line-1148 message ("does not have enough space to
accommodate a block") in that run's log and no line-1110, 1121 or 1102 stop, as B2f's "log" column already predicts. The two
rows above are added so that every outcome has a row. Predictions and the other rows are unchanged.

**B2h. Controls.**
- **U0** (R = 0) shows that the same workload moves 37 blocks when the cap does not bind. This is the positive control for "usage moves".
- **U3** shows the boundary at A0 ≤ B.
- **The R-to-A0 assertion** in step 7 rules out a knob that silently fails to apply.
- **The spy on `moveBlockAcrossVolumes`** proves the stop came from line 1138. With a stop at line 1138, the last recorded value is > B and the loop ended by `break`, with no "No source blocks" or "Exceeded the max error count" log.
- **`fs.du.interval=3600000`** rules out a DU refresh changing `dfsUsed` mid-run.
- **Single test JVM and no clients** rule out concurrent writers.

### B3. Cluster tier

**B3a. Environment and build.**
- **Hosts and daemons:** one Linux host, pseudo-distributed. Run a NameNode and one DataNode, both started with `hdfs --daemon start ...`. Do not use `start-dfs.sh`, which needs SSH. No YARN.
- **Build:** a distribution from the tag, `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`, built in a private copy on local disk. Set `HADOOP_HOME=<copy>/hadoop-dist/target/hadoop-3.4.2`, or the existing built distribution of the stage-4 environment.
- **Run directory:** `RUN=/mydata/<runner>/o26`, on local disk. It must not be NFS.
- **Environment variables:**
  - `HADOOP_CONF_DIR=$RUN/conf` (copy `$HADOOP_HOME/etc/hadoop` there)
  - `HADOOP_LOG_DIR=$RUN/logs`
  - `HADOOP_PID_DIR=$RUN/pids`
  - `HADOOP_HEAPSIZE_MAX=1g`
  - `JAVA_HOME` pointing to JDK 8 or 11
  - *Amendment D1-3 (2026-11-25, stage-4 audit; environment only):* `RUN=/mydata/jingsong-s4/dfs.datanode.du.reserved-copyBlocks-getAvailable-run1/cluster`;
    `HADOOP_HOME` = a copy (`cp -a`) of the node's built distribution `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2`
    in `$RUN/hadoop`; `JAVA_HOME` = JDK 8 (`/usr/lib/jvm/java-8-openjdk-amd64`).

`core-site.xml`:
- `fs.defaultFS=hdfs://localhost:19000`
- `hadoop.tmp.dir=$RUN/tmp`
- `fs.du.interval=3600000`

`hdfs-site.xml`:
- **Ports, offset so they do not clash with other users on a shared node:**
  - `dfs.namenode.http-address=0.0.0.0:19870`
  - `dfs.namenode.secondary.http-address=0.0.0.0:19868`
  - `dfs.datanode.address=0.0.0.0:19866`
  - `dfs.datanode.http.address=0.0.0.0:19864`
  - `dfs.datanode.ipc.address=0.0.0.0:19867`
- **Storage and blocks:**
  - `dfs.namenode.name.dir=$RUN/nn`
  - `dfs.replication=1`
  - `dfs.blocksize=16777216`
- **Disk balancer:** `dfs.disk.balancer.enabled=true`
- **Data directories, which change by phase:**
  - Load phase: `dfs.datanode.data.dir=$RUN/dn/vol-src`.
  - Balance phase: `$RUN/dn/vol-src,$RUN/dn/vol-dst`.
- **The knob, balance phase only:** `dfs.datanode.du.reserved.$RUN/dn/vol-dst=<R>`. Write the literal absolute path, no trailing slash. The per-directory key applies the reserve to the destination only, so the source and plan writes are unaffected.

Both data dirs sit on the same local filesystem. The headroom formula from B2b holds there: `A = total - g - R - dfsUsed_dst`.

**B3b. Knobs.** `R` = `dfs.datanode.du.reserved.<vol-dst path>`, in `hdfs-site.xml`. A change needs a **DataNode restart**; there is no reconfig.
- R is computed per run from `stat -f -c '%S %b %f %a' $RUN/dn/vol-dst` (S = fragment size, b = total blocks, f = free blocks, a = available blocks) and `U_dst`, the destination `usedSpace` from JMX before the restart: `R = S·(b − f + a) − U_dst − A0_target`.
- Values, with B = 1073741824 (1 GiB), b = 16 MiB, meta = 7 + 4·32768 = 131079, and c = 16908295:

| Run | R | A0 target | plan step edits |
|---|---|---|---|
| C0 (positive control) | 0 (key absent) | n/a (≈ usable) | bytesToMove = B, tolerancePercent = 10, bandwidth = 100 |
| C1 | computed | B + 20.5c = 1420361872 | same |
| C2 | computed | B + 40.5c = 1758527772 | same |
| C3 | computed | B − c = 1056833529 | same |
| C4 (overshoot probe) | computed | 13000000 | bytesToMove = 10000000, tolerancePercent = 100 |

**B3c. Workload.**
- 2 GiB, which is 128 blocks of 16 MiB, held only on vol-src: `head -c 2147483648 /dev/urandom > $RUN/in.bin; hdfs dfs -put $RUN/in.bin /data/f`, run with only vol-src configured.
- B = 1 GiB is moved from vol-src to vol-dst by `hdfs diskbalancer -execute`.
- **Close-enough count:** `n_close = 59` blocks, because `58·16 MiB·1.1 = 1020.8 MiB < 1024` and `59·16·1.1 = 1038.4 MiB > 1024`. That leaves at least 69 blocks of spare source supply.
- **Binding counts:** `ceil((A0 − B)/c)` = 21 for C1, 41 for C2, 0 for C3.
- **C4:** a 16 MiB block passes `isLessThanNeeded` because `16777216 ≤ 2·10000000`, and passes the check because `13000000 > 10000000`. After landing, H = 13000000 − 16908295 = −3908295.
- **Duration:** at 100 MB/s step bandwidth, about 0.17 s per block, so under 15 s per run, plus the restarts.

**B3d. Observables and instruments.**
- **DataNode JMX:** `curl -s 'http://localhost:19864/jmx?qry=Hadoop:service=DataNode,name=DataNodeInfo'`.
  - Its `VolumeInfo` JSON string, keyed by `<vol>/current`, gives `usedSpace` (dfsUsed), `freeSpace` (getAvailable, clamped at 0), `reservedSpace` (R), `reservedSpaceForReplicas` and `numBlocks` (`FsDatasetImpl.java:3319-3333`, `DataNode.getVolumeInfo` `:3774`).
  - Sample it every 1 s during execute (`while :; do date +%s.%N; curl ...; sleep 1; done > $RUN/jmx-<run>.log`). Take the minimum destination `freeSpace` and the final value.
- **Disk:** `du -sb $RUN/dn/vol-dst/current` before and after, for the actual bytes. Also `stat -f -c '%S %b %f %a' $RUN/dn/vol-dst` before and after, giving total, g and usable.
- **Headroom including any negative part:** `H = S·b − S·(f − a) − R − usedSpace_dst` (`= total − g − R − dfsUsed`).
- **Physical intrusion into the reserve:** `max(0, (S·b − S·(f−a) − R) − du_dst)`. This uses `du` and counts directories, so it is approximate by a few KiB.
  *Amendment D2-1 (2026-11-25, runbook defect found in cluster attempt 1; sign error, independent of the readings):* the
  formula is reversed. As written it is the headroom left between the HDFS allowance and `du`, positive whenever the reserve
  is **not** entered, and it cannot give B3f's own C4 value ("`du` intrusion about 3.9 MB" with H ≈ −3.9 MB). The intended
  observable is **`max(0, du_dst − (S·b − S·(f−a) − R))`**. B3f and B3g are unchanged; the cluster tier restarts from step 1.
- **Balancer:** `hdfs diskbalancer -query localhost:19867 -v` gives the result (`PLAN_DONE`), `bytesToCopy`, `bytesCopied`, `blocksCopied` and `errorCount`.
- **DataNode log:** `$RUN/logs/hadoop-*-datanode-*.log`, checked for "does not have enough space to accommodate a block", "Copy from ... done" and "No source blocks".
- **Not observable directly:** the value at the exact moment of each check. The 1 s JMX sampling misses intermediate values; use the unit tier for per-pass values.

**B3e. Procedure.**
1. **Format and start (once).**
   - `hdfs namenode -format -nonInteractive`
   - `hdfs --daemon start namenode`
   - Set `dfs.datanode.data.dir=$RUN/dn/vol-src,$RUN/dn/vol-dst` with no reserve key, then `hdfs --daemon start datanode`. This creates both volumes and their storage IDs.
   - `hdfs dfsadmin -report` shows 1 live node. Note the DataNode hostname H_DN.
2. **Load the data (per run).**
   - Make sure `/data/f` is absent. Otherwise `hdfs dfs -rm -skipTrash /data/f` and wait until JMX `numBlocks` is 0 on both volumes.
   - `hdfs --daemon stop datanode`. Set `dfs.datanode.data.dir=$RUN/dn/vol-src`. `hdfs --daemon start datanode`.
   - `hdfs dfs -mkdir -p /data && hdfs dfs -put $RUN/in.bin /data/f`.
   - Check `hdfs fsck /data/f -files -blocks` shows 128 blocks.
3. **Set up the balance phase.**
   - Read `U_dst` from the last JMX for vol-dst before the stop (the value from the previous balance phase, after deletion), or use 0 on the first run.
   - `hdfs --daemon stop datanode`.
   - Set both data dirs. Set the reserve key to R from B3b (remove the key for C0).
   - `hdfs --daemon start datanode`. Wait until `hdfs dfsadmin -report` shows it live.
4. **Verify the knob.** JMX `reservedSpace` for `vol-dst/current` must equal R, and 0 for vol-src. If not, stop: the path in the key is wrong.
5. **Plan (template once, in C0).**
   - `hdfs diskbalancer -plan H_DN -thresholdPercentage 0.01 -out /dbplan`, then `hdfs dfs -get /dbplan/H_DN.plan.json $RUN/plan-template.json`.
   - For each run, edit with python3: set the destination step's `bytesToMove`, `tolerancePercent` and `bandwidth` as in B3b, keep only the step whose `destinationVolume.uuid` is the vol-dst storage ID, and set `timeStamp` to `int(time.time()*1000)`.
   - Upload: `hdfs dfs -put -f $RUN/plan-<run>.json /dbplan/plan-<run>.json`.
   - *Amendment D1-4 (2026-11-25, stage-4 audit; a control, no prediction changed):* **no plan file stays in HDFS.** A
     small HDFS file whose block sits on vol-src is a valid source block (`getBlockToCopy` takes the first finalized block
     that fits, `DiskBalancer.java:952-981`) and, having a lower block ID than the next run's `/data/f`, would be iterated
     and moved first, changing `blocksCopied`. So: in C0, after `hdfs dfs -get` of the template, `hdfs dfs -rm -r -skipTrash /dbplan`
     and wait until JMX `numBlocks` is 128 on vol-src and 0 on vol-dst before step 6. The edited plan of each run is
     **not uploaded**; it is executed from local disk with `hdfs diskbalancer -D fs.defaultFS=file:/// -execute $RUN/plan-<run>.json`
     (`ExecuteCommand` reads the file through the default filesystem, `Command.java:447-453`, and sends the plan text to the
     DataNode over RPC, `ExecuteCommand.java:96-105`). Step 6 reads A0 after the plan is written locally. Step 2's load check
     adds: JMX `numBlocks` = 128 on vol-src and 0 on vol-dst at A0 time, i.e. no block other than `/data/f`'s exists.
6. **Read A0.** Take JMX `freeSpace` for vol-dst after the plan upload, and record `usedSpace`, `du -sb` and `stat -f`.
7. **Execute.**
   - Start the JMX sampler.
   - `hdfs diskbalancer -execute /dbplan/plan-<run>.json`.
   - Poll `hdfs diskbalancer -query localhost:19867 -v` every 2 s until the result is `PLAN_DONE`.
   - Stop the sampler.
8. **Record.** Collect `blocksCopied`, `bytesCopied`, the final JMX `usedSpace`/`freeSpace`, `du -sb`, `stat -f`, H, and `grep -n "enough space\|Copy from\|No source blocks" <datanode log>`.
9. Repeat steps 2-8 for C1 through C4. Run C0 first, because it produces the template.
10. **Cleanup.**
    - `hdfs --daemon stop datanode; hdfs --daemon stop namenode`.
    - `jps` must show no NameNode or DataNode from `$RUN`.
    - `rm -rf $RUN`.

**B3f. Predictions.** Stated before any run. A0 is measured in step 6, and `n = min(59, max(0, ceil((A0 − B)/c)))`.

| Run | blocksCopied | Δ usedSpace(dst) | final H | log |
|---|---|---|---|---|
| C0 | 59 (bytesCopied 989855744) | 59c = 997589405 | ≈ usable, minus about 1 GiB | "Copy from ... done" |
| C1 (A0 ≈ 1420361872) | 21 | 21c = 355074195 | ≈ 1065287677, in (B − c, B] = (1056833529, 1073741824] | "does not have enough space" |
| C2 (A0 ≈ 1758527772) | 41 | 41c = 693240095 | ≈ 1065287677, in (B − c, B] | same |
| C3 (A0 ≈ 1056833529) | 0 | 0 | = A0 | same (immediately) |
| C4 (A0 ≈ 13000000) | 1 | c = 16908295 | ≈ −3908295 (JMX freeSpace 0; `du` intrusion about 3.9 MB) | "Copy from ... done" |

- `Δ du -sb` on vol-dst should match `Δ usedSpace` within a few hundred KiB (directory blocks).
- C2 − C1 should be 20 blocks for a 20c difference in A0, i.e. 1:1 in R.
- The minimum sampled `freeSpace` during C1 and C2 should never fall below `B − c`.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| C1, C2 and C3 match n; final H in (B − c, B]; C2 − C1 = 20 blocks | Claim confirmed: the reserve-adjusted availability caps the disk balancer's writes to the destination |
| C1 or C2 copies 59 blocks like C0 | Claim refuted: R does not govern destination usage |
| Final H < B − c in C1 or C2, with no other writer | Claim refuted: the destination was filled past the check's margin |
| `du` intrusion > 0 in C1 or C2 | Claim refuted at the physical level: the reserve was entered |
| C4: one block lands with H ≈ −3.9 MB | Bounded one-block overshoot confirmed. It qualifies the claim but does not refute it |
| JMX `reservedSpace(dst) ≠ R` | Not confirmed: the knob was not applied. Fix the key path and re-run |
| C0 copies fewer than 59 blocks, or errors | The positive control failed. Results are not interpretable |
| Execute is rejected (hash, time or node UUID) | Procedure fault in step 5 (timestamp or nodeUUID). Not a reading |
| *D1-6 (2026-11-25):* C1, C2 or C3 match the counts, but the DataNode log for that run lacks the line-1148 message, or shows a line-1110, 1121 or 1102 stop | Not confirmed: the stop is not shown to come from the check |
| *D1-6 (2026-11-25):* any other reading (e.g. a binding run's `blocksCopied` ≠ n but ≠ 59, with H ≥ B − c and no `du` intrusion) | Not confirmed (no matching row) |

*Amendment D1-6 (2026-11-25, stage-4 audit, before any reading; group B "direct disallow evidence"):* the first row
("Claim confirmed") additionally requires, in each of C1, C2 and C3, the line-1148 message in the DataNode log for that run
and no line-1110, 1121 or 1102 stop, as B3f's "log" column already predicts. The two rows above are added so that every
outcome has a row. Predictions and the other rows are unchanged.

**B3h. Controls.**
- **C0**, with the same data, plan and bandwidth and R = 0, shows usage moves to about 1 GiB when the cap does not bind.
- **C3** shows the A0 ≤ B edge.
- **The per-directory key** keeps the source and plan files out of the reserve logic.
- **Reading A0 after the plan upload** excludes the plan file's own bytes.
- **No clients run during execute**, so there are no concurrent writers.
- **`fs.du.interval=3600000`** prevents a DU refresh mid-run.
- **The log line at `:1148`** distinguishes a stop at the check from a stop by close-enough (`:1110`), by "No source blocks" (`:1121`) or by the error count (`:1102`).

**B4. Risks and cleanup.**
- **Disk:**
  - The unit tier uses less than 200 MB under the private source copy's `target/`.
  - The cluster tier peaks at about 2 GiB (`in.bin`) + 2 GiB (vol-src) + 1 GiB (vol-dst), plus the NameNode and logs. That is under 6 GB on `$RUN`, which must be local disk with at least 10 GB usable. Delete `in.bin` after the final run.
  - R is a large number, but it only shrinks HDFS's view; it allocates nothing.
- **Shared storage:** never point any directory at NFS or `/proj`.
- **Ports:** 19000, 19864, 19866, 19867, 19868 and 19870 are offset from the defaults. Check them free first with `ss -ltn`.
- **Processes:** the cluster tier stops both daemons, then `jps` must show none. Kill leftovers by PID from `$RUN/pids`. The unit tier's MiniDFSCluster shuts down in `finally`.
- **Cleanup:** `rm -rf $RUN` and the private source copy's `target/test/data`.

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DiskBalancer.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsVolumeImpl.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetImpl.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/BlockPoolSlice.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/ReservedSpaceCalculator.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataNode.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/diskbalancer/planner/GreedyPlanner.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/diskbalancer/planner/MoveStep.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/diskbalancer/planner/NodePlan.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/diskbalancer/datamodel/DiskBalancerVolume.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/diskbalancer/datamodel/DiskBalancerVolumeSet.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/diskbalancer/connectors/DBNameNodeConnector.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/diskbalancer/command/ExecuteCommand.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/diskbalancer/command/PlanCommand.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/diskbalancer/command/Command.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/tools/DiskBalancerCLI.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/server/datanode/DiskBalancerWorkItem.java
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/DF.java
- hadoop-common-project/hadoop-common/src/main/resources/core-default.xml
- hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/HDFSDiskbalancer.md
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/diskbalancer/TestDiskBalancer.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/diskbalancer/DiskBalancerTestUtil.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/MiniDFSCluster.java
- https://issues.apache.org/jira/browse/HDFS-13892
- https://issues.apache.org/jira/browse/HDFS-15440
- https://issues.apache.org/jira/browse/HDFS-13728

## D. Stage-4 feedback

**Stage-4 audit, 2026-11-25 (fresh stage-4 agent working as Jingsong, node `pc91`), before any reading.** Bottom line:
**Ready after amendments.** Filed sha256 `a72ff16c…0706c1` (matches `_INDEX.md` §4). Amendments, each next to the text it
changes:

- **D1-1** (B2a, environment): per-case copy with `copy-source.sh`, offline `mvn -o … test`, no install into `~/.m2`.
- **D1-2** (B2e step 6, procedure detail): an explicit `hdfs.minidfs.basedir` per run, shared by cluster 1 and cluster 2.
- **D1-3** (B3a, environment): run folder and distribution copy on `pc91`'s `/mydata`, JDK 8.
- **D1-4** (B3e step 5, control): no plan file in HDFS during a run (its block on vol-src would be moved first); plans
  executed from local disk with `-D fs.defaultFS=file:///`; `numBlocks` 128/0 checked at A0 time.
- **D1-5 / D1-6** (B2g / B3g): Confirmed also requires the line-1148 message in each binding run (U1–U3, C1–C3) and no
  other stop; rows added for "counts match, stop not from the check" and "any other reading" (both Not confirmed).

- **D2-1** (B3d, runbook defect found in cluster attempt 1, 2026-11-25 10:37 MST): the "physical intrusion" formula had its
  sign reversed (it measured headroom, and as written would have matched B3g's "`du` intrusion > 0" Refuted row in every
  non-intruding run). Corrected to `max(0, du_dst − (S·b − S·(f−a) − R))`; the cluster tier restarted from step 1
  (attempt 2). The audit (group B/C) should have caught it: B3f's C4 value already implied the corrected sign.

B1, B2f, B3f and every predicted number are unchanged. Recommendations left for stage 3 (not applied): the default
(R = 0) arm stands in for the knob's default in both tiers (U0/C0); the "filling the filesystem" variant (R = 0 with a
small loop filesystem) is not needed because `getAvailable()` is algebraically independent of other files on the
filesystem while `R ≥ actualNonDfsUsed` (A3 step 3).

**Stage-4 run 1, 2026-11-25 (pc91, 10:29–10:42 MST): unit Confirmed, cluster Confirmed — effect `caps`; outcome class
true positive.** Results: `hadoop/stage4-runtime-verification/jingsong/results/dfs.datanode.du.reserved-copyBlocks-getAvailable--autonomous.md`.
- Unit (B2g row 1): U1/U2/U3 copied 11/21/0 blocks = n from the measured A0 (53,039,178 / 63,606,928 / 40,886,265, each
  exactly the target); final headroom 41,414,653 in (B − c, B] for U1 and U2; the pre-move operand fell by exactly c = 1,056,775
  per move and was > B at every move; one line-1148 stop in each of U1–U3, no other stop. U0 (R = 0) copied 37 (close-enough).
  U4: 1 block landed with H = −256,775 (bounded overshoot row).
- Cluster (B3g row 1), attempt 2 after D2-1: C1/C2/C3 copied 21/41/0 blocks = n (A0 1,420,361,872 / 1,758,527,772 /
  1,056,833,529); final H 1,065,287,677 in (B − c, B] for C1 and C2; C2 − C1 = 20 blocks for 20c of A0; Δ`du` − Δ`usedSpace`
  = 8–12 KiB (directories); `du` intrusion 0; one line-1148 stop each. C0 59 blocks (positive control). C4: 1 block,
  H = −3,908,295, `du` intrusion 3,933,428 B (bounded overshoot row). Attempt 1 (formula error only) had the same counts and
  bytes to the byte.
- For stage 3: (1) predict the observable formulas as carefully as the numbers (D2-1); (2) side finding: the disk balancer's
  **source** volume keeps each moved block's meta length in `dfsUsed` (`FsDatasetImpl.cleanupReplica`, `:1187-1196`, deletes
  the meta file before `getMetadataLength()` reads its length) — 59, 80 and 121 × 131,079 B observed, exact.
