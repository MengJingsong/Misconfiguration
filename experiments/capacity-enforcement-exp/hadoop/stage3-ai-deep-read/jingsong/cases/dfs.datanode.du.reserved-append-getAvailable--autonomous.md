# dfs.datanode.du.reserved — verification solution  <!-- file: cases/dfs.datanode.du.reserved-append-getAvailable--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`FsVolumeImpl.java:1265`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsVolumeImpl.java#L1265), `if (getAvailable() < bytesReserved)` in `FsVolumeImpl.append(String, ReplicaInfo, long, long)` (row unit; this is also the main enforcement point for appends) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive`. Before a DataNode reopens a finalized replica for append, it refuses (DiskOutOfSpaceException) unless the volume's available space, which is the filesystem space minus `dfs.datanode.du.reserved`, minus HDFS bytes and minus open-write reservations, covers the rest of a full block (`blockSize - replicaLen`). Raising the reserve makes appends fail earlier, so HDFS bytes on the volume stay at or below `capacity - reserved`. Overshoot windows exist (A3). |
| Ground | — |

Stem parts: constraint `dfs.datanode.du.reserved`; function `append` (the method enclosing the given if statement); operand `getAvailable` (written `getAvailable()` at the check; parentheses dropped for the file name).

## A. Constraint trace

