# dfs.namenode.resource.du.reserved — verification solution  <!-- file: cases/dfs.namenode.resource.du.reserved-isResourceAvailable-duReserved--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`NameNodeResourceChecker.java:87`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/NameNodeResourceChecker.java#L87) — `if (availableSpace < duReserved)` in `CheckedVolume.isResourceAvailable()` (row unit; this is also the main enforcement point) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive` — the key sets a free-space floor on every local NameNode edits volume (plus any `dfs.namenode.resource.checked.volumes`); once usable space falls below it, the active NameNode's resource monitor puts it in resource-low safe mode, which rejects every namespace mutation, so the NameNode's own edit-log growth on that volume stops near `usable size − reserved`. It is a reactive, polled floor (5 s by default) with a bounded overshoot (in-flight edits plus one 1 MiB edit-log preallocation chunk), not a hard write cap. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- Name: `dfs.namenode.resource.du.reserved` (configuration key).
- Declared: [`DFSConfigKeys.java:1243`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java#L1243) (`DFS_NAMENODE_DU_RESERVED_KEY`); default constant `DFS_NAMENODE_DU_RESERVED_DEFAULT = 1024 * 1024 * 100` at `DFSConfigKeys.java:1244`.
- `hdfs-default.xml:1077-1085`: value `104857600`, "The amount of space to reserve/require for a NameNode storage directory in bytes. The default is 100MB. Support multiple size unit suffix". The Java constant and the XML value agree (100 MiB = 104857600 B); `hdfs-default.xml` is loaded into every `HdfsConfiguration`, so the XML value is what `conf.getLongBytes` returns unless overridden — the same number either way.
- Unit: bytes, size suffixes accepted (`Configuration.getLongBytes`, `Configuration.java:1624`; read at `NameNodeResourceChecker.java:112-113`).
- Read by: the NameNode only, once, in the `NameNodeResourceChecker` constructor (`NameNodeResourceChecker.java:108-113`), which is built in `FSNamesystem.startCommonServices` (`FSNamesystem.java:1344`). Stored in the `final long duReserved` field (`NameNodeResourceChecker.java:52`).
- How set: `hdfs-site.xml` on the NameNode host (or a `-D` generic option at NameNode start). It is not among the NameNode's reconfigurable properties (no reference in `NameNode.java`), so a change needs a **NameNode restart**.
- Related keys (not the primary knob): `dfs.namenode.resource.check.interval` (poll period, default 5000 ms, `DFSConfigKeys.java:1241-1242`, `hdfs-default.xml:1065-1075`); `dfs.namenode.resource.checked.volumes` (extra directories checked, all "required", `DFSConfigKeys.java:1245`); `dfs.namenode.resource.checked.volumes.minimum` (minimum number of redundant volumes that must be above the floor, default 1, `DFSConfigKeys.java:1246-1247`); `dfs.namenode.edits.dir` (default `${dfs.namenode.name.dir}`, `hdfs-default.xml:493-499`) and `dfs.namenode.edits.dir.required` (`hdfs-default.xml:503-509`), which decide which volumes are checked and whether each is required or redundant.

**A2. What it caps.** Local disk on the NameNode's metadata volumes: the filesystem of each local (`file:` scheme) edits directory, de-duplicated per filesystem, plus every `dfs.namenode.resource.checked.volumes` directory (`NameNodeResourceChecker.java:115-138`, `NNStorage.java:72`). The quantity compared is `DF.getAvailable()` = `File.getUsableSpace()` of the directory (`DF.java:95-97`), read live on every check (not cached by `fs.df.interval`). The limit is a **floor on free space**: a volume is "available" while usable bytes ≥ `duReserved`. The NameNode-owned consumer that the floor stops is the edit log (growth of `edits_inprogress_*`, new segments) and, by stopping mutations, the size of future fsimage checkpoints. Read as a cap: NameNode usage on the volume is held at about `filesystem usable size − duReserved − (other consumers' usage)`.

**A3. Mechanism.**
1. Constructor (`NameNodeResourceChecker.java:108-143`): reads `duReserved` (112-113); collects local edits dirs from `FSNamesystem.getNamespaceEditsDirs(conf)` filtered to `file:` URIs (118-125); adds each with `required = getRequiredNamespaceEditsDirs(conf).contains(dir)` (129-133; the required set is `dfs.namenode.edits.dir.required` ∪ shared edits dirs, `FSNamesystem.java:1679-1684`); adds every extra checked volume as required (136-138). One `CheckedVolume` per filesystem, keyed by `df.getFilesystem()` (`NameNodeResourceChecker.java:64-69`, 154-166); a required entry is never downgraded (163).
2. The check: `CheckedVolume.isResourceAvailable()` reads `availableSpace = df.getAvailable()` (82) and evaluates [`if (availableSpace < duReserved)`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/NameNodeResourceChecker.java#L87). True → WARN "Space available on volume '…' is …, which is below the configured reserved amount …" and `return false` (88-91); false → `return true` (92-93). Equality counts as available.
3. Policy: `NameNodeResourcePolicy.areResourcesAvailable` (`NameNodeResourcePolicy.java:46-90`): empty set → true (54-56); any required volume unavailable → false (68-72); no redundant volumes → true if any required exist (76-79); otherwise available iff `redundant − disabledRedundant ≥ minimumRedundantVolumes` (81-88). With the default single, non-required edits dir and minimum 1, one volume under the floor → false.
4. `hasAvailableDiskSpace()` (`NameNodeResourceChecker.java:176-179`) is called from `FSNamesystem.checkAvailableResources()` (`FSNamesystem.java:4513-4520`), which caches the result in `volatile hasResourcesAvailable` (`FSNamesystem.java:599`).
5. Enforcement loop: `NameNodeResourceMonitor.run()` (`FSNamesystem.java:4541-4571`), a daemon started only in `startActiveServices` (`FSNamesystem.java:1453-1455`, comment "ResourceMonitor required only at ActiveNN. See HDFS-2914"). Each iteration: `checkAvailableResources()`; if unavailable → WARN "NameNode low on available disk space. Entering safe mode." and `enterSafeMode(true)` (4548-4555); else, if only resource-low safe mode is on, `leaveSafeMode(false)` (4557-4560); then `Thread.sleep(resourceRecheckInterval)` (4563; interval read at `FSNamesystem.java:883-885`).
6. `enterSafeMode(true)` (`FSNamesystem.java:5225-5245`): stops the secret manager, `logSyncAll()` to flush pending edits, sets `resourceLowSafeMode = true` (5241; setter 5306-5310).
7. Effect: `isInSafeMode()` is true (`FSNamesystem.java:5212-5214`); `checkNameNodeSafeMode` throws `SafeModeException` (`FSNamesystem.java:1645-1657`) on the mutating paths — e.g. create (`FSNamesystem.java:2771`), mkdirs (`FSNamesystem.java:3530`), addBlock (`FSDirWriteFileOp.java:603`), rollEditLog (`FSNamesystem.java:5313`); 65 call sites in `FSNamesystem.java`. No new edit records → the in-progress edit segment stops growing.
8. Recovery: when usable ≥ reserved again, the next iteration leaves safe mode automatically (unless manual safe mode is also on). A manual `hdfs dfsadmin -safemode leave` while still under the floor is undone at the next poll (tip text `FSNamesystem.java:5272-5276`).
9. HA: `NameNode.monitorHealth()` (`NameNode.java:1981-2003`) also calls `checkAvailableResources()` and reports UNHEALTHY to ZKFC when unavailable (1995-1997), driving failover.

Bypasses and overshoot:
- **Polling lag:** between checks (default 5 s) mutations continue; overshoot ≈ op rate × bytes per edit × interval, plus whatever is in flight when `logSyncAll` runs.
- **Preallocation:** `EditLogFileOutputStream.preallocate()` (`EditLogFileOutputStream.java:225-245`) extends the in-progress file in `MIN_PREALLOCATION_LENGTH` = 1 MiB chunks (`EditLogFileOutputStream.java:47`), so free space falls in 1 MiB steps; one step can cross the floor by up to 1 MiB.
- **`saveNamespace`** requires safe mode (`FSNamesystem.java:5058-5060`) and writes a full fsimage into the name dirs even in resource-low safe mode — an admin-initiated write below the floor.
- **Non-active NameNode:** the monitor runs only on the active (`FSNamesystem.java:1454`); a standby's checkpoint writes to its own name dirs are not held by this floor.
- **Unchecked locations:** fsimage-only name dirs on a filesystem with no edits dir, `HADOOP_LOG_DIR` (NameNode and audit logs), `hadoop.tmp.dir` — not checked unless listed in `dfs.namenode.resource.checked.volumes`.
- **Startup:** `startCommonServices` computes the flag (`FSNamesystem.java:1344-1345`) but safe-mode entry happens only after the monitor starts in `startActiveServices`; a NameNode started under the floor becomes active and enters safe mode at the first poll.
- **Disk full anyway:** if another process fills the volume faster than the poll, edit-log writes fail (journal failure), which is outside this check.

**A4. Other consumers.** The floor compares free space of the whole filesystem, so it counts everything on it: DataNode block files if `dfs.datanode.data.dir` shares the volume, NameNode/DataNode logs and the audit log if `HADOOP_LOG_DIR` shares it, `hadoop.tmp.dir`, SecondaryNameNode/standby checkpoint uploads into the name dir (fsimage files received through the image servlet), other users' files. None of these is throttled by the check; only the NameNode's namespace mutations are stopped. DataNode volumes have their own reserve (`dfs.datanode.du.reserved`), unrelated to this key.

**A5. Evidence beyond the source.**
- `hdfs-default.xml:1065-1102`, descriptions of the four `dfs.namenode.resource.*` keys.
- Tests: `TestNameNodeResourceChecker` (reserved 0 → available, lines 61-70; `Long.MAX_VALUE` → unavailable, 76-85; a mocked checker drives the NN into and out of safe mode through the monitor, 90-146); `TestNameNodeResourcePolicy`.
- In-code reference HDFS-2914 (`FSNamesystem.java:1453`): https://issues.apache.org/jira/browse/HDFS-2914 (resource monitor only on the active NN).
- Feature origin: HDFS-1594 ("When the disk becomes full Namenode is getting shutdown and not able to recover"), https://issues.apache.org/jira/browse/HDFS-1594 — introduced the NameNode resource checker and low-resource safe mode.
- `HdfsUserGuide.md:277` describes safe mode as read-only for the namespace.

## B. Verification solution

**B1. Claim under test.** On the active NameNode, once usable space on a checked edits volume drops below `dfs.namenode.resource.du.reserved`, the NameNode enters safe mode within one check interval and its edit-log usage on that volume stops growing (namespace mutations fail with `SafeModeException`), so the volume's free space is held at the floor (undershoot at most one interval's edits plus one 1 MiB preallocation chunk); with the floor set below the reachable range (reserved = 0) the same workload keeps growing the edit log. The claim is wrong if NameNode usage keeps growing well past the floor, or if safe mode is not entered while usable < reserved.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 8, Maven 3.3+. Copy the tree to local disk; never build in a shared tree: `rsync -a ~/hadoop-3.4.2/ $RUN/src/` (`$RUN` = a run directory on local disk, e.g. `/mydata/<person>-s4/o38`). Build: `cd $RUN/src && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`. Test source: new file `$RUN/src/hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestNNDuReservedBoundary.java` (same package, so it can use the package-private `CheckedVolume` and the public `FSNamesystem.setNNResourceChecker`, `FSNamesystem.java:7128`). Test volume `$UTVOL`: preferably a dedicated loop-mounted ext4 image (`truncate -s 1G $RUN/ut.img; mkfs.ext4 -F -m 0 $RUN/ut.img; mkdir -p $RUN/utvol; sudo mount -o loop $RUN/ut.img $RUN/utvol; sudo chown $USER $RUN/utvol`) so no other writer moves its free space; without sudo, a directory `$RUN/utvol` on local disk with the relative thresholds below and the noise guard of B2h. The test reads the base path from `System.getProperty("nnres.base")`, falling back to `System.getenv("NNRES_BASE")`. Default surefire JVM options suffice (MiniDFSCluster with one DataNode).

**B2b. Knobs.** `dfs.namenode.resource.du.reserved`, set in the test's `Configuration` (`conf.setLong(DFSConfigKeys.DFS_NAMENODE_DU_RESERVED_KEY, R)`), relative to the usable space `U` measured at runtime so the boundary is placed exactly on any disk:
- Checker test: R ∈ {0, U0 − 64 MiB, U0 + 64 MiB, `Long.MAX_VALUE`} — clearly available, available with headroom, already under, never available.
- Monitor test: R = U1 − D with D = 32 MiB (headroom, sysprop `nnres.delta.mb`), installed with `setNNResourceChecker`; control R = 0. `dfs.namenode.resource.check.interval` = 200 ms in both runs, so polling lag is small and the overshoot bound is tight.

**B2c. Workload.**
- Checker test: a 128 MiB filler file written (then `FileChannel.force(true)`) under `$UTVOL`, then deleted; 128 MiB > the 64 MiB headroom, so it crosses R = U0 − 64 MiB.
- Monitor test: first a filler of D − 8 MiB = 24 MiB on `$UTVOL` (outside the name dir) to bring free space close to the floor; then namespace mutations through the client: `fs.mkdirs(new Path("/t/d" + (i / 1000) + "/" + i))` for i = 0..N_max (N_max = 2,000,000), each logging one `OP_MKDIR` edit. Arithmetic: remaining headroom ≈ 8 MiB; with b bytes of edit log per mkdir (calibrated in B2e step 3 as Δ(edit bytes)/Δ(txid) over 20,000 ops), the floor is reached after ≈ 8 MiB / b ops, far below N_max for any b ≥ 5 B. The control (R = 0) runs 1.5 × the tripped run's op count; if b × that count would exceed U1 − 24 MiB − 64 MiB, cap it there.

**B2d. Observables and instruments.** Sampled in the test thread every 5,000 ops and every 200 ms in the post-trip phase, written as CSV to `$RUN/ut-<test>.csv`:
- `U` = `new File(base).getUsableSpace()` — identical to the checker operand `DF.getAvailable()` (`DF.java:95-97`).
- `avail` = `hasAvailableDiskSpace()` of a probe `NameNodeResourceChecker(conf2)` built with the same configuration (same operand and floor as the installed one).
- `E` = sum of the lengths of `edits_*` files in `<dir>/current` for each URI in `cluster.getNameEditsDirs(0)` (`MiniDFSCluster.java:2801`); preallocation extends the file length, so length tracks allocated edit-log bytes.
- `txid` = `fsn.getLastWrittenTransactionId()` (`FSNamesystem.java:4779`).
- `safe` = `fsn.isInSafeMode()`, and the time and op index of the first `SafeModeException` (unwrapped from `RemoteException`).
- NameNode log lines "Space available on volume" (`NameNodeResourceChecker.java:88`) and "NameNode low on available disk space" (`FSNamesystem.java:4549`) in surefire output.
Not directly observable: the exact instant the monitor thread ran; it is bracketed by the 200 ms interval.

**B2e. Procedure.**
1. Build as in B2a; create `$UTVOL`; record `df -B1 $RUN/utvol`.
2. `checkerOperand` test: `conf.set(DFS_NAMENODE_EDITS_DIR_KEY, base + "/n1")` (directory created first); for each R of B2b build a `NameNodeResourceChecker` and record (R, U, `hasAvailableDiskSpace()`). Then with R = U0 − 64 MiB: record; write the 128 MiB filler; record; delete it; record.
3. `monitorStopsEditGrowth` test: `conf.set(MiniDFSCluster.HDFS_MINIDFS_BASEDIR, base + "/cluster")` (puts the managed name/edits dirs on `$UTVOL`), `DFS_NAMENODE_RESOURCE_CHECK_INTERVAL_KEY = 200`, R = 0; `new MiniDFSCluster.Builder(conf).numDataNodes(1).build(); cluster.waitActive()`. Calibrate with 20,000 mkdirs (→ b). Measure U1; `conf2 = new Configuration(conf)` with R = U1 − D; `fsn.setNNResourceChecker(new NameNodeResourceChecker(conf2))`. Write the 24 MiB filler. Run the mkdirs loop with sampling until the first `SafeModeException` (record ops_trip, U, E, txid) or N_max.
4. Post-trip: for 30 s keep calling `mkdirs` every 200 ms; every call must fail; sample U, E, txid.
5. Recovery: delete the filler; poll `fsn.isInSafeMode()` every 100 ms for up to 5 s; then one `mkdirs` must succeed.
6. Control: repeat step 3 in a fresh cluster (fresh base subdir) keeping R = 0 (no checker swap), same filler, for 1.5 × ops_trip ops; sample identically.
7. Run: `cd $RUN/src && mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestNNDuReservedBoundary -Dnnres.base=$RUN/utvol -Dnnres.delta.mb=32 2>&1 | tee $RUN/ut.log`. Each test shuts its cluster down and deletes its filler in `finally`.

**B2f. Predictions.**
- Checker: R = 0 → true; R = U0 − 64 MiB → true; R = U0 + 64 MiB → false; `Long.MAX_VALUE` → false; filler written → false (U < R); filler deleted → true.
- Monitor (R = U1 − 32 MiB): `safe` becomes true no later than one 200 ms poll after U first reads < R; the first `SafeModeException` comes no later than the first op issued after that poll. E growth from filler to trip ≈ 8 MiB, at most 8 MiB + 1 MiB (preallocation) + b × (ops per 200 ms). U at trip ∈ [R − 1 MiB − b × ops_per_200ms, R). After the trip, E, txid and U stay constant for 30 s (no NameNode writes). After the filler is deleted, `safe` is false within ≤ 2 polls and mkdirs succeeds.
- Control (R = 0): no `SafeModeException`; E grows linearly with ops (b per op, in 1 MiB steps) past the point where the tripped run stopped, ending at ≈ 1.5 × the tripped run's E growth.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Checker values as predicted; tripped run stops E growth within the bound; control keeps growing | Claim confirmed at unit level: the operand is the volume's usable space, and the floor halts edit growth |
| `hasAvailableDiskSpace()` stays true with U < R | Claim wrong: the check does not see the volume (wrong dir/filesystem mapping) |
| U < R but `safe` stays false for > 2 polls | Claim wrong: monitor not enforcing (or not running on this NN) |
| `safe` true but E or txid keeps growing past trip + 1 MiB | Claim wrong: mutations bypass resource-low safe mode |
| E growth at trip exceeds 8 MiB by far more than 1 MiB + b × ops_per_200ms | Floor enforced but with an overshoot larger than traced; report as partial |
| Control also trips, or control E does not grow | Workload or instrument broken: not confirmed; fix before reading the tripped run |
| U changes by > 2 MiB between samples without NameNode or filler writes | External writer on the volume: run invalid (repeat on a loop mount) |

**B2h. Controls.** The R = 0 control (same workload, same volume) shows usage moves when no floor binds. The checker-only test separates the operand (usable space) from the policy and the monitor. The recovery step shows the state follows U vs R, not a one-way failure. Noise guard: a background thread samples U every 200 ms; any change not explained by the filler or E (> 2 MiB) invalidates the run. Exact equality (U == R) is not reachable byte-exactly on a real filesystem; the strict `<` is taken from the source.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux host, pseudo-distributed: NameNode + one DataNode, each started with `hdfs --daemon start` (no SecondaryNameNode, so no checkpoint uploads into the name dir during the run; no YARN).
- Build: `cd $RUN/src && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true` (`BUILDING.txt:364-368`); `HADOOP_HOME=$RUN/src/hadoop-dist/target/hadoop-3.4.2` (or an existing distribution of the tag built on the node). `HADOOP_CONF_DIR=$RUN/conf` (copy of `$HADOOP_HOME/etc/hadoop`), `HADOOP_LOG_DIR=$RUN/logs`, `HADOOP_PID_DIR=$RUN/pids`, `HADOOP_HEAPSIZE_MAX=1g`, JDK 8 or 11.
- NameNode volume `$NNVOL`: a dedicated 512 MiB ext4 loop image: `truncate -s 512M $RUN/nn.img; mkfs.ext4 -F -m 0 $RUN/nn.img; mkdir -p $RUN/nnvol; sudo mount -o loop $RUN/nn.img $RUN/nnvol; sudo chown $USER $RUN/nnvol`. Without sudo: `$RUN/nnvol` on local disk with the relative thresholds of B3b and the noise guard of B3h.
- `core-site.xml`: `fs.defaultFS = hdfs://localhost:9000`; `hadoop.tmp.dir = $RUN/tmp`.
- `hdfs-site.xml`: `dfs.namenode.name.dir = file://$RUN/nnvol/name` (the edits dir defaults to it); `dfs.datanode.data.dir = file://$RUN/dn` (local disk, not on `$NNVOL`); `dfs.replication = 1`; `dfs.namenode.resource.check.interval = 1000` (1 s, to tighten the overshoot bound; one run uses the default 5000, B3b); `dfs.namenode.resource.du.reserved` per run (B3b); `dfs.namenode.fs-limits.min-block-size = 16` (required by NNThroughputBenchmark with `-fs`, per its usage text, `NNThroughputBenchmark.java:1557-1558`); `dfs.namenode.checkpoint.txns = 100000000` (keeps checkpoint-driven activity out of the run).
- Logs, pids, DataNode data and tmp all under `$RUN` on local disk.

