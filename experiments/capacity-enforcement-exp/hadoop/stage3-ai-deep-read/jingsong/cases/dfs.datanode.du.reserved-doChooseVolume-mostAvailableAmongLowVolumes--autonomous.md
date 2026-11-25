# dfs.datanode.du.reserved — verification solution  <!-- file: cases/dfs.datanode.du.reserved-doChooseVolume-mostAvailableAmongLowVolumes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`AvailableSpaceVolumeChoosingPolicy.java:166`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/AvailableSpaceVolumeChoosingPolicy.java#L166) — `if (mostAvailableAmongLowVolumes < replicaSize \|\| random.nextFloat() < scaledPreferencePercent)` in `doChooseVolume` (row unit; not a helper) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive`. The limit-side operand at line 166 is a volume's `FsVolumeImpl.getAvailable()`, which is capacity minus `dfs.datanode.du.reserved` minus finalized HDFS bytes minus outstanding replica reservations. A new replica is placed on a volume only if that value is ≥ the replica's declared size (line 166) and > it (the round-robin re-check). So for sequential writes, each volume's HDFS bytes stay within capacity − reserved, up to about one meta file. Known leaks: concurrent writers (acked bytes of in-flight blocks are counted nowhere), and paths that pass a smaller size estimate than the block that is later written. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**