**A1. The constraint.**
- **Name:** `dfs.datanode.du.reserved`, a configuration key. It can also be set per volume or storage type, in this order of priority: `dfs.datanode.du.reserved.<dir>.<storagetype>` > `dfs.datanode.du.reserved.<dir>` > `dfs.datanode.du.reserved.<storagetype>` > `dfs.datanode.du.reserved` (`ReservedSpaceCalculator.getReservedFromConf`, ReservedSpaceCalculator.java:107-112; hdfs-default.xml:399-412).
- **Declaration:** [`DFSConfigKeys.java:964`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java#L964), `DFS_DATANODE_DU_RESERVED_KEY = "dfs.datanode.du.reserved"`. The default `DFS_DATANODE_DU_RESERVED_DEFAULT = 0` is at DFSConfigKeys.java:965. The `*-default.xml` entry is [`hdfs-default.xml:397`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml#L397), value `0`.
- **Unit and default:** bytes; default 0 (the Java constant and the xml agree). The base key is read with `getLongBytes`, so it accepts size suffixes. The per-dir and per-type variants are read with `getLong`, so they take plain bytes only (ReservedSpaceCalculator.java:108-111).
- **Other sources of the same limit** (the limit-side operand `getAvailable()` is derived from several sources):
  - The calculator class `dfs.datanode.du.reserved.calculator`, default `ReservedSpaceCalculatorAbsolute` (DFSConfigKeys.java:959-963; hdfs-default.xml:383). It decides whether the key above, or `dfs.datanode.du.reserved.pct` (DFSConfigKeys.java:966-968), or the max/min of the two is used (ReservedSpaceCalculator.java:126-232).
  - The runtime filesystem figures `DF.getCapacity()`, `DF.getUsed()` and `DF.getAvailable()` (= `File.getTotalSpace()`, `getTotalSpace() - getFreeSpace()`, `getUsableSpace()`; DF.java:85-97).
  - The cached HDFS usage `BlockPoolSlice.getDfsUsed()` (a `du`-based `CachingGetSpaceUsed`, refreshed every `fs.du.interval` ± `fs.getspaceused.jitterMillis`; BlockPoolSlice.java:218, 320-321).
  - The in-memory open-write reservation `reservedForReplicas` (FsVolumeImpl.java:128).
  - `dfs.datanode.fixed.volume.size`, which caches capacity (FsVolumeImpl.java:176-181), and `configuredCapacity`, which is test-only (FsVolumeImpl.java:456-465).
  - The user-tuned one is `dfs.datanode.du.reserved`.
- **How it is set:** in `hdfs-site.xml` on the DataNode. The value is read once, when the volume is constructed (`ReservedSpaceCalculatorAbsolute` constructor, ReservedSpaceCalculator.java:126-130, called from the FsVolumeImpl constructor, FsVolumeImpl.java:173-175). A change therefore needs a DataNode restart, or a volume hot-swap (`dfs.datanode.data.dir` reconfig), which rebuilds the volume. `DataNode.java` has no reconfiguration handler for this key (grep finds no `DU_RESERVED` in DataNode.java).
- **Reader:** the DataNode (each `FsVolumeImpl`).

**A2. What it caps.** It caps disk space on one DataNode volume (the filesystem that holds a `dfs.datanode.data.dir` entry). It is the space that HDFS must leave for non-HDFS use. The check at the target compares:
- **Usage side:** `bytesReserved = estimateBlockLen - replicaInfo.getNumBytes()` (FsVolumeImpl.java:1264). This is the space still needed to grow the appended replica to a full block. `estimateBlockLen` is the block's `numBytes` as sent by the client, which is the file's block size (DataStreamer.java:1917-1918; passed as `b.getNumBytes()` at FsDatasetImpl.java:1409-1410).
- **Limit side:** `getAvailable()` (FsVolumeImpl.java:474-482):
  `min( getCapacity() - dfsUsed - reservedForReplicas , DF.usable - max(R - nonDfsUsed, 0) - reservedForReplicas )`, floored at 0.
  - `getCapacity() = max(DF.total - R, 0)` (FsVolumeImpl.java:434-455).
  - `R = getReserved()` (FsVolumeImpl.java:556-558).
  - `nonDfsUsed = max(DF.used - dfsUsed, 0)` (FsVolumeImpl.java:484-504).

  When `R >= nonDfsUsed` and the filesystem has no root-reserved blocks (`usable == free`), both terms reduce to `DF.total - R - dfsUsed - reservedForReplicas`. The check therefore enforces `dfsUsed + reservedForReplicas + (blockSize - len) <= total - R`.

**A3. Mechanism.**
1. A client opens a file for append. `DataStreamer` sends `WRITE_BLOCK` with stage `PIPELINE_SETUP_APPEND`, and `numBytes` set to the file's block size (DataStreamer.java:1917-1918). Older clients send 0, and DataXceiver then substitutes `dfs.blocksize` (DataXceiver.java:756-758; DataXceiverServer.java:196-197).
2. `BlockReceiver` calls `datanode.data.append(block, newGs, minBytesRcvd)` (BlockReceiver.java:233-234). For the append-recovery stage, `recoverAppend` is called instead (BlockReceiver.java:240). It reaches the same code for FINALIZED replicas (FsDatasetImpl.java:1536-1538).
3. `FsDatasetImpl.append(ExtendedBlock,...)` checks the state and length (FsDatasetImpl.java:1379-1405), then calls the private `append(bpid, replicaInfo, newGS, b.getNumBytes())` (FsDatasetImpl.java:1409-1410). That method uncaches the block, breaks hardlinks, and calls `FsVolumeImpl.append` (FsDatasetImpl.java:1431-1452).
4. **The check:** [`FsVolumeImpl.java:1265`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsVolumeImpl.java#L1265) `if (getAvailable() < bytesReserved)` throws `DiskOutOfSpaceException("Insufficient space for appending to " + replicaInfo)` (FsVolumeImpl.java:1265-1268).
   - **Reached:** nothing on disk has changed yet. The replica stays FINALIZED in `finalized/`. `BlockReceiver` rethrows a DiskOutOfSpaceException without a disk check or cleanup (BlockReceiver.java:282-284). The client's pipeline setup fails. With replication 1, the append fails at the client: the error surfaces on `write`/`hflush`/`close`, and the file stays open with a lease until lease recovery.
   - **Passed:** a new RBW replica is built with `setBytesToReserve(bytesReserved)` (FsVolumeImpl.java:1274-1282). The files are moved to `rbw/` (FsVolumeImpl.java:1291), and `reserveSpaceForReplica(bytesReserved)` adds to `reservedForReplicas` (FsVolumeImpl.java:1295, 629-635). Later writers see that much less space.
5. **Release:** as packets are acked, `setBytesAcked` releases the acked bytes from `reservedForReplicas` (LocalReplicaInPipeline.java:145-154). On finalize, `addFinalizedBlock` releases the rest (FsVolumeImpl.java:1034-1036) and adds the **full** new block length plus meta to `dfsUsed` (BlockPoolSlice.java:445-454).

**Bypasses and overshoots** (all from reading the code; stage 4 should confirm):
- (a) **Acked but not finalized bytes are counted nowhere.** On ack, the bytes leave `reservedForReplicas`, but `dfsUsed` grows only at finalize. In the DF term, they show up as `nonDfsUsed` and lower `max(R - nonDfsUsed, 0)` one for one. While a replica is being written, `getAvailable()` therefore overstates by the bytes acked so far. Concurrent writers can push real usage past `total - R` by up to the sum of their in-flight acked bytes.
- (b) **Double count after append.** On finalize after an append, `dfsUsed` gains the whole block length, but the pre-append bytes were already counted (no decrement in the append path; `decDfsUsed` is called only on deletion, FsVolumeImpl.java:369-392). `dfsUsed` is over-counted by the old length until the next `du` refresh (`fs.du.interval`, default 600000 ms, ±60000 ms jitter; CommonConfigurationKeysPublic.java:74-94). This makes the check conservative, not leaky.
- (c) **Not atomic with other writers.** The check (line 1265) and the reservation (line 1295) are separate steps. They run under the volume write lock for appends (FsDatasetImpl.java:1381-1382, 1434-1435), but new-block writes reserve through `createRbwFile` (FsVolumeImpl.java:1015-1024) after the volume-choosing check (RoundRobinVolumeChoosingPolicy.java:110-126), on a different path.
- (d) **Non-HDFS usage above R removes the reserve's effect.** If non-HDFS data already exceeds R, `max(R - nonDfsUsed, 0) = 0`, and the limit is just `DF.usable - reservedForReplicas`.
- (e) **Root-reserved blocks.** On ext4 with root-reserved blocks (`usable < free`), the DF term is smaller than the capacity term by about the root reserve. Positioning `getAvailable()` near a boundary with R alone is then not possible on such a filesystem. The tiers below use a dedicated ext4 image made with `-m 0`.
- (f) **RBW recover-append skips the check.** For an RBW replica, `recoverAppend` only bumps the GS (FsDatasetImpl.java:1539-1541), with no check and no new reservation.
- (g) **Provided storage is separate.** `ProvidedVolumeImpl.append` (ProvidedVolumeImpl.java:614) is a separate implementation, not covered here.

**A4. Other consumers.** Other code uses the same volume space without this check:
- New blocks: client writes via `createRbw`, replication/balancer via `createTemporary`. These are gated by the volume-choosing policies (RoundRobinVolumeChoosingPolicy.java:110-126; AvailableSpaceVolumeChoosingPolicy.java:245) and by NameNode placement (remaining space ≥ blockSize × `dfs.namenode.block-placement-policy.min-blocks-for-write`, DFSConfigKeys.java:1299-1302).
- On-disk metadata files: `.meta`, the `dfsUsed` cache file, `replicas` and `scanner.cursor` files.
- The `lazypersist`/RAM_DISK path.
- The block scanner state.
- Any non-HDFS process writing to the same filesystem. du.reserved only *reserves room* for these; it does not limit them.
- DataNode logs, if `HADOOP_LOG_DIR` is on the same filesystem.

**A5. Evidence beyond the source.**
- In-tree tests:
  - `TestWriteToReplica.testAppend` (hadoop-hdfs/src/test/.../fsdataset/impl/TestWriteToReplica.java:178-196). It inflates `dfsUsed` and expects `DiskOutOfSpaceException` with message prefix "Insufficient space for appending to ".
  - `TestSpaceReservation.testReservedSpaceForAppend` (TestSpaceReservation.java:595-633). It checks that an append reserves `BLOCK_SIZE - len`.
  - `TestSpaceReservation.createFileAndTestSpaceReservation` (TestSpaceReservation.java:168-222).
- Docs: hdfs-default.xml:383-438 (du.reserved, calculator, pct).
- No JIRA was consulted.

## B. Verification solution

**B1. Claim under test.** A DataNode refuses an append to a finalized replica exactly when the volume's `getAvailable()` is below `blockSize - replicaLen`, and `getAvailable()` falls one-for-one as `dfs.datanode.du.reserved` rises. So on a volume where only HDFS writes, sequential appends stop when HDFS bytes on the volume reach about `total - R - (blockSize - replicaLen)`, and the stop point moves by −1 byte per byte of R. It would be wrong if appends succeed with `getAvailable() < blockSize - len`, or fail with `getAvailable() >= blockSize - len`, or if the stop point does not move with R.

Shared numbers:
- block size `B = 16 MiB = 16777216`
- seeded replica length `L = 1 MiB = 1048576`
- `B - L = 15728640`
- appended chunk `c = 1 MiB`

### B2. Unit tier

**B2a. Environment and build.**
- **Toolchain:** JDK 8, Maven 3.3+, a private copy of the tree (`rsync -a ~/hadoop-3.4.2/ $RUN/src/`, never the shared copy). Build with `cd $RUN/src && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
- **Test source:** new class `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/TestAppendDuReservedBoundary.java`. It sits in that package so it can call the package-private `getReserved()` and `getDfAvailable()`.
- **Data filesystem** (needs sudo; `$RUN` is the stage-4 run directory on local disk, e.g. `/mydata/<person>-s4/<case>`):
  ```
  mkdir -p $RUN/mnt $RUN/snap && truncate -s 2G $RUN/vol.img
  mkfs.ext4 -F -m 0 -O ^has_journal $RUN/vol.img
  sudo mount -o loop $RUN/vol.img $RUN/mnt && sudo chown $(id -u):$(id -g) $RUN/mnt
  stat -f $RUN/mnt   # check "Free blocks" == "Available blocks"
  ```
  Use `-m 0` so that usable == free (A3e). If sudo is unavailable, use any XFS or other filesystem on local disk where `stat -f` shows Free == Available and no other process writes during the run. Record that choice.
- **JVM:** Surefire defaults; `-Xmx1g` is enough.

**B2b. Knobs.**
- **Knob:** `dfs.datanode.du.reserved` (set in the test `Configuration` before each MiniDFSCluster start; the volume reads it at construction).
- **Calibration values:** `T` = `FsVolumeImpl.getCapacity()` with R=0 (= DF total). `D` = `getDfsUsed()` after seeding and a du refresh.
- **Values:** `R(δ) = T - D - (B - L) - δ` for `δ ∈ {-4 MiB, -256 KiB, +256 KiB, +4 MiB}`, which aims `getAvailable()` at `15 MiB + δ`, plus the control `R = 0`. These straddle the boundary at two distances: ±4 MiB is robust to `du` rounding (directory blocks, 4 KiB allocation), and ±256 KiB is tight. R ≈ 2 GiB ≫ non-HDFS usage on a fresh image, so `max(R - nonDfs, 0) = R - nonDfs`.
- **Fixed settings:**
  - `fs.du.interval=500`
  - `fs.getspaceused.jitterMillis=0`
  - `dfs.datanode.cached-dfsused.check.interval.ms=0` (restart re-runs du rather than loading a cached value; BlockPoolSlice.java:338-382)
  - `dfs.blocksize=16m`, `dfs.replication=1`
  - `dfs.datanode.scan.period.hours=-1`

**B2c. Workload.**
- **Seeding:** at R=0, create `/t/f1` with `fs.create(p, true, 4096, (short)1, B)`, write `L` bytes and close. This produces one FINALIZED replica of length L. Wait 1.5 s for a du refresh, read `D`, shut down with `cluster.shutdown(false)` and snapshot the base dir (`$RUN/mnt/mdfs`) to `$RUN/snap/` (off the image).
- **Per δ:** restore the snapshot into `$RUN/mnt/mdfs` (`rsync -a --delete`) and start `new MiniDFSCluster.Builder(conf_R, new File(mnt,"mdfs")).format(false).numDataNodes(1).storagesPerDatanode(1).build()`. Read the operand, then call the dataset directly:
  `ExtendedBlock eb = DFSTestUtil.getFirstBlock(fs, p); ExtendedBlock req = new ExtendedBlock(eb); req.setNumBytes(B); ds.append(req, eb.getGenerationStamp()+1, L);`
  This mirrors what the client sends (A3 step 1), so `bytesReserved = B - L = 15728640`. The arithmetic: `getAvailable() = T - R - D' - 0 = 15 MiB + δ + (D - D')`, where `D'` is the dfsUsed after restart, expected to equal D within a few KiB.
- **Client-path variant** (same restore, δ = −4 MiB and +4 MiB): `fs.append(p)`, write `c`, `hflush()`, `close()`.

**B2d. Observables and instruments.** Logged per run through `LOG.info` in the test and copied to the readings file:
- `vol.getCapacity()`, `vol.getDfsUsed()`, `vol.getReservedForReplicas()`, `vol.getReserved()` and `vol.getDfAvailable()`.
- `vol.getAvailable()` read immediately before the `append` call (this is the operand; call it `A`).
- The outcome: a returned `ReplicaHandler`, or a `DiskOutOfSpaceException` and its message.
- `vol.getReservedForReplicas()` after the call.
- Whether the block file is still under `finalized/` (via `FsDatasetTestUtils`/`cluster.getBlockFile`) or now under `rbw/`.

Not directly observable: the exact `nonDfsUsed` (derive it as `T - getDfAvailable() - getDfsUsed()`). There is also a small race between reading `A` and the check. Nothing else writes in the JVM, so it should be zero.

**B2e. Procedure.**
1. Mount the image (B2a). Copy the tree, build, and add the test class (B2c), with one `@Test` per δ plus the calibration `@BeforeClass`.
2. Run `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestAppendDuReservedBoundary -Dhdfs.minidfs.basedir=$RUN/mnt/mdfs`. The test builds the cluster with an explicit base dir, so the property is only a belt-and-braces setting.
3. Run the client-path variant: `-Dtest=TestAppendDuReservedBoundary#clientAppend*`.
4. Collect `target/surefire-reports/*-output.txt`.
5. After each δ, assert `(outcome == DiskOutOfSpaceException) == (A < B - L)`. Record A and the outcome even when the assertion holds.

**B2f. Predictions.**

| δ | expected A (bytes) | outcome | reservedForReplicas after | replica dir |
|---|---|---|---|---|
| R=0 (control) | ≈ T - D (≈ 2 GiB) | handler returned | 15728640 | `rbw/` |
| −4 MiB | ≈ 11534336 (± few KiB) | DiskOutOfSpaceException "Insufficient space for appending to …" | 0 | `finalized/`, length L |
| −256 KiB | ≈ 15466496 | exception | 0 | `finalized/` |
| +256 KiB | ≈ 15990784 | handler returned | 15728640 | `rbw/` |
| +4 MiB | ≈ 19922944 | handler returned | 15728640 | `rbw/` |

In every row, the outcome depends only on whether `A < 15728640`. Each successful append lowers `getAvailable()` by exactly 15728640 immediately afterwards.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Outcome matches `A < B - L` in all rows, and the table above holds | Claim confirmed at the mechanism level |
| An append succeeds with `A < 15728640` | Claim wrong (check bypassed) |
| An append fails with `A >= 15728640` | Claim wrong (check uses something other than `getAvailable()`/`B - L`; inspect the message) |
| A differs from `15 MiB + δ` by more than ~64 KiB, but the outcome still matches A | Positioning error only (du rounding, or `nonDfs > R`); claim still holds; record it |
| A ≈ 0 for every δ | `usable < free` (root reserve) or `nonDfs > R`; the setup is invalid; check `stat -f` and redo |
| `reservedForReplicas` after success ≠ B - L | The reservation does not follow the check; a partial refutation of the "cap" part |
| Failure message is "Out of space…" or a NameNode placement error | A different check fired; not this one; setup error |

**B2h. Controls.**
- The R=0 run shows that the same call succeeds when the reserve is absent.
- The δ pairs at ±4 MiB and ±256 KiB on both sides show that the outcome flips at the boundary.
- `A` is read in the same thread just before the call.
- The data is restored from one snapshot, so every δ starts from the identical replica.
- The image is dedicated, so no outside writer moves DF figures.
- Asserting that the replica stays in `finalized/` on failure shows that nothing was written (the check precedes any move).

### B3. Cluster tier

**B3a. Environment and build.**
- **Distribution:** one Linux host, pseudo-distributed. Build it from the private copy: `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`, then unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `$RUN/hadoop`. Reuse an existing built distribution if stage 4 has one.
- **Daemons:** NameNode and one DataNode (no YARN). `HADOOP_HEAPSIZE_MAX=1g`, `HADOOP_LOG_DIR=$RUN/logs`, `HADOOP_PID_DIR=$RUN/pids`, `HADOOP_CONF_DIR=$RUN/conf`.
- **Data filesystem:** the same 2 GiB `-m 0` image mounted at `$RUN/mnt` (B2a; recreate it fresh for this tier).
- **core-site.xml:**
  - `fs.defaultFS=hdfs://localhost:9000`
  - `hadoop.tmp.dir=$RUN/tmp`
  - `fs.du.interval=5000`
  - `fs.getspaceused.jitterMillis=0`
- **hdfs-site.xml:**
  - `dfs.namenode.name.dir=$RUN/nn` (off the image)
  - `dfs.datanode.data.dir=$RUN/mnt/dn`
  - `dfs.replication=1`
  - `dfs.blocksize=16m`
  - `dfs.datanode.cached-dfsused.check.interval.ms=0`
  - `dfs.datanode.du.reserved=<R>` (B3b)
  - `dfs.datanode.scan.period.hours=-1`
  - Default ports (NN 9000/9870, DN 9866/9864/9867). Check first with `ss -ltn` that they are free.

**B3b. Knobs.** `dfs.datanode.du.reserved` in `hdfs-site.xml`. A change needs a DataNode restart (`hdfs --daemon stop datanode; hdfs --daemon start datanode`). Values:
- **Calibration:** R = 0. Measure `T = df -B1 --output=size $RUN/mnt | tail -1` (= DF total) and `D` = VolumeInfo `usedSpace` after seeding and one du refresh.
- **Boundary pair:** `R = T - D - 15728640 - δ`, `δ ∈ {-4 MiB, +4 MiB}`.
- **Fill pair:** `R_F(a) = T - D_F - a`, `a ∈ {48 MiB, 80 MiB}`, where `D_F` is usedSpace after seeding the fill files. These show that the stop point moves with R.

**B3c. Workload.**
- **Local chunk:** `head -c 1048576 /dev/urandom > $RUN/c1m.bin`.
- **Seeding (R=0):**
  ```
  hdfs dfs -mkdir -p /t
  hdfs dfs -D dfs.blocksize=16m -D dfs.replication=1 -put $RUN/c1m.bin /t/fA
  ```
  Repeat the `-put` for `/t/fB` and `/t/g001 … /t/g080`. That is 82 files of L = 1 MiB in one partial 16 MiB block each, about 83 MiB of HDFS data on the 2 GiB image.
- **Boundary test:** `hdfs dfs -appendToFile $RUN/c1m.bin /t/fA` at δ = −4 MiB (operand ≈ 11 MiB < 15 MiB), then `/t/fB` at δ = +4 MiB (≈ 19 MiB ≥ 15 MiB).
- **Fill test:** at each `R_F(a)`, append 1 MiB to `g001, g002, …` in order, one append per file (each target block stays partial, so every append goes through the target check with `B - L = 15 MiB`). Sleep 6 s after each append (> `fs.du.interval`), so `du` corrects the double count (A3b). Stop at the first failure.
- **Fill arithmetic:** per successful append, HDFS bytes grow by `s ≈ 1 MiB + 8 KiB` (data plus checksum: 4 bytes per 512 bytes). Appends succeed while the operand `A_k = a - k·s ≥ 15 MiB`, so `N ≈ floor((a - 15 MiB)/s) + 1`. That gives N ≈ 33 for a = 48 MiB and N ≈ 65 for a = 80 MiB. 80 seeded files are enough for both.
- **Duration:** about 15 minutes.

**B3d. Observables and instruments.**
- **Operand:** DataNode JMX `curl -s 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=DataNodeInfo'`, attribute `VolumeInfo` (a JSON string keyed by volume). Fields:
  - `freeSpace` = `getAvailable()` (FsDatasetImpl.java:3297-3313, 3325)
  - `usedSpace` = dfsUsed
  - `reservedSpace` = R
  - `reservedSpaceForReplicas`
  Read it before and after every append.
- **Actual resource:**
  - `du -sb $RUN/mnt/dn`: HDFS bytes on the volume.
  - `df -B1 --output=size,used,avail $RUN/mnt`: filesystem figures. Non-HDFS usage = df used − du of `dn`.
  - Read both after every append.
- **Outcome:** the exit status of `hdfs dfs -appendToFile`, and `grep -c "Insufficient space for appending to" $RUN/logs/*datanode*.log`. Also grep for "Out of space" and "could only be written to" to spot other checks.
- **Replica location:** `find $RUN/mnt/dn -name 'blk_*' -newer <marker>`, to see whether a failed append's replica stayed in `finalized/`.
- Not observable: per-replica acked-but-unfinalized bytes (A3a); with sequential appends this is zero between steps.

**B3e. Procedure.**
1. Mount a fresh image. Write the configs, then run `hdfs namenode -format -nonInteractive`, `hdfs --daemon start namenode` and `hdfs --daemon start datanode`. Wait for `hdfs dfsadmin -report` to show one live node.
2. Seed (B3c). Sleep 10 s. Record `T`, `D`, VolumeInfo, `du` and `df`. Check that df used − du(dn) (non-HDFS) is far below the R values about to be used.
3. **Boundary δ = −4 MiB:** stop the DN, set R, start the DN, wait for it to register (`hdfs dfsadmin -report`) and record VolumeInfo (`freeSpace` = A). If A is not within ±1 MiB of `15 MiB + δ`, recompute R from the new `usedSpace` and restart. Then run `hdfs dfs -appendToFile $RUN/c1m.bin /t/fA`. Record the exit code, the DN log grep, VolumeInfo, du, df and `hdfs fsck /t/fA -files -blocks`. Then release the lease with `hdfs debug recoverLease -path /t/fA -retries 5`.
4. **Boundary δ = +4 MiB:** restart with the new R, re-check A, append to `/t/fB`, and record the same items.
5. **Control R = 0:** restart and append to `/t/fA`; record.
6. **Fill a = 48 MiB:** restart with `R_F(48 MiB)` (recompute `D_F` from the current `usedSpace`). Run the append loop of B3c, recording all observables at each step, until the first non-zero exit. Recover the lease on the failed file.
7. **Fill a = 80 MiB:** restart with `R_F(80 MiB)` (again from the current `usedSpace`, so the starting operand is 80 MiB). Continue the loop with the next unused `g` files.
8. Clean up (B4).

**B3f. Predictions.**
- **Boundary δ = −4 MiB:** `freeSpace` ≈ 11.0 MiB < 15728640. `appendToFile` exits non-zero, and the DN log shows one "Insufficient space for appending to". `du -sb dn` is unchanged (±4 KiB) and `fsck` shows the length still 1048576. `reservedSpaceForReplicas` is 0 afterwards.
- **Boundary δ = +4 MiB:** `freeSpace` ≈ 19.0 MiB. The append succeeds, `fsck` length is 2097152, `du` grows by ≈ 1 MiB + 8 KiB, and there is no "Insufficient space" line.
- **Control R = 0:** the append to `/t/fA` succeeds.
- **Fill:**
  - N(48 MiB) = 33 ± 2 successes, and N(80 MiB) = 65 ± 2 counted from its own start.
  - The first failure in each fill is the "Insufficient space for appending to" message.
  - At the stop, `freeSpace` is in `[15 MiB - s, 15 MiB)`. `du -sb dn` ≤ `T - R_F - 14 MiB` and ≥ `T - R_F - 16 MiB`.
  - The ceiling on HDFS bytes at the stop is `T - R - ~15 MiB` in both runs, so the HDFS bytes at the stop differ by ≈ 32 MiB (the R difference), ±2 MiB.
  - `df avail` on the mount at the stop ≥ R − nonDfs.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Boundary and fill predictions hold | Confirmed: du.reserved, through `getAvailable()`, caps HDFS bytes reached by appends |
| Append succeeds with `freeSpace < 15728640` just before it | Wrong: the check does not gate appends |
| Fill: HDFS bytes at the stop do not move with R (the 32 MiB difference is absent) | Wrong: the reserve does not set the stop point |
| Fill stops through "Out of space" or NameNode "could only be written to" instead | A different check fired (new block); redesign the chunking; not a reading on this check |
| N about half of predicted, with `usedSpace` > `du -sb dn` before refresh | The double count (A3b) was not corrected by du in time; the check is more conservative than the formula; note it, not a refutation |
| `du -sb dn` at the stop > `T - R_F` | Overshoot past the reserve; report the size (A3a/c) |
| `freeSpace` ≈ 0 regardless of R | `usable < free` or `nonDfs > R`; invalid setup |
| R=0 control append fails | Something else is blocking appends; the run is invalid |

**B3h. Controls.**
- The R=0 append and the +4 MiB run show that the same command succeeds when the operand is above the boundary.
- The −4 MiB run shows that it fails below.
- The two fill values isolate R as the only change: the same files, chunk size and sleep.
- The DN log message ties each failure to this check rather than to volume choosing or NameNode placement.
- `du`/`df` on a dedicated image rule out outside writers, and the NameNode and logs are kept off the image.
- `fsck` lengths confirm that nothing was written on a failed append.

**B4. Risks and cleanup.**
- **Loop image:** the 2 GiB sparse file is in `$RUN` on local disk. Mounting needs sudo. Unmount with `sudo umount $RUN/mnt`, then `rm $RUN/vol.img`.
- **Disk:** the build copy is several GB, in `$RUN/src` on local disk, never on shared storage. Nothing is added to the shared source tree.
- **Ports:** 9000, 9870, 9864, 9866 and 9867; check before starting and pick others if they are taken.
- **Leases:** failed appends leave files open. Run `hdfs debug recoverLease` (B3e).
- **Daemons:** `hdfs --daemon stop datanode`, `hdfs --daemon stop namenode`, then `jps` must show no `NameNode`, `DataNode`, or leftover Surefire/MiniDFSCluster JVMs. Kill any by PID that belong to this run only.
- **Unit tier:** MiniDFSCluster shuts down in `@After`/`@AfterClass` (`cluster.shutdown(true)` at the very end).
- **Final cleanup:** remove `$RUN/mnt/*` before unmounting. Keep `$RUN/logs` and the readings.

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsVolumeImpl.java (115-200, 405-660, 1000-1040, 1200-1320)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetImpl.java (1379-1460, 1523-1555, 3278-3330)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/ReservedSpaceCalculator.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsVolumeImplBuilder.java (80-95)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/BlockPoolSlice.java (137, 218-275, 313-330, 338-382, 435-454)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/LocalReplicaInPipeline.java (70-180)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/BlockReceiver.java (180-300)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataXceiver.java (700-800)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataXceiverServer.java (178-200)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/RoundRobinVolumeChoosingPolicy.java (80-126)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java (43-46, 172-189, 959-968, 1243, 1299-1302)
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml (383-438)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DataStreamer.java (1910-1920)
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/DF.java (40-100)
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/CachingGetSpaceUsed.java (grep: refresh/jitter)
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/CommonConfigurationKeysPublic.java (74-94)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/TestSpaceReservation.java (80-225, 590-636)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/TestWriteToReplica.java (170-205)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/TestFsDatasetImpl.java (1420-1455)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/MiniDFSCluster.java (169, 243, 346, 622-634, 2173-2180, 2475, 2624-2631)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/DFSTestUtil.java (848)

## D. Stage-4 feedback

none yet
