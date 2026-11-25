# dfs.namenode.snapshot.filesystem.limit — verification solution  <!-- file: cases/dfs.namenode.snapshot.filesystem.limit-checkSnapshotLimit-limit--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`SnapshotManager.java:483`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/SnapshotManager.java#L483) `if (snapshotCount >= limit)` in `checkSnapshotLimit(int limit, int snapshotCount, String type)`. This is a shared helper. The file-system-wide caller is `checkFileSystemSnapshotLimit` (`SnapshotManager.java:473-475`, called from `createSnapshot` at `:464`). The per-directory caller is `checkPerDirectorySnapshotLimit` (`SnapshotManager.java:477-479`, called from `DirectorySnapshottableFeature.addSnapshot` at `DirectorySnapshottableFeature.java:193`). |
| Pinned source | `rel/release-3.4.2` |
| Session / date | stage-3 autonomous agent, 2026-11-24 |
| Estimate | `positive`. The NameNode checks the live snapshot count against the limit before it allocates anything for a new snapshot, and it rejects the create once the count reaches the limit. Snapshot objects, per-snapshot diff layers and their fsimage records are the NameNode heap and disk that grow with the snapshot count, and they stop growing at the limit. Caveats: the check only logs, and does not enforce, while the image or edits are loading, so a NameNode restarted with a lower limit keeps every existing snapshot. The limit also does not cap diffs or retained blocks that pile up inside snapshots that already exist. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `dfs.namenode.snapshot.filesystem.limit`. This is a configuration key.
- **Declaration:** [`DFSConfigKeys.java:551-555`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java#L551-L555). The constant `DFS_NAMENODE_SNAPSHOT_FILESYSTEM_LIMIT` holds the key, and `DFS_NAMENODE_SNAPSHOT_FILESYSTEM_LIMIT_DEFAULT = 65536` is the default.
- **`hdfs-default.xml` entry:** `hdfs-default.xml:5535-5543`, value `65536`, "Limits the maximum number of snapshots allowed on the entire filesystem."
- **Unit:** a count of snapshots that exist at the same time, across all snapshottable directories.
- **Default:** 65536. The Java constant and the XML value agree, so neither wins over the other.
- **How to set it:** in `hdfs-site.xml` on the NameNode. The value is read once in the `SnapshotManager` constructor (`SnapshotManager.java:160-162`) and kept in the `final` field `maxSnapshotFSLimit` (`:136`). The key is not reconfigurable, so a change needs a NameNode restart.
- **Who reads it:** the NameNode, both active and standby. Every NameNode builds a `SnapshotManager`.

The same helper and the same `limit` operand are also fed by a second key, `dfs.namenode.snapshot.max.limit` ([`DFSConfigKeys.java:547-549`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java#L547-L549), default 65536, `hdfs-default.xml:5526-5534`):
- It is the per-snapshottable-directory limit, read into `maxSnapshotLimit` at `SnapshotManager.java:155-159`.
- Startup refuses `max.limit > filesystem.limit` with a `SnapshotException` (`SnapshotManager.java:185-191`).

I chose the file-system key as the primary constraint for these reasons:
- It is checked first, in `createSnapshot` (`:464`), before the per-directory check (`DirectorySnapshottableFeature.java:193`).
- It bounds the NameNode-wide total.
- Its JIRA, HDFS-15497, states the memory concern: too many snapshots "bloat up the namespace".

The per-directory key is tested as a secondary arm (runs T3 and D below).

Two related limits are hard-coded:
- A per-directory snapshot quota, `SNAPSHOT_QUOTA_DEFAULT = 1 << 16` (`DirectorySnapshottableFeature.java:62`), checked at `:188`. It is not settable by a user; `SnapshotManager.java:256` sets it at allowSnapshot.
- The snapshot-ID space `(1 << 28) - 1` (`SnapshotManager.java:130`, `:763-765`), checked at `:454`.

**A2. What it caps.**
- **Quantity compared:** `snapshotCount` is `numSnapshots.get()`, the NameNode-wide count of live snapshots (`SnapshotManager.java:463`). It is compared against `maxSnapshotFSLimit`. For the per-directory arm, the count is `getNumSnapshots()` of that directory (`DirectorySnapshottableFeature.java:187`).
- **Resource behind it: NameNode heap.** Each snapshot allocates the following, and none of it is shared or freed until the snapshot is deleted:
  - a `Snapshot` and a `Snapshot.Root` (an `INodeDirectory` copy, `Snapshot.java:162-180`, `:239-248`);
  - a `DirectoryDiff` in the root's diff list (`DirectorySnapshottableFeature.java:202`);
  - an entry in `snapshotsByNames` (`:204`);
  - for every file or directory modified afterwards, at most one extra diff with a snapshot copy of its attributes per snapshot. A new diff is added only when the latest snapshot ID is newer than the last diff (`AbstractINodeDiffList.java:306-324`).
- **Resource behind it: NameNode disk.** The same structures are serialized into the fsimage snapshot sections (`FSImageFormatPBSnapshot.java:438-439`).
- **Indirect effect only:** retained DataNode blocks are not tied to the snapshot count (see A4).

**A3. Mechanism.**
1. **Client call.** The client calls `createSnapshot` over RPC or WebHDFS. `NameNodeRpcServer.createSnapshot` bumps `CreateSnapshotOps` before the attempt, so the counter counts attempts (`NameNodeRpcServer.java:1947`). Then `FSNamesystem.createSnapshot` takes the write lock (`FSNamesystem.java:7175-7190`), and `FSDirSnapshotOp.createSnapshot` (`FSDirSnapshotOp.java:97-123`) calls `SnapshotManager.createSnapshot` (`SnapshotManager.java:448`).
2. **ID-space check.** `createSnapshot` checks the ID space first (`:454-462`).
3. **File-system check.** `createSnapshot` reads `n = numSnapshots.get()` (`:463`) and calls `checkFileSystemSnapshotLimit(n)` (`:464`), which calls `checkSnapshotLimit(maxSnapshotFSLimit, n, "file system")` (`:474`).
4. **The check:** [`if (snapshotCount >= limit)`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/SnapshotManager.java#L483). Because `n` is the count before the add and the test is `>=`, the maximum reachable count is exactly `limit`.
   - **Image loaded** (`isImageLoaded()`, `:487`, which is `FSNamesystem.imageLoaded`): it throws `SnapshotException("Failed to create snapshot: there are already N snapshot(s) and the file system snapshot limit is L")` (`:489-490`). Nothing has been allocated yet; `addSnapshot` and the counter increment at `:465-469` are skipped. No edit is logged, because the exception propagates out of `FSDirSnapshotOp.createSnapshot` before `logCreateSnapshot` (`FSDirSnapshotOp.java:124`). Over WebHDFS, the `IOException` maps to HTTP 403 (`web/resources/ExceptionHandler.java:106-107`).
   - **Image not loaded** (fsimage or edit-log replay at startup): it only runs `LOG.error(msg)` (`:491-494`) and the create goes ahead.
5. **Per-directory check.** If the file-system check passes, `srcRoot.addSnapshot` runs `DirectorySnapshottableFeature.addSnapshot`:
   - It checks the hard-coded quota (`:188`).
   - It calls `checkPerDirectorySnapshotLimit(n_dir)` (`:193`), which reaches the same line 483 with `maxSnapshotLimit` and the text "per directory".
   - Only then does it allocate the `Snapshot` (`:194`) and the `DirectoryDiff` (`:202`).
6. **Counters on success.** `snapshotCounter++` and `numSnapshots++` (`SnapshotManager.java:468-469`).
7. **Deletion.** Deletion decrements `numSnapshots` (`:547`), with one exception. With `dfs.namenode.snapshot.deletion.ordered=true`, deleting a snapshot that is not the oldest only marks and renames it and returns before the decrement (`:511-541`). Such snapshots keep counting until the GC removes them.

**Bypasses and overshoots:**
- **(a) fsimage load.** Loading the fsimage sets `numSnapshots` directly (`FSImageFormatPBSnapshot.java:151`) with no limit check.
- **(b) Edit-log replay at startup.** `FSEditLogLoader.java:798-806` calls `createSnapshot` while `imageLoaded` is false, so the check only logs. HDFS-15568 made it work this way, because a NameNode with a lowered limit used to fail to start. As a result, lowering either limit and restarting leaves the NameNode holding more snapshots than the limit (`TestSnapshotManager.java:141-198` asserts this). New creates still fail.
- **(c) Standby NameNode (hypothesis, not tested here).** A standby has `imageLoaded = true` while it tails edits. If its configured limit is lower than the active's, the replay of `OP_CREATE_SNAPSHOT` would throw instead of logging.
- **(d) Modifications inside existing snapshots.** These keep adding diffs and retaining deleted children and blocks after the limit is reached; the count limit does not cover them.

**A4. Other consumers.** These use the same NameNode heap or disk but are outside this constraint:
- the namespace itself (inodes and blocks);
- diffs created by renames and deletes inside existing snapshots, which are bounded only by churn;
- the number of snapshottable directories, which has no limit (`HdfsSnapshots.md:58`);
- snapshot diff reports (`dfs.namenode.snapshotdiff.listing.limit`, `DFSConfigKeys.java:541-545`);
- the retry cache;
- edit-log growth;
- DataNode disk held by blocks of files deleted or overwritten after a snapshot, which depends on data volume rather than snapshot count.

**A5. Evidence beyond the source.**
- [HDFS-15497](https://issues.apache.org/jira/browse/HDFS-15497) (fix 3.4.0) introduced both configurable limits: "Too many snapshots in the system can potentially bloat up the namespace".
- [HDFS-12947](https://issues.apache.org/jira/browse/HDFS-12947) is the earlier per-directory limit work: many snapshots make deletion expensive.
- [HDFS-15568](https://issues.apache.org/jira/browse/HDFS-15568) reports a NameNode that failed to start with `max.limit` set; it is the origin of the log-only branch during load.
- `HdfsSnapshots.md:32-44`: "Additional memory is used only when modifications are made relative to a snapshot: memory usage is O(M)".
- `TestSnapshotManager.java:64-127` covers the limit with mocks, and `:141-198` covers the restart overshoot.

## B. Verification solution

**B1. Claim under test.** On a running NameNode, once the live snapshot count reaches `dfs.namenode.snapshot.filesystem.limit` = L, every further `createSnapshot` fails with "file system snapshot limit is L". From then on, the NameNode heap and fsimage bytes that grow with the snapshot count stay flat while the same create-and-modify workload continues. With the default 65536 (not binding), the same workload keeps growing them linearly. Secondary arm: the same holds per directory for `dfs.namenode.snapshot.max.limit`. Expected exception, not part of the claim: after a restart with a lower limit, the count stays above the limit.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 8, Maven 3.3+.
- Copy the tree to local disk: `rsync -a ~/hadoop-3.4.2/ $WORK/hadoop-src/`, where `$WORK` is a local-disk directory such as `/mydata/<user>-s4/<case>`.
- Build: `cd $WORK/hadoop-src && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
- The test goes in `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/snapshot/TestSnapshotLimitUsage.java`. It uses the same package, so it can reach package-private members.
- The default surefire JVM options are enough. MiniDFSCluster data goes under the module's `target/test/data`, which is on local disk.

**B2b. Knobs.** All set through `Configuration` before `MiniDFSCluster` starts:

| Test | `filesystem.limit` | `max.limit` | Why |
|---|---|---|---|
| T1 | 40 | 40 | File-system arm. `max.limit` must be ≤ the file-system limit (`SnapshotManager.java:185`), and each directory only gets 20 attempts, so the per-directory check never binds. |
| T2 | unset (65536) | unset (65536) | Control: the limit does not bind. |
| T3 | unset | 8 | Per-directory arm. |
| T4 | 40/40, then 20/5 | (in the same pair) | After T1, the limits are lowered to 20 / 5 and the NameNode is restarted (overshoot arm). |

The retry cache is off (`dfs.namenode.enable.retrycache=false`) in all tests, to remove unrelated heap.

**B2c. Workload.**
- Setup: 4 snapshottable directories `/t/d0..d3`, each with 50 empty files (no blocks).
- 20 rounds. Each round:
  - for each directory, `createSnapshot(dir, "s<r>")`;
  - then `setPermission` on all 200 files, alternating 0600 and 0644. Each permission change records one `FileDiff` per file for that directory's newest snapshot (`AbstractINodeDiffList.java:314-324`).
- That is 80 create attempts in total.
- Arithmetic for T1: the limit of 40 is reached after 10 rounds (attempt 40), and attempts 41-80 must fail.

**B2d. Observables and instruments.** All read in-JVM:
- `SnapshotManager.getNumSnapshots()`, the check's own operand `snapshotCount`. It is sampled after every attempt (maximum kept) and after every round.
- Count of successful creates and failed creates, the index of the first failure and its message.
- Total `FileDiff` count: the sum over files of `INodeFile.getDiffs().asList().size()`. This is the heap layer that grows with the snapshot count.

Bytes are not measured in this tier, because the test JVM heap holds the client and DataNode too. Bytes are measured in B3.

**B2e. Procedure.**

1. Add the test below.

```java
package org.apache.hadoop.hdfs.server.namenode.snapshot;

import java.util.ArrayList;
import java.util.List;
import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.fs.permission.FsPermission;
import org.apache.hadoop.hdfs.DFSConfigKeys;
import org.apache.hadoop.hdfs.DistributedFileSystem;
import org.apache.hadoop.hdfs.HdfsConfiguration;
import org.apache.hadoop.hdfs.MiniDFSCluster;
import org.apache.hadoop.hdfs.protocol.SnapshotException;
import org.apache.hadoop.hdfs.server.namenode.FSDirectory;
import org.apache.hadoop.hdfs.server.namenode.INodeFile;
import org.junit.Test;

public class TestSnapshotLimitUsage {
  static final int DIRS = 4, FILES = 50, ROUNDS = 20, UNSET = -1;

  static final class Run {
    int ok, failed, maxNum, firstFailAttempt = -1; long fileDiffs; String firstMsg;
    final List<Integer> perRound = new ArrayList<>();
    @Override public String toString() {
      return "ok=" + ok + " failed=" + failed + " maxNumSnapshots=" + maxNum
          + " firstFailAttempt=" + firstFailAttempt + " fileDiffs=" + fileDiffs
          + " perRound=" + perRound + " firstMsg=" + firstMsg;
    }
  }

  static MiniDFSCluster start(int fsLimit, int dirLimit) throws Exception {
    Configuration conf = new HdfsConfiguration();
    if (fsLimit != UNSET) conf.setInt(DFSConfigKeys.DFS_NAMENODE_SNAPSHOT_FILESYSTEM_LIMIT, fsLimit);
    if (dirLimit != UNSET) conf.setInt(DFSConfigKeys.DFS_NAMENODE_SNAPSHOT_MAX_LIMIT, dirLimit);
    conf.setBoolean(DFSConfigKeys.DFS_NAMENODE_ENABLE_RETRY_CACHE_KEY, false);
    MiniDFSCluster c = new MiniDFSCluster.Builder(conf).numDataNodes(1).build();
    c.waitActive();
    DistributedFileSystem fs = c.getFileSystem();
    for (int d = 0; d < DIRS; d++) {
      Path dir = new Path("/t/d" + d);
      fs.mkdirs(dir);
      for (int f = 0; f < FILES; f++) fs.create(new Path(dir, "f" + f)).close();
      fs.allowSnapshot(dir);
    }
    return c;
  }

  static long fileDiffs(MiniDFSCluster c) throws Exception {
    FSDirectory fsd = c.getNamesystem().getFSDirectory();
    long n = 0;
    for (int d = 0; d < DIRS; d++)
      for (int f = 0; f < FILES; f++) {
        INodeFile file = fsd.getINode("/t/d" + d + "/f" + f).asFile();
        FileDiffList l = file.getDiffs();
        n += (l == null) ? 0 : l.asList().size();
      }
    return n;
  }

  static Run drive(MiniDFSCluster c, int rounds) throws Exception {
    DistributedFileSystem fs = c.getFileSystem();
    SnapshotManager sm = c.getNamesystem().getSnapshotManager();
    Run run = new Run();
    int attempt = 0;
    for (int r = 0; r < rounds; r++) {
      for (int d = 0; d < DIRS; d++) {
        attempt++;
        try {
          fs.createSnapshot(new Path("/t/d" + d), "s" + r);
          run.ok++;
        } catch (SnapshotException e) {
          run.failed++;
          if (run.firstMsg == null) { run.firstMsg = e.getMessage(); run.firstFailAttempt = attempt; }
        }
        run.maxNum = Math.max(run.maxNum, sm.getNumSnapshots());
      }
      FsPermission p = new FsPermission((short) (r % 2 == 0 ? 0600 : 0644));
      for (int d = 0; d < DIRS; d++)
        for (int f = 0; f < FILES; f++) fs.setPermission(new Path("/t/d" + d + "/f" + f), p);
      run.perRound.add(sm.getNumSnapshots());
    }
    run.fileDiffs = fileDiffs(c);
    return run;
  }

  @Test(timeout = 900000) public void t1FsLimit() throws Exception {
    MiniDFSCluster c = start(40, 40);
    try { System.out.println("RESULT T1 " + drive(c, ROUNDS)); } finally { c.shutdown(); }
  }

  @Test(timeout = 900000) public void t2Control() throws Exception {
    MiniDFSCluster c = start(UNSET, UNSET);
    try { System.out.println("RESULT T2 " + drive(c, ROUNDS)); } finally { c.shutdown(); }
  }

  @Test(timeout = 900000) public void t3PerDirLimit() throws Exception {
    MiniDFSCluster c = start(UNSET, 8);
    try { System.out.println("RESULT T3 " + drive(c, ROUNDS)); } finally { c.shutdown(); }
  }

  @Test(timeout = 900000) public void t4RestartLowered() throws Exception {
    MiniDFSCluster c = start(40, 40);
    try {
      System.out.println("RESULT T4-before " + drive(c, ROUNDS));
      c.getNameNode().getConf().setInt(DFSConfigKeys.DFS_NAMENODE_SNAPSHOT_FILESYSTEM_LIMIT, 20);
      c.getNameNode().getConf().setInt(DFSConfigKeys.DFS_NAMENODE_SNAPSHOT_MAX_LIMIT, 5);
      c.restartNameNodes();
      c.waitActive();
      SnapshotManager sm = c.getNamesystem().getSnapshotManager();
      String msg = "none";
      try { c.getFileSystem().createSnapshot(new Path("/t/d0"), "after"); }
      catch (SnapshotException e) { msg = e.getMessage(); }
      System.out.println("RESULT T4-after numSnapshots=" + sm.getNumSnapshots()
          + " fsLimitNow=" + 20 + " fileDiffs=" + fileDiffs(c) + " createMsg=" + msg);
    } finally { c.shutdown(); }
  }
}
```

2. Run it: `cd $WORK/hadoop-src && mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestSnapshotLimitUsage 2>&1 | tee $WORK/unit.log`.
3. Read the results: `grep RESULT hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports/*TestSnapshotLimitUsage-output.txt`, or from `$WORK/unit.log`.
4. For T4, also check the NameNode ERROR lines written during the restart by the edit-replay branch (`SnapshotManager.java:493`). MiniDFSCluster runs no checkpointer, so the restart rebuilds all 40 snapshots by replaying `OP_CREATE_SNAPSHOT` from the empty format-time fsimage. The replayed count `n` runs 0..39, so expect `there are already N snapshot(s) and the file system snapshot limit is 20` for N = 20..39 (20 lines), and `the per directory snapshot limit is 5` for N = 5..9 in each of the 4 directories (20 lines). The text `already 40 snapshot(s) ... limit is 20` appears only in the message of the post-restart create (`createMsg`), not in the replay log.

**B2f. Predictions.**

| Test | ok | failed | maxNumSnapshots | firstFailAttempt | first message contains | perRound | fileDiffs |
|---|---|---|---|---|---|---|---|
| T1 (40/40) | 40 | 40 | 40 | 41 | `file system snapshot limit is 40` | 4, 8, …, 40 (rounds 0-9), then 40 for rounds 10-19 | 4 × 50 × 10 = 2000 |
| T2 (default) | 80 | 0 | 80 | -1 | (none) | 4, 8, …, 80 | 4 × 50 × 20 = 4000 |
| T3 (per dir 8) | 32 | 48 | 32 | 33 | `per directory snapshot limit is 8` | 4, …, 32 (rounds 0-7), then 32 | 4 × 50 × 8 = 1600 |
| T4-after (20/5) | — | — | numSnapshots = 40 (> 20) | — | `file system snapshot limit is 20` | — | 2000 (unchanged) |

In T1 and T3, `fileDiffs` stays at its value from the round where the limit binds, even though `setPermission` keeps running on all 200 files every round.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| T1 maxNumSnapshots = 40, failures start at attempt 41 with the file-system message, fileDiffs = 2000, while T2 reaches 80 and 4000 | Claim holds at the operand level: the count, and the diff layers that scale with it, stop at L. |
| T1 maxNumSnapshots > 40, or ok > 40 | Claim wrong: the check does not cap the count. |
| T1 fileDiffs > 2000 (for example 4000) with ok = 40 | Claim wrong about usage: diff layers grow past the limit without new snapshots. My trace (`AbstractINodeDiffList.java:306-311`) would be wrong. |
| T1 first failure message is "per directory" or "snapshot quota" | A different check bound. Re-check the knob values. |
| T2 does not reach 80 / 4000 | Control failed: the workload did not move usage, so T1 is not conclusive. |
| T3 = 32 / 1600 with the per-directory message | Secondary arm holds. |
| T4-after numSnapshots = 40 and the create fails with limit 20 | Expected overshoot on restart, as predicted in A3. It is not a refutation; it marks where the limit does not apply. |
| T4-after NameNode fails to start | Different from the source (HDFS-15568 behaviour); record it. |

**B2h. Controls.**
- T2 runs the same workload with the limit not binding.
- `setPermission` keeps running after the limit, so a flat `fileDiffs` is not caused by the workload stopping.
- The retry cache is off.
- The files are empty, so the DataNode stores nothing.
- T3 separates the per-directory path from the file-system path through the `type` string of the same line 483.

### B3. Cluster tier

**B3a. Environment and build.**
- **Host:** one Linux host, pseudo-distributed. Daemons: 1 NameNode and 1 DataNode. No YARN and no SecondaryNameNode (so no automatic checkpoint runs during a run).
- **Build:** in a local copy (`$WORK/hadoop-src`, see B2a), run `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`. Unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `$WORK/hadoop` and set `export HADOOP_HOME=$WORK/hadoop PATH=$WORK/hadoop/bin:$WORK/hadoop/sbin:$PATH`.
- **Run directory:** `S4=$WORK/run` on local disk. About 2 GB free is needed per run, mostly for edit logs.
- **`etc/hadoop/hadoop-env.sh`:**
  - `export JAVA_HOME=<jdk8>`
  - `export HADOOP_LOG_DIR=$S4/logs`
  - `export HADOOP_PID_DIR=$S4/pid`
  - `export HDFS_NAMENODE_OPTS="-Xms2g -Xmx2g"`
  - `export HDFS_DATANODE_OPTS="-Xmx512m"`
- **`core-site.xml`:** `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=$S4/tmp` (write the literal path).
- **`hdfs-site.xml`:**
  - `dfs.replication=1`
  - `dfs.namenode.name.dir=file://$S4/nn`
  - `dfs.datanode.data.dir=file://$S4/dn`
  - `dfs.namenode.enable.retrycache=false`
  - the two knobs from B3b
- **Ports:** if 9000, 9870, 9864, 9866 or 9867 are taken on a shared host, move them with `dfs.namenode.http-address`, `dfs.datanode.address`, `dfs.datanode.http.address`, `dfs.datanode.ipc.address` and the `fs.defaultFS` port. Update the URLs below to match.

**B3b. Knobs.** Each run starts from a freshly formatted NameNode, with the knobs in `hdfs-site.xml` (restart required).

| Run | `dfs.namenode.snapshot.filesystem.limit` | `dfs.namenode.snapshot.max.limit` | Purpose |
|---|---|---|---|
| A | 1000 | 1000 | File-system limit binds halfway through the workload. |
| B | 200 | 200 | Lower limit, to check that usage scales with L. |
| C | 65536 (unset) | 65536 (unset) | Positive control: same workload, no binding limit. |
| D | 65536 (unset) | 100 | Per-directory arm. |
| E | after run A: 500 | 50 | Restart overshoot arm. No reformat; restart only. |

`max.limit` must be ≤ `filesystem.limit`, or the NameNode refuses to start (`SnapshotManager.java:185-191`).

**B3c. Workload.**
- 10 snapshottable directories `/snaptest/d0..d9`, each with 1000 empty files: 10,000 inodes and no blocks.
- 200 rounds. Each round:
  - one WebHDFS `CREATESNAPSHOT` per directory (10 attempts);
  - one `hdfs dfs -chmod <600|644> '/snaptest/d*/f*'`, alternating each round, which changes all 10,000 files.
- That is 2000 create attempts in total.
- **Run A arithmetic:** 10 creates per round reach 1000 at the end of round 99. Rounds 100-199 make 1000 attempts that must fail.
  - Live snapshots: 100 per directory.
  - `FileDiff` count: 10 × 100 × 1000 = 1,000,000.
- **Run C:** 2000 snapshots and 2,000,000 `FileDiff`s.
- **Run B:** 200 snapshots and 200,000 `FileDiff`s.
- **Run D:** each directory stops at 100 snapshots (round 99), so 1000 snapshots and 1,000,000 `FileDiff`s, the same as run A but with the per-directory message.
- **Heap scale:** each `FileDiff` plus its `INodeFileAttributes.SnapshotCopy` is roughly 80-150 B, so run A's snapshot-attributable heap is on the order of 100 MB. Run C should be about twice that. This fits in a 2 GB heap and is far above GC noise.
- **Duration:** about 3-10 s per chmod round, so about 10-35 min per run.

**B3d. Observables and instruments.** Sample every 10 rounds, and once more at the end:
- **NameNode snapshot count:**
  - `curl -s 'http://localhost:9870/jmx?qry=Hadoop:service=NameNode,name=FSNamesystem'`, attributes `Snapshots` (`FSNamesystem.java:4898-4900`) and `LastWrittenTransactionId` (`:4778`).
  - `curl -s 'http://localhost:9870/jmx?qry=Hadoop:service=NameNode,name=NameNodeActivity'`, attribute `CreateSnapshotOps`. It counts attempts (`NameNodeRpcServer.java:1947`).
- **Snapshot-attributable heap (bytes and instance counts):**
  - `jcmd $NNPID GC.class_histogram`. It forces a full GC, so it shows live objects.
  - Keep the lines for `org.apache.hadoop.hdfs.server.namenode.snapshot.Snapshot`, `...snapshot.Snapshot$Root`, `...snapshot.FileDiff`, `...snapshot.DirectoryWithSnapshotFeature$DirectoryDiff` and `org.apache.hadoop.hdfs.server.namenode.INodeFileAttributes$SnapshotCopy`.
  - `B_snap` = the sum of their bytes column.
- **Total heap after that full GC:** `jcmd $NNPID GC.heap_info`, "used".
- **Per-create outcome:** HTTP code and body of every WebHDFS create, logged to `$S4/creates.tsv`.
- **Disk:** at the end of the run, after `hdfs dfsadmin -safemode enter && hdfs dfsadmin -saveNamespace && hdfs dfsadmin -safemode leave`, record the size of the newest `$S4/nn/current/fsimage_*`. Optionally, `hdfs oiv -p XML -i <fsimage> -o $S4/img.xml` and count the `<snapshot>` elements.
- **Not directly observable:** the bytes of each individual snapshot. They are inferred from the class totals.

**B3e. Procedure.**
1. Build and configure (B3a). Set the run's knobs (B3b). Then run:
   - `rm -rf $S4/{nn,dn,tmp,logs}`
   - `hdfs namenode -format -nonInteractive`
   - `start-dfs.sh`
   - `jps`, which must show NameNode and DataNode (and SecondaryNameNode if `start-dfs.sh` started one; stop it with `hdfs --daemon stop secondarynamenode`)
   - `NNPID=$(jps | awk '/ NameNode$/{print $1}')`
2. Check the startup log: `grep "maxSnapshotFSLimit" $S4/logs/hadoop-*-namenode-*.log` must show the configured values (logged at `SnapshotManager.java:163-171`).
3. Setup:

```bash
for d in $(seq 0 9); do
  hdfs dfs -mkdir -p /snaptest/d$d
  hdfs dfs -touchz $(seq -f "/snaptest/d$d/f%g" 0 999)
  hdfs dfsadmin -allowSnapshot /snaptest/d$d
done
```

4. Baseline sample: run the B3d sampling once (round = -1).
5. Rounds:

```bash
U=$(whoami)
for r in $(seq 0 199); do
  for d in $(seq 0 9); do
    code=$(curl -s -o $S4/resp.json -w '%{http_code}' -X PUT \
      "http://localhost:9870/webhdfs/v1/snaptest/d$d?op=CREATESNAPSHOT&snapshotname=s$r&user.name=$U")
    printf '%s\t%s\t%s\t%s\n' "$r" "$d" "$code" "$(tr -d '\n' < $S4/resp.json)" >> $S4/creates.tsv
  done
  m=$([ $((r % 2)) -eq 0 ] && echo 600 || echo 644)
  hdfs dfs -chmod $m '/snaptest/d*/f*'
  if [ $(( (r + 1) % 10 )) -eq 0 ]; then
    { echo "round $r"; curl -s 'http://localhost:9870/jmx?qry=Hadoop:service=NameNode,name=FSNamesystem' | grep -E '"Snapshots"|LastWrittenTransactionId';
      curl -s 'http://localhost:9870/jmx?qry=Hadoop:service=NameNode,name=NameNodeActivity' | grep CreateSnapshotOps;
      jcmd $NNPID GC.class_histogram | grep -E 'namenode\.snapshot\.(Snapshot|Snapshot\$Root|FileDiff|DirectoryWithSnapshotFeature\$DirectoryDiff)$|INodeFileAttributes\$SnapshotCopy$';
      jcmd $NNPID GC.heap_info; } >> $S4/samples.txt
  fi
done
```

6. Save the namespace and record the fsimage size (B3d). Run `hdfs lsSnapshottableDir` and record the snapshot number per directory.
7. Run E, right after run A, before cleanup:
   - `stop-dfs.sh`
   - set `filesystem.limit=500` and `max.limit=50`
   - `start-dfs.sh`
   - Sample once (step-5 commands).
   - `grep -c "ERROR.*file system snapshot limit is 500" $S4/logs/hadoop-*-namenode-*.log`, run before the create below, counts the file-system replay errors. Expect 0: the step-6 `saveNamespace` folded every create into the fsimage, so the restart takes the count from the fsimage (`FSImageFormatPBSnapshot.java:151`, bypass A3 (a)) and replays no `OP_CREATE_SNAPSHOT`. To exercise the replay path (bypass A3 (b)) instead, run a variant E' after a run A that skips step 6: then expect ERROR lines `there are already N snapshot(s) and the file system snapshot limit is 500` for N = 500..999 and `per directory snapshot limit is 50` for N = 50..99 in each directory.
   - Try one create with curl and record its code and message.
8. Stop the cluster: `stop-dfs.sh`, then `jps` must show no NameNode or DataNode. Archive `samples.txt`, `creates.tsv`, the fsimage sizes and the NameNode logs, then `rm -rf $S4/{nn,dn,tmp}`. Repeat from step 1 for the next run.

**B3f. Predictions.** Here `B_snap(r)` is the histogram bytes of the five snapshot classes at round r.

| Run | `Snapshots` at the end | First 403 at | 403 count | 403 message | Histogram at the end | `B_snap` | fsimage |
|---|---|---|---|---|---|---|---|
| A | 1000 | round 100, dir 0 | 1000 | `file system snapshot limit is 1000` | `Snapshot` = `Snapshot$Root` = 1000; `FileDiff` ≈ 1,000,000 | Rises roughly linearly through round 99, then flat: the samples at rounds 99-199 differ by under 2%. Heap-used after GC is flat within a few MB over the same rounds. | `size(A)` |
| B | 200 | round 20 | 1800 | limit is 200 | `FileDiff` ≈ 200,000 | `B_snap(B,end)` ≈ `B_snap(A,end)` / 5 (±20%) | `size(B)` |
| C | 2000 | none | 0 | — | `FileDiff` ≈ 2,000,000 | Linear to the end; `B_snap(C,end)` ≈ 2 × `B_snap(A,end)` (±20%) | `size(C)` |
| D | 1000 | round 100 | 1000 | `per directory snapshot limit is 100` | `FileDiff` ≈ 1,000,000 | ≈ `B_snap(A)` | ≈ `size(A)` |
| E | 1000 after restart (above 500) | — | — | The one create fails with `there are already 1000 snapshot(s) and the file system snapshot limit is 500`; replay ERROR lines: 0 (500 + 500 in variant E') | `Snapshot` = 1000 | Unchanged from the end of A | — |

Further predictions:
- **fsimage sizes:** `size(B) < size(A) < size(C)`, with `size(C) − size(A)` ≈ `size(A) − size(B)` × 1000/800 (±25%).
- **`CreateSnapshotOps`:** rises by 10 every round in every run, before and after the limit.
- **`LastWrittenTransactionId`:** keeps rising after the limit in A, B and D, because the chmod edits continue.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| A: `Snapshots` stops at 1000, all creates from round 100 return 403 with the file-system message, and `B_snap` and the `FileDiff` count are flat from round 99 while C keeps growing linearly | Claim confirmed. The limit caps the NameNode heap that grows with snapshots, and the fsimage. |
| A: `Snapshots` > 1000, or any 200 response after round 99 | Claim wrong: the check does not bind on the live path. |
| A: `Snapshots` = 1000 but `B_snap` or the `FileDiff` count keeps growing after round 99 at a rate comparable to C | Claim wrong about usage: the count is capped but the memory it was meant to bound is not. |
| A: `B_snap` flat, but heap-used after GC keeps growing at the rate of C | Some snapshot-related heap the histogram filter misses. Inspect the full histogram before concluding. |
| C does not grow linearly (for example flat) | Control failed: the workload does not move usage, so A is not conclusive. |
| `B_snap(B)` : `B_snap(A)` : `B_snap(C)` ≈ 1 : 5 : 10 | Usage follows L. |
| D matches A, with the per-directory message | Secondary arm confirmed. |
| E: `Snapshots` = 1000 > 500 after restart | Expected overshoot (bypass A3 (a) or (b)). The limit does not shrink existing usage. |
| E: NameNode fails to start | Different from the source; record it as a finding. |

**B3h. Controls.**
- **Run C** is the positive control: the same workload with a non-binding limit.
- **`CreateSnapshotOps` and `LastWrittenTransactionId`** show that create attempts and chmod modifications continue after the limit. A flat `B_snap` therefore means the cap binds, not that the workload stopped.
- **Run B** shows that usage scales with L, not with a fixed artifact.
- **Empty files** mean no blocks, so the DataNode and its disk are out of the picture.
- **Retry cache off**, and **no SecondaryNameNode**, so no checkpoints change the fsimage mid-run.
- **Histogram after full GC** removes garbage. The class filter isolates snapshot structures from the namespace, which is the same in every run.

**B4. Risks and cleanup.**
- **Disk:** edit logs grow by about 10k transactions per round, roughly 0.1-0.3 GB per run. Keep `$S4` on local disk with ≥ 2 GB free and wipe `nn`, `dn` and `tmp` between runs.
- **Memory:** the NameNode heap is 2 GB and the DataNode 512 MB; check `free -g` first. `jcmd GC.class_histogram` pauses the NameNode briefly, which is harmless here.
- **Ports:** 9000, 9870, 9864, 9866 and 9867. Check with `ss -ltn` and move them if they are taken (B3a).
- **Leftovers:**
  - Run `stop-dfs.sh`, then make sure `jps` shows no NameNode, DataNode or SecondaryNameNode, and `kill` any stragglers listed in `$S4/pid`.
  - In the unit tier, `MiniDFSCluster.shutdown()` runs in `finally`. Afterwards, check that `jps` shows no surefire fork left.
  - Remove the added test file from the local copy only. Nothing touches the shared source tree.

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/SnapshotManager.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/DirectorySnapshottableFeature.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/Snapshot.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/AbstractINodeDiffList.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/DirectoryWithSnapshotFeature.java (grep)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/FileWithSnapshotFeature.java (grep)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/FSImageFormatPBSnapshot.java (grep)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirSnapshotOp.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSNamesystem.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogLoader.java (grep)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirectory.java (grep)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirAttrOp.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/INodeDirectory.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/INodeFile.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/INodeFileAttributes.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/NameNodeRpcServer.java (grep)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/metrics/NameNodeMetrics.java (grep)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/web/resources/ExceptionHandler.java (grep)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/snapshot/TestSnapshotManager.java
- hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/HdfsSnapshots.md
- https://issues.apache.org/jira/browse/HDFS-15497
- https://issues.apache.org/jira/browse/HDFS-15568
- https://issues.apache.org/jira/browse/HDFS-12947

## D. Stage-4 feedback

none yet