**B3b. Knobs.** `dfs.namenode.resource.du.reserved` in `$RUN/conf/hdfs-site.xml`; NameNode restart per value (`hdfs --daemon stop namenode; hdfs --daemon start namenode`). After format and start, free space is `U1` (from `df`). A filler file sets free space to `U_f = 140 MiB` (`fallocate -l $((U1 − 140 MiB)) $RUN/nnvol/filler`, resized before each run). Values:
- R = 0 — control: the floor never binds within the workload.
- R = 100m — the default; floor 40 MiB below U_f.
- R = 130m — floor 10 MiB below U_f.
- R = 130m with `dfs.namenode.resource.check.interval = 5000` — default polling, to read the overshoot at the default interval.
- R = 200m with U_f = 140 MiB already in place at NameNode start — the floor is crossed before the NameNode starts (startup path).
Relative fallback without sudo: the same headrooms (40 MiB, 10 MiB) computed as R = U_now − headroom immediately before each restart, with no filler.

**B3c. Workload.** Namespace mutations through the client RPC path with NNThroughputBenchmark (in the distribution's `share/hadoop/hdfs/hadoop-hdfs-3.4.2-tests.jar`, added to `HADOOP_CLASSPATH`): `hadoop org.apache.hadoop.hdfs.server.namenode.NNThroughputBenchmark -fs hdfs://localhost:9000 -op mkdirs -threads 4 -dirs N -dirsPerDir 1000`. Fallback on the same client path: `for k in $(seq 1 M); do hdfs dfs -mkdir -p $(printf "/w/$k/d%d " $(seq 1 1000)); done` (1000 mkdirs per JVM). Calibration (B3e step 4) gives b = edit-log bytes per mkdir (Δ size of `name/current/edits_*` ÷ Δ `LastWrittenTransactionId`). Ops needed to reach the floor = headroom / b: 40 MiB / b for R = 100m, 10 MiB / b for R = 130m. Every run uses N = 1.5 × (40 MiB / b), so the workload is always 1.5 × what crossing the 100m floor needs, and in the control (R = 0) adds ≈ 60 MiB, which fits in U_f = 140 MiB (no disk-full risk). Duration: set by NameNode mkdir throughput; record wall time.

**B3d. Observables and instruments.** A sampler script, 1 s period, writing `$RUN/samples-<run>.csv`:
- `df -B1 --output=avail $RUN/nnvol` (the checker's operand; `getUsableSpace` corresponds to df "avail").
- `du -sb $RUN/nnvol/name/current` and `ls -l $RUN/nnvol/name/current/edits_inprogress_*` (NameNode edit-log bytes).
- `curl -s 'http://localhost:9870/jmx?qry=Hadoop:service=NameNode,name=FSNamesystemState'` → `FSState` (`safeMode`/`Operational`, `FSNamesystem.java:5635`); `...name=FSNamesystem` → `LastWrittenTransactionId`; `...name=NameNodeInfo` → `Safemode` tip text (`FSNamesystem.java:6594`, which contains "Resources are low on NN" for this cause).
- `hdfs dfsadmin -safemode get` every 5 s (cross-check).
- NameNode log `$RUN/logs/hadoop-*-namenode-*.log`: timestamps of "Space available on volume ... below the configured reserved amount", "NameNode low on available disk space. Entering safe mode." and "Namenode has sufficient available resources, exiting safe mode."
- Benchmark or loop output: first `SafeModeException` and the op count at that point.
Not directly observable: per-op edit size (only the average b) and the exact poll instant (bracketed by the interval).

**B3e. Procedure.**
1. Build or copy the distribution; write configs (B3a); create and mount `$NNVOL`; run `df -B1 $RUN/nnvol` and `jps` (no leftover Hadoop JVMs); check ports free (`ss -ltn`).
2. `hdfs namenode -format -nonInteractive`; `hdfs --daemon start namenode; hdfs --daemon start datanode`; wait until `hdfs dfsadmin -safemode get` reports OFF.
3. Read U1; create the filler to bring free space to U_f = 140 MiB; `sync`; confirm with `df`.
4. Calibrate with R = 0: start the sampler; run the benchmark with `-dirs 50000`; compute b. Leave the directories (deleting them is itself a mutation that writes edits); re-read U and resize the filler back to U_f = 140 MiB.
5. For each R of B3b (order: 0, 100m, 130m, 130m @ 5000 ms, 200m-at-start): stop the NameNode; set R (and the interval); for the startup run, establish U_f first; start the NameNode; wait for OFF (except the startup run); otherwise establish U_f = 140 MiB by resizing the filler; start the sampler; run the workload of N ops; keep sampling for 60 s after the workload ends or stops on `SafeModeException`; in that minute try `hdfs dfs -mkdir /probe-<run>-<n>` every 10 s.
6. Recovery (R = 100m and 130m runs): first, a manual-leave probe once: `hdfs dfsadmin -safemode leave`, then read FSState for 3 intervals. Then `truncate -s 0 $RUN/nnvol/filler`; within ≤ 2 intervals FSState returns to `Operational` and `hdfs dfs -mkdir /after-<run>` succeeds.
7. Optional bypass probe (once, at R = 100m, while tripped and before freeing): `hdfs dfsadmin -saveNamespace` while sampling `df`/`du` — measures the documented bypass (`FSNamesystem.java:5058-5060`).
8. Cleanup (B4).

**B3f. Predictions.** ΔE = edit-log growth after the filler is in place; U = df avail.
- R = 0: no safe mode; ΔE ≈ b × N ≈ 60 MiB (in 1 MiB steps); U falls to ≈ 80 MiB.
- R = 100m: FSState `safeMode` within ≤ 1 s after U < 100 MiB; ΔE ≈ 40 MiB, excess ≤ 1 MiB + b × (ops/s × 1 s); afterwards U, ΔE and `LastWrittenTransactionId` flat for 60 s; the workload fails with `SafeModeException`; final U ∈ [100 MiB − 1 MiB − b × ops/s, 100 MiB).
- R = 130m: same, with ΔE ≈ 10 MiB; final U just under 130 MiB.
- R = 130m @ 5000 ms: ΔE ≈ 10 MiB with excess ≤ 1 MiB + b × (ops/s × 5 s), i.e. larger than in the 1 s run by about 4 s of ops.
- R = 200m at start (U = 140 MiB < 200 MiB): FSState `safeMode` within one interval of the NameNode becoming active; the first mkdir fails; ΔE ≈ 0.
- Across runs: ΔE(R=0) > ΔE(100m) > ΔE(130m); the stop point tracks R (final U ≈ min(R, U_f − b × N)).
- After freeing: `Operational` within ≤ 2 intervals. Manual leave while under the floor: `safeMode` again within one interval. saveNamespace (optional): U drops below the floor by about the new fsimage file size.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Stop point of ΔE / U follows R (100m vs 130m); control grows past both | Claim confirmed: the key caps NameNode edit-log disk usage on the volume |
| U < R for > 2 intervals while FSState is `Operational` | Claim wrong: floor not enforced (check the log for the WARN line; if absent, the volume is not checked) |
| FSState `safeMode` but `LastWrittenTransactionId` / ΔE keep rising beyond 1 MiB | Claim wrong: mutations bypass resource-low safe mode |
| Overshoot at 5000 ms ≈ overshoot at 1000 ms, both ≫ 1 MiB + b × ops/s × interval | Mechanism differs from the traced poll; report as partial |
| Control (R = 0) does not grow, or trips | Workload or measurement broken: not confirmed |
| Startup run does not enter safe mode while U < R | Claim wrong for the startup path |
| Manual leave under the floor stays off | Floor can be overridden indefinitely: partial |
| saveNamespace lowers U below R | Expected bypass (admin action), consistent with A3, not a refutation |
| df avail moves with no NameNode activity (no-sudo mode) | External writer: run invalid |

**B3h. Controls.** The R = 0 control with the same filler and workload shows usage moves when no floor binds. Two non-zero floors (100m, 130m) show the stop point follows the knob, not a fixed disk-full or benchmark limit. The 5000 ms run separates the poll lag from the floor. Recovery and manual-leave probes show the state follows U vs R. DataNode data, logs and tmp are off `$NNVOL`, and no SecondaryNameNode runs, so the only writers on `$NNVOL` are the NameNode and the filler. In no-sudo mode the sampler's df series is checked for unexplained changes.

**B4. Risks and cleanup.**
- Disk: all data under `$RUN` on local disk; the loop images (1 GiB unit, 512 MiB cluster) cannot grow; the control workload leaves ≥ 80 MiB free on `$NNVOL`, so the NameNode never hits disk full (which would fail its only journal). In no-sudo mode never let the real filesystem go below 1 GiB free; stop if `df` shows less.
- Shared storage: nothing under `/proj` or any NFS path; the source copy is built under `$RUN/src` only.
- Ports: 9000, 9870, 9864/9866/9867 on localhost; if busy, choose others in `core-site.xml`/`hdfs-site.xml`. MiniDFSCluster uses ephemeral ports.
- Cleanup: `hdfs --daemon stop datanode; hdfs --daemon stop namenode`; `jps` must list no `NameNode`, `DataNode`, `NNThroughputBenchmark`, surefire or Maven JVMs; stop the sampler; `sudo umount $RUN/nnvol $RUN/utvol`; remove `$RUN/*.img`, `$RUN/tmp`, `$RUN/dn`, `$RUN/nnvol`, `$RUN/utvol`; keep `$RUN/samples-*.csv`, `$RUN/ut*.csv`, logs and configs as results.

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/NameNodeResourceChecker.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/NameNodeResourcePolicy.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSNamesystem.java (599, 883-885, 1340-1350, 1390, 1445-1460, 1645-1660, 1679-1745, 2771, 3530, 4500-4575, 4779, 5050-5075, 5205-5320, 5635, 6594, 7128)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/NameNode.java (1981-2003)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/EditLogFileOutputStream.java (47, 220-245)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirWriteFileOp.java (603)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/NNStorage.java (72)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/metrics/NameNodeMetrics.java (450)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/metrics/FSNamesystemMBean.java (45)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java (686-693, 1241-1247)
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml (441-447, 493-509, 1065-1102, 1354-1368)
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/DF.java (49-97)
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/conf/Configuration.java (1624-1627)
- hadoop-common-project/hadoop-common/src/main/resources/core-default.xml (1355-1358)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestNameNodeResourceChecker.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/NNThroughputBenchmark.java (109-110, 654-713, 1541-1560)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/MiniDFSCluster.java (166-169, 2801)
- hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/HdfsUserGuide.md (277)
- https://issues.apache.org/jira/browse/HDFS-2914
- https://issues.apache.org/jira/browse/HDFS-1594

## D. Stage-4 feedback

none yet