- **Name:** `dfs.datanode.du.reserved`. It also has per-volume and per-storage-type forms, which the same lookup resolves: `dfs.datanode.du.reserved.<data-dir>.<storage-type>`, then `dfs.datanode.du.reserved.<data-dir>`, then `dfs.datanode.du.reserved.<storage-type>`, then `dfs.datanode.du.reserved` (`ReservedSpaceCalculator.java:112-118`). Here `<data-dir>` is the volume's directory exactly as `currentDir.getParent()` prints it (`FsVolumeImpl.java:173-175`), and `<storage-type>` is lower case (`disk`, `ssd`, `archive`, `ram_disk`, `nvdimm`).
- **Kind:** configuration key.
- **First declared:** [`DFSConfigKeys.java:964`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java#L964) `DFS_DATANODE_DU_RESERVED_KEY = "dfs.datanode.du.reserved"`. The default `DFS_DATANODE_DU_RESERVED_DEFAULT = 0` is at `DFSConfigKeys.java:965`. The `hdfs-default.xml:396-417` entry also says `0`, with the description "Reserved space in bytes per volume. Always leave this much space free for non dfs use." The constant and the XML agree, so there is no conflict.
- **Unit:** bytes.
  - The bare key is read with `conf.getLongBytes`, so suffixes such as `10g` work (`ReservedSpaceCalculator.java:117`).
  - The directory and storage-type forms are read with plain `conf.getLong` (`ReservedSpaceCalculator.java:113-116`). They must be plain decimal byte counts. A suffix there throws `NumberFormatException`, which `Builder.build()` wraps as `IllegalStateException("Error instantiating ReservedSpaceCalculator")` (`ReservedSpaceCalculator.java:83-86`).
- **Derived from several sources.** Which calculator reads the key is chosen by `dfs.datanode.du.reserved.calculator` (`DFSConfigKeys.java:959-963`):
  - `ReservedSpaceCalculatorAbsolute` (the default) uses this key (`ReservedSpaceCalculator.java:131-147`).
  - `ReservedSpaceCalculatorPercentage` uses `dfs.datanode.du.reserved.pct` (`:152-169`).
  - `Conservative` takes the max of the two and `Aggressive` the min (`:175-239`).

  The other inputs to the line-166 operand are runtime-queried: `DF.getCapacity/getUsed/getAvailable`, which are `File.getTotalSpace`, total − `getFreeSpace`, and `getUsableSpace` (`hadoop-common .../fs/DF.java:85-97`). The volume's cached `dfsUsed` and `reservedForReplicas` also feed in. Of these, a user tunes only `dfs.datanode.du.reserved`.
- **How it is set:** in `hdfs-site.xml` on the DataNode.
  - It is read once, when each `FsVolumeImpl` is built (`FsVolumeImpl.java:173-175`, `ReservedSpaceCalculator.java:139-140`).
  - It is not in the DataNode's reconfigurable set (no reference in `DataNode.java`), so a change needs a DataNode restart. A hot-swap re-add of the volume through `dfs.datanode.data.dir` reconfiguration would also rebuild it.
- **Reader:** the DataNode process.
- **Line-166 knobs that are not the constraint.** Two other keys act at line 166 itself, but neither one sets the limit:
  - `dfs.datanode.available-space-volume-choosing-policy.balanced-space-threshold` (`DFSConfigKeys.java:1184-1185`, default 10 GiB) decides which volumes are "low".
  - `...balanced-space-preference-fraction` (`:1186-1187`, default 0.75) sets the random preference.
  - The policy itself is chosen by `dfs.datanode.fsdataset.volume.choosing.policy` (`DFSConfigKeys.java:1182`). The default is `RoundRobinVolumeChoosingPolicy` (`FsDatasetImpl.java:343-347`), so line 166 runs only when that key names `AvailableSpaceVolumeChoosingPolicy`.

**A2. What it caps.**

The resource is disk space on each DataNode volume (each `dfs.datanode.data.dir` entry). The reserve sets how many bytes of the volume's file system HDFS must leave free for non-HDFS use. Equivalently, it sets the most HDFS block and meta bytes a volume will be given.

The quantity compared at line 166 is `mostAvailableAmongLowVolumes`, the largest `getAvailable()` among the "low" volumes (`AvailableSpaceVolumeChoosingPolicy.java:152-153, 230-236`). It is compared against `replicaSize`, the declared size of the replica about to be created. `getAvailable()` is (`FsVolumeImpl.java:474-482`):

```
remaining = getCapacity() - getDfsUsed() - getReservedForReplicas()
            where getCapacity() = max(DF.capacity - reserved, 0)          (FsVolumeImpl.java:434-455)
available = DF.usable - getRemainingReserved() - getReservedForReplicas()
            where getRemainingReserved() = max(reserved - actualNonDfsUsed, 0) (FsVolumeImpl.java:514-521)
                  actualNonDfsUsed = max(DF.used - dfsUsed, 0)           (FsVolumeImpl.java:484-504)
getAvailable = max(min(remaining, available), 0)
```

`reserved` is `ReservedSpaceCalculator.getReserved()` via `FsVolumeImpl.getReserved()` (`FsVolumeImpl.java:556-558`). The same value goes into the heartbeat storage report as "remaining" (`FsDatasetImpl.java:167-174`) and into the DataNode JMX `VolumeInfo.freeSpace` (`FsDatasetImpl.java:3297-3313, 3324-3328`).

**A3. Mechanism.**

1. **Where `replicaSize` comes from.**
   - The NameNode creates a new block with `numBytes = 0` (`FSNamesystem.java:3251`).
   - The client overwrites the copy it sends with the file's block size: `blockCopy.setNumBytes(stat.getBlockSize())` (`hadoop-hdfs-client .../DataStreamer.java:1917-1918`).
   - On the DataNode, `DataXceiver.writeBlock` substitutes the DataNode's own `dfs.blocksize` only if the size arrived as 0 (`DataXceiver.java:756-758`, `DataXceiverServer.java:196-197`).
   - `BlockReceiver` calls `createRbw` (`BlockReceiver.java:220`) or `createTemporary` (`:216, :248`).
   - These call `volumes.getNextVolume(storageType, storageId, b.getNumBytes())` (`FsDatasetImpl.java:1639`, `:1912`).
   - Disk-balancer and mover moves use the actual block length (`FsDatasetImpl.java:1103-1107`).
   - Balancer `replaceBlock` from another node uses the DataNode's `dfs.blocksize` estimate (`DataXceiver.java:1207`).
2. **Which volumes are candidates.** `FsVolumeList.getNextVolume` keeps the volumes of the requested storage type (`FsVolumeList.java:177-186`) and drops slow disks (`:105-113`). `storageId` is passed on but ignored by this policy. It then calls `blockChooser.chooseVolume` (`:116-118`), which takes the per-storage-type lock (`AvailableSpaceVolumeChoosingPolicy.java:127-129`) and enters `doChooseVolume`.
3. **Snapshot.** `getAvailable()` is read once per volume into `AvailableSpaceVolumePair` (`:194-199, 277-280`).
4. **Balanced case.** If max − min available ≤ `balanced-space-threshold` (`:205-213`), selection falls back to plain round robin over all volumes (`:137-147`). Line 166 is not reached.
5. **Imbalanced case.**
   - "Low" volumes are those with available ≤ least + threshold; "high" volumes are the rest (`:241-264`).
   - `mostAvailableAmongLowVolumes` is the max over the low volumes (`:152-153`).
   - `scaledPreferencePercent` = `nHigh·f / (nHigh·f + nLow·(1−f))` (`:160-165`).
6. **The check:** [`AvailableSpaceVolumeChoosingPolicy.java:166`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/AvailableSpaceVolumeChoosingPolicy.java#L166-L167).
   - **True:** the best low volume cannot hold `replicaSize`, or the random draw prefers high volumes. Selection is round robin over the high volumes (`:168-169`).
   - **False:** round robin over the low volumes (`:176-177`).
   - The guard matters with `f` = 0.0: then `scaledPreferencePercent = 0` and only the space test can send a block to a high volume.
7. **The actual cap.** Each inner `RoundRobinVolumeChoosingPolicy` re-reads `volume.getAvailable()` live. It returns the first volume with `availableVolumeSize > blockSize + additionalAvailableSpace` (`RoundRobinVolumeChoosingPolicy.java:110-113`). Otherwise, after one full cycle, it throws `DiskOutOfSpaceException("Out of space: The volume with the most available space (=X B) is less than the block size (=Y B).")` (`:122-126`).
   - The three inner instances are built with `new` and never get `setConf` (`AvailableSpaceVolumeChoosingPolicy.java:108-113`). So `additionalAvailableSpace` stays at Java's default 0, not the 1 GiB of `dfs.datanode.round-robin-volume-choosing-policy.additional-available-space` (`DFSConfigKeys.java:1188-1193`).
   - The real cap is therefore "available > replicaSize". Line 166 sends a block away from a low group that would fail that test toward one that can pass it.
8. **Reservation and accounting.**
   - After the choice, and outside the policy lock, `createRbwFile` and `createTmpFile` add `b.getNumBytes()` to `reservedForReplicas` (`FsVolumeImpl.java:1015-1021, 617-621, 629-634`).
   - As packets are acked, the reservation is released by the acked byte count (`LocalReplicaInPipeline.java:145-154`, from `BlockReceiver.java:1673`).
   - `dfsUsed` grows by block + meta length only at finalize (`BlockPoolSlice.java:445-452`). Finalize happens before the last ack goes upstream (`BlockReceiver.java:1514`, then `:1520`).
   - Otherwise `dfsUsed` is refreshed by `du` every `fs.du.interval` (600000 ms, `core-default.xml:1361-1362`).
9. **Outcome when the limit is reached on every volume.** `DiskOutOfSpaceException` reaches the writer. Separately, the NameNode stops choosing this DataNode for the storage type: `chooseStorage4Block` keeps only storages whose reported remaining (= `getAvailable`) is ≥ `blockSize·minBlocksForWrite`, net of scheduled blocks (`DatanodeDescriptor.java:816-840`, `BlockPlacementPolicyDefault.java:968-972`). The client then fails with "could only be written to 0 of the 1 minReplication nodes".

**Paths that bypass or overshoot:**

- **(a) Meta file.** It is not reserved. A `B`-byte block brings a meta file of `B/512·4 + 7` bytes (CRC32C, 512-byte chunks), which for `B` = 100 MiB is 819,207 bytes. Final usage can exceed the budget by up to one meta file, minus the slack (available − B) at admission.
- **(b) In-flight acked bytes are invisible.** Once a packet is acked, its bytes leave `reservedForReplicas` but enter `dfsUsed` only at finalize. When the reserve is in force (`actualNonDfsUsed < reserved`), these bytes also cancel out of the DF term: usable falls by x and non-DFS rises by x. So `getAvailable()` overstates the room by the acked bytes of every unfinalized replica.
  - Concurrent writers can therefore get more blocks admitted than fit, and overshoot the reserve by up to about the acked bytes of the other in-flight replicas.
  - The choice is also made under the policy lock, while the reservation is taken later under the volume lock (`FsDatasetImpl.java:1639` then `:1655`), so a second small race window exists.
- **(c) Under-declared size.** Balancer `replaceBlock` declares the DataNode's `dfs.blocksize` (`DataXceiver.java:1207`) even if the block being copied is larger. `BlockReceiver` makes no space check while bytes arrive (no `getAvailable` call in `BlockReceiver.java`).
- **(d) Append.** It does not go through the policy. `FsVolumeImpl.append` makes its own `getAvailable() < bytesReserved` check (`FsVolumeImpl.java:1263-1268`).
- **(e) Boundary mismatch.** Line 166 tests `<` but the round robin tests `>`. If the best low volume has exactly `replicaSize` available and the draw picks the low group, round robin over the low group throws `DiskOutOfSpaceException`, even when a high volume has plenty of room.
- **(f) File-system root-reserved blocks.** For example the ext4 reserved-blocks-percentage. They make `getFreeSpace` larger than `getUsableSpace`, are counted in `actualNonDfsUsed` as not used, and so shift the effective budget (worked out in B3a). `hdfs-default.xml:414-416` warns about this.
- **(g) Default value.** With the default `dfs.datanode.du.reserved = 0`, HDFS may fill a volume to the file system's usable space.

**A4. Other consumers.** These use the same volume disk outside this constraint's control:

- non-HDFS files on the same file system;
- DataNode logs if `HADOOP_LOG_DIR` is on that file system;
- other volumes that share one mount. Each volume subtracts only its own `dfsUsed`, and with same-disk tiering they share `reserved` through `getActualNonDfsUsed` (`FsVolumeImpl.java:484-500`);
- the `tmp`, `rbw`, `lazypersist` and scanner/`dfsUsed` cache files;
- block-pool trash used during rolling upgrade;
- the replica cache and memory-mapped RAM_DISK replicas, which are a different storage type.

The NameNode's `dfs.namenode.resource.du.reserved` guards NameNode metadata directories, not DataNode volumes.

**A5. Evidence beyond the source.** All from the source tree; none of the JIRAs were opened in this session:

- `hdfs-default.xml:396-417` (meaning and precedence of the per-dir and per-type forms, plus the tune2fs warning), `:2709-2747` (the policy keys) and `:4839-4848` (choosing the policy).
- In-tree tests: `TestAvailableSpaceVolumeChoosingPolicy#testNotEnoughSpaceOnSelectedVolume` (`hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/TestAvailableSpaceVolumeChoosingPolicy.java:247-271`) exercises exactly the line-166 space guard with mock volumes and fraction 0.0. `TestFsVolumeList#testDfsReservedForDifferentStorageTypes` (`TestFsVolumeList.java:159-226`) checks the reserve lookup. `TestSpaceReservation` (`.../impl/TestSpaceReservation.java`) covers RBW reservation.
- JIRA context, unverified here: HDFS-1804 (introduced `AvailableSpaceVolumeChoosingPolicy`) and HDFS-6898 (DataNode reserves space for a full block when an RBW is created).

## B. Verification solution

**B1. Claim under test.** With `AvailableSpaceVolumeChoosingPolicy`, the DataNode places a new replica of declared size `B` only on a volume whose `getAvailable()` (DF capacity − `dfs.datanode.du.reserved` − finalized HDFS bytes − outstanding reservations) is at least `B` at line 166 and greater than `B` at the round-robin re-check. When the low-space group cannot fit `B`, the block goes to a high-space volume. The consequence is that for sequential writes, each volume's HDFS block + meta bytes never exceed (capacity − reserved) by more than one meta file, and the per-volume block count follows the reserve as `n_i = number of k ≥ 0 with A_i − k·S > B`, where `A_i` is the starting available space and `S` is the per-block footprint. The claim is false if a volume takes a block when its available space is ≤ `B`, if a low-group volume that cannot fit `B` is chosen while a high volume can, or if per-volume usage does not move with the reserve.

### B2. Unit tier

**B2a. Environment and build.**

- Linux, JDK 8, Maven ≥ 3.3.
- Copy the tree to local disk first, never into the shared tree: `rsync -a ~/hadoop-3.4.2/ $WORK/hadoop-src/` (`$WORK` is a local-disk scratch directory).
- Build once: `cd $WORK/hadoop-src && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
- The test goes in `$WORK/hadoop-src/hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/TestDuReservedAvailableSpacePlacement.java`. It must be in package `...fsdataset.impl` because `FsVolumeList`, `FsVolumeImplBuilder.setUsage(DF)` and `FsVolumeList.addVolume` are package-private.
- The surefire default JVM options are enough. No daemon or `MiniDFSCluster` is needed: real `FsVolumeImpl`, `FsVolumeList`, `ReservedSpaceCalculator` and `AvailableSpaceVolumeChoosingPolicy` objects run in one JVM, and only `DF` is mocked so that capacity is exact.

**B2b. Knobs.**

| Name | Fixed values |
|---|---|
| Replica size `B` | 104,857,600 (100 MiB) |
| Volume `d0` (mocked DF: capacity = usable = `C0`, used = 0) | `C0` = 1,073,741,824 (1 GiB) |
| Volume `d1` (mocked DF: capacity = usable = `C1`, used = 0) | `C1` = 3,221,225,472 (3 GiB) |
| `...balanced-space-threshold` | `T` = 1,048,576 (1 MiB), so the volumes are always imbalanced |
| `...balanced-space-preference-fraction` | `f` = 0.0, so only the line-166 space test can route to a high volume; deterministic |

With DF used = 0, `getAvailable() = C_i − R − reservedForReplicas` (both terms in A2 are equal). The varied knob `R` is the global `dfs.datanode.du.reserved`, set with `conf.setLong` before the volumes are built:

| Run | `R` (bytes) | Why |
|---|---|---|
| U-R0 | 0 | baseline |
| U-R512 | 536,870,912 | reserve bites on both volumes |
| U-R960 | 1,006,632,960 | `d0` starts below `B`: 64 MiB |
| U-EQ | 968,884,224 = `C0` − `B` | `d0` available is exactly `B`: line-166 boundary |
| U-EQ1 | 968,884,225 | `d0` available is `B` − 1 |
| U-R0-f75, U-R512-f75 | as U-R0 / U-R512 | `f` = 0.75 (default), randomised order |
| U-R512-bal | 536,870,912 | `T` = 10 GiB: balanced branch, line 166 never reached |

**B2c. Workload.** The loop mimics `createRbw`:

1. `ref = volumeList.getNextVolume(StorageType.DISK, null, B)`
2. `((FsVolumeImpl) ref.getVolume()).reserveSpaceForReplica(B)`
3. `ref.close()`

Repeat for up to 100 steps, stopping at the first `DiskOutOfSpaceException`. Each step adds `B` to the chosen volume's reservation, which is exactly what `createRbwFile` does (`FsVolumeImpl.java:1017`). With `A_i = C_i − R`, volume i accepts while `A_i − k·B > B`, i.e. `n_i = floor((A_i − 1)/B)` blocks. For example, `A0` = 1024 MiB allows 10 blocks and leaves 24 MiB. The total demand (100 steps × 100 MiB) exceeds every budget, so the limit is always reached.

**B2d. Observables and instruments.**

- Before each step, record `v.getAvailable()` and `v.getReservedForReplicas()` for `d0` and `d1`.
- Record the line-166 operand `mostAvailableAmongLowVolumes`. It is recomputed in the test from those snapshots with the class's own rule (low = available ≤ min + `T`, then the max over the low group), because the field is a local variable.
- Record which volume was returned, or the exception text.
- The policy's own DEBUG lines are captured too: "Volumes are imbalanced. Selecting <vol> from high|low available space volumes for write of block size …" (`AvailableSpaceVolumeChoosingPolicy.java:171-181`). Enable them with `GenericTestUtils.setLogLevel(LoggerFactory.getLogger(AvailableSpaceVolumeChoosingPolicy.class), org.slf4j.event.Level.DEBUG)`. With `f` = 0.0, a "from high" line means line 166 was true because of space.
- Output: one CSV line per step on stdout (`target/surefire-reports/...TestDuReservedAvailableSpacePlacement-output.txt`).
- Not observable: real disk bytes. That is the cluster tier's job.

Test source to write:

```java
package org.apache.hadoop.hdfs.server.datanode.fsdataset.impl;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import java.io.File;
import java.util.*;
import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.DF;
import org.apache.hadoop.fs.FileSystemTestHelper;
import org.apache.hadoop.fs.StorageType;
import org.apache.hadoop.hdfs.DFSConfigKeys;
import org.apache.hadoop.hdfs.server.common.Storage.StorageDirectory;
import org.apache.hadoop.hdfs.server.datanode.BlockScanner;
import org.apache.hadoop.hdfs.server.datanode.StorageLocation;
import org.apache.hadoop.hdfs.server.datanode.fsdataset.*;
import org.apache.hadoop.test.GenericTestUtils;
import org.apache.hadoop.util.DiskChecker.DiskOutOfSpaceException;
import org.apache.hadoop.util.ReflectionUtils;
import org.junit.Test;
import org.slf4j.LoggerFactory;

public class TestDuReservedAvailableSpacePlacement {
  static final long MiB = 1L << 20, B = 100 * MiB, C0 = 1024 * MiB, C1 = 3072 * MiB;

  private FsVolumeImpl vol(Configuration conf, String base, String name, long cap) throws Exception {
    File d = new File(base, name); d.mkdirs();
    DF df = mock(DF.class);
    when(df.getCapacity()).thenReturn(cap);
    when(df.getUsed()).thenReturn(0L);
    when(df.getAvailable()).thenReturn(cap);
    return new FsVolumeImplBuilder().setConf(conf).setDataset(mock(FsDatasetImpl.class))
        .setStorageID("sid-" + name)
        .setStorageDirectory(new StorageDirectory(StorageLocation.parse(d.getPath())))
        .setUsage(df).build();
  }

  private void run(String tag, long reserved, float f, long threshold) throws Exception {
    GenericTestUtils.setLogLevel(LoggerFactory.getLogger(AvailableSpaceVolumeChoosingPolicy.class),
        org.slf4j.event.Level.DEBUG);
    Configuration conf = new Configuration();
    conf.setLong(DFSConfigKeys.DFS_DATANODE_DU_RESERVED_KEY, reserved);
    conf.setLong(DFSConfigKeys.DFS_DATANODE_AVAILABLE_SPACE_VOLUME_CHOOSING_POLICY_BALANCED_SPACE_THRESHOLD_KEY, threshold);
    conf.setFloat(DFSConfigKeys.DFS_DATANODE_AVAILABLE_SPACE_VOLUME_CHOOSING_POLICY_BALANCED_SPACE_PREFERENCE_FRACTION_KEY, f);
    conf.setInt(DFSConfigKeys.DFS_DATANODE_SCAN_PERIOD_HOURS_KEY, -1);
    @SuppressWarnings("unchecked")
    VolumeChoosingPolicy<FsVolumeImpl> p =
        ReflectionUtils.newInstance(AvailableSpaceVolumeChoosingPolicy.class, conf);
    FsVolumeList list = new FsVolumeList(Collections.emptyList(),
        new BlockScanner(null, conf), p, conf, null);
    String base = new FileSystemTestHelper().getTestRootDir() + "/" + tag;  // unique per run
    FsVolumeImpl[] v = { vol(conf, base, "d0", C0), vol(conf, base, "d1", C1) };
    for (FsVolumeImpl x : v) list.addVolume(x.obtainReference());
    System.out.println("CSV,tag,step,R,reserved0,reserved1,avail0,avail1,mostLow,chosen");
    for (int step = 1; step <= 100; step++) {
      long a0 = v[0].getAvailable(), a1 = v[1].getAvailable();
      long least = Math.min(a0, a1), mostLow = Long.MIN_VALUE;
      if (a0 <= least + threshold) mostLow = Math.max(mostLow, a0);
      if (a1 <= least + threshold) mostLow = Math.max(mostLow, a1);
      String chosen;
      try (FsVolumeReference ref = list.getNextVolume(StorageType.DISK, null, B)) {
        FsVolumeImpl c = (FsVolumeImpl) ref.getVolume();
        c.reserveSpaceForReplica(B);
        chosen = c == v[0] ? "d0" : "d1";
      } catch (DiskOutOfSpaceException e) {
        chosen = "EXC:" + e.getMessage();
      }
      System.out.println("CSV," + tag + "," + step + "," + reserved + "," + v[0].getReserved() + ","
          + v[1].getReserved() + "," + a0 + "," + a1 + "," + mostLow + "," + chosen);
      if (chosen.startsWith("EXC")) break;
    }
  }

  @Test public void r0()        throws Exception { run("U-R0",   0L,          0.0f,  MiB); }
  @Test public void r512()      throws Exception { run("U-R512", 512 * MiB,   0.0f,  MiB); }
  @Test public void r960()      throws Exception { run("U-R960", 960 * MiB,   0.0f,  MiB); }
  @Test public void eq()        throws Exception { run("U-EQ",   C0 - B,      0.0f,  MiB); }
  @Test public void eq1()       throws Exception { run("U-EQ1",  C0 - B + 1,  0.0f,  MiB); }
  @Test public void r0f75()     throws Exception { run("U-R0-f75",   0L,        0.75f, MiB); }
  @Test public void r512f75()   throws Exception { run("U-R512-f75", 512 * MiB, 0.75f, MiB); }
  @Test public void r512bal()   throws Exception { run("U-R512-bal", 512 * MiB, 0.0f,  10240 * MiB); }
}
```

**B2e. Procedure.**

1. Copy the tree and run the `install` from B2a.
2. Write the test file above into the local copy.
3. `cd $WORK/hadoop-src && mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestDuReservedAvailableSpacePlacement -DfailIfNoTests=false`
4. `grep '^CSV' hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports/*TestDuReservedAvailableSpacePlacement-output.txt > $WORK/u-results.csv`
5. Count, per tag, the steps that chose `d0` and `d1`. Record the exception text and step.
6. Check that the `reserved0`/`reserved1` columns equal `R`. This confirms the key reached `ReservedSpaceCalculatorAbsolute`.
7. Compare with B2f.

**B2f. Predictions.** All values are in bytes, with `B` = 104,857,600.

| Tag | Steps → d0 | Steps → d1 | Failing step and message (most available) | Final avail d0 / d1 |
|---|---|---|---|---|
| U-R0 | 1–10 | 11–40 | 41, `(=75497472 B)` | 25,165,824 / 75,497,472 |
| U-R512 | 1–5 | 6–30 | 31, `(=62914560 B)` | 12,582,912 / 62,914,560 |
| U-R960 | none | 1–21 | 22, `(=67108864 B)` (d0 is now the "high" volume, and too small) | 67,108,864 / 12,582,912 |
| U-EQ | none | none | 1, `(=104857600 B) is less than the block size (=104857600 B)` while d1 has 2,252,341,248 | unchanged |
| U-EQ1 | none | 1–21 | 22, `(=104857599 B)` | 104,857,599 / 50,331,647 |
| U-R0-f75 | 10 in total, random order | 30 in total | 41 | as U-R0 |
| U-R512-f75 | 5 in total | 25 in total | 31 | as U-R512 |
| U-R512-bal | 5, alternating with d1 until d0 is full | 25 | 31; no "Volumes are imbalanced" DEBUG line | as U-R512 |

For the four deterministic `f` = 0.0 tags (not U-EQ):

- On every step that chose `d1` while `d0` still existed, the recorded `mostLow` is < `B` and a "from high available space volumes" DEBUG line appears.
- On every step that chose `d0` (the low volume), `mostLow` is ≥ `B`.
- Invariant: the bytes reserved on volume i never exceed `C_i − R`, and n_i·B ≤ `C_i − R` < (n_i + 1)·B for each tag (U-EQ excepted).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Counts and failing steps match B2f; `mostLow < B` on exactly the steps routed to the high volume | Mechanism works as traced: usage follows the reserve, line 166 routes around a too-small low volume. Claim supported at unit level. |
| A volume chosen when its pre-step `getAvailable()` ≤ `B` | Cap does not hold; claim wrong. |
| With `f` = 0.0, `d0` (low) chosen while `mostLow < B` | Line 166 does not guard as traced; claim wrong. |
| With `f` = 0.0, `d1` chosen while `mostLow ≥ B` and `d0` still has > `B` | Some other routing is at work; trace wrong. |
| `n_0`, `n_1` the same for R = 0, 512 MiB and 960 MiB | Usage does not follow the reserve; claim wrong. |
| `reserved0` ≠ `R` | Key did not take effect (calculator or lookup); run invalid, not a refutation. |
| U-EQ throws at step 1 | Confirms the `<`/`>` boundary mismatch, A3(e): a spurious out-of-space failure, not an overshoot. |
| U-EQ returns `d1` | Boundary handled differently from the trace; A3(e) wrong (the cap claim is unaffected). |
| U-R512-bal totals equal U-R512 | The cap comes from `getAvailable`/`du.reserved` plus the round-robin check, not from line 166. Line 166 only routes. |

**B2h. Controls.**

- R = 0 is the baseline: each volume fills to its capacity.
- The `_bal` run removes line 166 from the path while keeping the reserve.
- The `f75` runs show the counts do not depend on routing order.
- `reserved0`/`reserved1` columns verify the knob landed.
- The DF mock removes host-disk noise. Unique per-run directories avoid metric-name and state reuse.
- Each test builds new policy and volume objects, so no round-robin cursor or reservation carries over.

### B3. Cluster tier

**B3a. Environment and build.**

- **Host:** one Linux host, pseudo-distributed, with 1 NameNode and 1 DataNode with two data directories on the same local file system. No YARN.
- **Build:** a distribution from the local copy, `cd $WORK/hadoop-src && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`, giving `hadoop-dist/target/hadoop-3.4.2/`. Copy it to `$RUN/hadoop`. A previously built 3.4.2 distribution of the same tag may be reused.
- **`$RUN`:** a fresh directory on local disk, for example `/mydata/<operator>-s4/<stem>/`. It needs ≥ 10 GiB usable, and the file system must not be shared storage such as NFS.
- **Environment:**
  - `export HADOOP_HOME=$RUN/hadoop`
  - `export HADOOP_CONF_DIR=$RUN/conf` (copy `$HADOOP_HOME/etc/hadoop/*` there first)
  - `HADOOP_LOG_DIR=$RUN/logs`
  - `HADOOP_PID_DIR=$RUN/pids`
  - `HADOOP_HEAPSIZE_MAX=1g`
  - `JAVA_HOME`: JDK 8 or 11

  Put these in `$RUN/conf/hadoop-env.sh`.
- **Ports:** use a private block to avoid other runs on the node: `NN_RPC=19820`, `NN_HTTP=19870`, `DN_XFER=19866`, `DN_HTTP=19864`, `DN_IPC=19867`. Check they are free with `ss -ltn`.
- **Per-volume budgets with the reserve.** Both volumes are on one file system, so the reserve is set per directory to give each volume an exact HDFS budget `b_i`. Measure once:

  ```
  read TOTAL ROOTRES < <(python3 -c 'import os,sys;s=os.statvfs(sys.argv[1]);print(s.f_blocks*s.f_frsize,(s.f_bfree-s.f_bavail)*s.f_frsize)' $RUN)
  R_i = TOTAL - ROOTRES - b_i
  ```

  This is Java's `getTotalSpace` and `getFreeSpace − getUsableSpace` on Linux. The arithmetic from A2, with `F` = free and `U` = usable, gives:
  - `R − nonDfs = U + D_i − b_i`, which is > 0 while `U > b_i`.
  - DF term = `U − (U + D_i − b_i) − rfr = b_i − D_i − rfr`.
  - Capacity term = `b_i + ROOTRES − D_i − rfr` ≥ the DF term.
  - So `getAvailable = b_i − D_i − rfr`, independent of other users' disk activity and of the other volume.
- **`core-site.xml`:** `fs.defaultFS=hdfs://127.0.0.1:19820`; `hadoop.tmp.dir=$RUN/tmp`.
- **`hdfs-site.xml`:**
  - `dfs.replication=1`
  - `dfs.blocksize=104857600`
  - `dfs.namenode.name.dir=file://$RUN/nn`
  - `dfs.datanode.data.dir=file://$RUN/dn/d0,file://$RUN/dn/d1`
  - `dfs.namenode.rpc-address=127.0.0.1:19820`, `dfs.namenode.http-address=127.0.0.1:19870`
  - `dfs.datanode.address=127.0.0.1:19866`, `dfs.datanode.http.address=127.0.0.1:19864`, `dfs.datanode.ipc.address=127.0.0.1:19867`
  - `dfs.heartbeat.interval=1`
  - `dfs.permissions.enabled=false`
  - `dfs.datanode.fsdataset.volume.choosing.policy=org.apache.hadoop.hdfs.server.datanode.fsdataset.AvailableSpaceVolumeChoosingPolicy`
  - `dfs.datanode.available-space-volume-choosing-policy.balanced-space-threshold=1048576`
  - `dfs.datanode.available-space-volume-choosing-policy.balanced-space-preference-fraction=0.0`
  - plus the reserve keys of B3b.
- **`$RUN/conf/log4j.properties`:** add `log4j.logger.org.apache.hadoop.hdfs.server.datanode.fsdataset.AvailableSpaceVolumeChoosingPolicy=DEBUG`.

**B3b. Knobs.** All are set in `hdfs-site.xml` with plain decimal bytes for the per-directory keys. Each change needs a DataNode restart; the runs below re-format.

| Run | Reserve setting | Budgets | Threshold / fraction |
|---|---|---|---|
| K1 | `dfs.datanode.du.reserved.$RUN/dn/d0 = TOTAL−ROOTRES−1073741824`, `dfs.datanode.du.reserved.$RUN/dn/d1 = TOTAL−ROOTRES−3221225472` | `b0` = 1 GiB, `b1` = 3 GiB | 1 MiB / 0.0 |
| K2 | same form | `b0` = 512 MiB (536870912), `b1` = 2 GiB (2147483648) | 1 MiB / 0.0 |
| K3 (no-166 control) | global `dfs.datanode.du.reserved = TOTAL−ROOTRES−1073741824` | 1 GiB each | 10737418240 (default) / 0.0; volumes stay balanced, so round-robin only |
| K1c (concurrency) | as K1 | as K1 | as K1 |

The key's directory suffix must equal the volume path exactly, with no trailing slash and no `file://`. If `$RUN` contains a symlink, use the path as the DataNode prints it in JMX `VolumeInfo`.

**B3c. Workload.**

- **Sequential runs (K1, K2, K3).** `head -c 104857600 /dev/urandom > $RUN/src/f100m` (one local 100 MiB file, reused). Then, for i = 1..45: `hdfs dfs -put $RUN/src/f100m /t/f$i; echo "$i $?"; sleep 3`.
  - Each file is exactly one full block. The declared `replicaSize` is the file block size, 104,857,600 (`DataStreamer.java:1918`).
  - The per-block footprint is `S = B + M = 104857600 + 819207 = 105676807`.
  - The 3 s sleep lets the NameNode see a fresh heartbeat.
  - K1 demand is 4.5 GiB against 4 GiB of budget, so the limit is reached. About 5 minutes.
- **K1c.** `head -c 1048576000 /dev/urandom > $RUN/src/f1000m` (10 blocks). Then start 8 writers at once: `for w in 1..8: hdfs dfs -put $RUN/src/f1000m /c/w$w &`, then `wait`. Demand is 80 blocks against a capacity of about 40. Repeat 3 times, re-formatting between repetitions.

**B3d. Observables and instruments.** After each put, or every 2 s during K1c:

- **Actual bytes on each volume:**
  - `find $RUN/dn/dX/current -type f -name 'blk_*' -printf '%s\n' | awk '{s+=$1} END{print s+0}'` (blocks + meta)
  - `find ... -name 'blk_*' ! -name '*.meta' | wc -l` (block count)
  - `du -sb $RUN/dn/dX` (whole volume, including small metadata)
- **The check's operand:** `curl -s "http://127.0.0.1:19864/jmx?qry=Hadoop:service=DataNode,name=DataNodeInfo"`. Its `VolumeInfo` JSON gives, per volume, `freeSpace` (= `getAvailable()`), `reservedSpace` (= `R_i`), `usedSpace`, `reservedSpaceForReplicas` and `numBlocks` (`FsDatasetImpl.java:3286-3292, 3324-3328`).
- **Routing:** DataNode-log DEBUG lines "Volumes are imbalanced. Selecting … from high|low available space volumes", plus `Out of space` from the DataNode log.
- **Client:** put exit codes and messages ("could only be written to 0 of the 1 minReplication nodes"). The NameNode log may show `NOT_ENOUGH_STORAGE_SPACE`.
- **Host disk:** `df -B1 $RUN` before and after, for context only.
- Not directly observable: which of the NameNode or DataNode check rejected the final write when both would. Use the logs.

**B3e. Procedure.**

1. `mkdir -p $RUN/{conf,logs,pids,tmp,nn,dn/d0,dn/d1,src}`. Unpack or copy the distribution. Write the configuration (B3a, plus K1 of B3b). Compute `TOTAL`/`ROOTRES` and fill in `R_i`.
2. `hdfs namenode -format -force -nonInteractive`, then `hdfs --daemon start namenode` and `hdfs --daemon start datanode`. Then `hdfs dfsadmin -safemode wait`.
3. Read JMX `VolumeInfo`. It must show `reservedSpace = R_i` for each volume, and `freeSpace` within 1 MiB of `b_i`. If not, fix the key path and restart.
4. `hdfs dfs -mkdir -p /t /c`. Run the sequential workload (B3c), logging after each put: i, exit code, blk-bytes and count per volume, JMX `freeSpace` per volume.
5. Stop: `hdfs --daemon stop datanode; hdfs --daemon stop namenode`. Save logs to `$RUN/results/K1/`.
6. `rm -rf $RUN/nn/* $RUN/dn/d0/* $RUN/dn/d1/*`. Set the K2 values and repeat steps 2–5. Then do the same for K3.
7. K1c: K1 configuration, re-format, start, run the concurrent workload. Record the final per-volume blk bytes. Repeat 3×.
8. Final cleanup per B4.

**B3f. Predictions.** Here `S` = 105,676,807, `B` = 104,857,600, and `n_i` = number of k ≥ 0 with `b_i − k·S > B`.

- **K1.**
  - Puts 1–10 → `d0`, with DEBUG "from low available space volumes".
  - Puts 11–40 → `d1`, with DEBUG "from high available space volumes". From put 11 on, `freeSpace(d0)` ≈ 16,973,754 < `B`.
  - Put 41 fails, as do the rest.
  - Final blk bytes: `d0` = 10·S = 1,056,768,070 ≤ `b0` = 1,073,741,824, and `d1` = 30·S = 3,170,304,210 ≤ `b1` = 3,221,225,472.
  - Final `freeSpace`: `d0` ≈ 16,973,754 and `d1` ≈ 50,921,262 (± 1 MiB for `du`-refresh directory overhead).
- **K2.**
  - `d0` takes puts 1–5 and `d1` takes puts 6–25; put 26 fails.
  - Final blk bytes: `d0` = 528,384,035 ≤ 536,870,912, and `d1` = 20·S = 2,113,536,140 ≤ 2,147,483,648.
- **K3.**
  - Volumes stay within the 10 GiB threshold, so there are no "Volumes are imbalanced" DEBUG lines and line 166 is never evaluated.
  - Puts alternate between `d0` and `d1`; each takes 10. Put 21 fails.
  - Final blk bytes are 1,056,768,070 per volume, each ≤ 1 GiB.
- **Cross-run relations.**
  - `d0` usage in K1 is about twice its usage in K2, so usage follows the reserve.
  - In every sequential run, blk bytes(dX) ≤ `b_X`, so free space on the volume stays ≥ the reserve's share.
- **K1c (secondary, bounded leak A3(b)).**
  - blk bytes(d0) may exceed `b0` in at least one of 3 repetitions, by at most 7·S (≈ 740 MB).
  - `d1` is less likely to overshoot, because the NameNode's scheduled-block subtraction double-counts in-flight blocks once only `d1` has room.
  - No volume exceeds `b_i + 8·S`.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| K1/K2/K3 counts and final blk bytes as predicted, all ≤ `b_i` | Usage follows the reserve on real disk; claim supported. |
| In a sequential run, blk bytes(dX) > `b_X + M` | The cap does not bind sequential writes; claim wrong. |
| Put 11 in K1 lands on `d0` although `freeSpace(d0) < B` | Line 166 or the round-robin check is not enforcing as traced; claim wrong. |
| K1 and K2 give the same `d0` usage | Usage does not follow the reserve; claim wrong. |
| `reservedSpace` in JMX ≠ `R_i` | Knob did not land; run invalid. |
| Writes fail long before the budgets fill, with `freeSpace` ≥ `B` on some volume | Something other than the reserve binds (NameNode heartbeat lag, or the A3(e) boundary). Check logs; the cap is not refuted, but the trace is incomplete. |
| K3 per-volume totals equal K1/K2 arithmetic for its budgets | The cap is independent of line 166. Line 166 only routes. |
| K1c overshoot > 0 but ≤ 7·S | Confirms leak A3(b): the cap holds only up to in-flight acked bytes under concurrency. |
| K1c overshoot = 0 in all repetitions | The leak did not show at this concurrency (not a refutation of A3(b); raise the writer count). |
| K1c overshoot > 8·S | Leak larger than traced; A3 incomplete. |

**B3h. Controls.**

- JMX `reservedSpace` proves the knob reached each volume.
- K3 removes line 166 from the path.
- K2 against K1 isolates the reserve as the variable.
- Counting `blk_*` files excludes `dfsUsed` cache, VERSION and scanner files.
- `freeSpace` is checked against an independent `find` sum.
- The 3 s sleep and `dfs.heartbeat.interval=1` remove NameNode staleness as a cause.
- Re-formatting between runs removes carry-over.
- The budget formula is independent of other users' disk activity (B3a). Record `df` anyway.

**B4. Risks and cleanup.**

- **Disk:** at most about 4.9 GiB of block data, plus 1.1 GiB of source files, under `$RUN` on local disk. Check `df -B1 $RUN` ≥ 10 GiB usable before starting, and abort if usable falls below 6 GiB.
- **Shared storage:** never point `$RUN` at it.
- **Shared source tree:** never build in it or add files to it.
- **Ports:** 19820/19870/19864/19866/19867. Check them first.
- **Memory:** two JVMs of ≤ 1 GiB each.
- **Cleanup after each run and at the end:**
  1. `hdfs --daemon stop datanode; hdfs --daemon stop namenode`
  2. `jps`: no `NameNode` or `DataNode` from `$RUN` may remain; kill any by the pid in `$RUN/pids`.
  3. `rm -rf $RUN/nn $RUN/dn $RUN/src $RUN/tmp`. Keep `$RUN/results` and `$RUN/logs`.
- **Unit tier:** delete `$WORK/hadoop-src/hadoop-hdfs-project/hadoop-hdfs/target/test/data` and the local copy when done. No processes outlive `mvn`.

## C. Sources read

hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/AvailableSpaceVolumeChoosingPolicy.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/RoundRobinVolumeChoosingPolicy.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsVolumeImpl.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsVolumeImplBuilder.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsVolumeList.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetImpl.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/ReservedSpaceCalculator.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/BlockPoolSlice.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/LocalReplicaInPipeline.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/BlockReceiver.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataXceiver.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataXceiverServer.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/BlockScanner.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataNode.java (grep only)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSNamesystem.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/BlockPlacementPolicyDefault.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/DatanodeDescriptor.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/common/HdfsServerConstants.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java
hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DataStreamer.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/HdfsClientConfigKeys.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/DF.java
hadoop-common-project/hadoop-common/src/main/resources/core-default.xml
hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/test/GenericTestUtils.java (grep only)
hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/TestAvailableSpaceVolumeChoosingPolicy.java
hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/TestFsVolumeList.java
hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/TestSpaceReservation.java

## D. Stage-4 feedback

none yet
