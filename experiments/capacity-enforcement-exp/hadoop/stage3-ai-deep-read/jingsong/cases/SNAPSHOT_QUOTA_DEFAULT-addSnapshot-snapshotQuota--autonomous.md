# SNAPSHOT_QUOTA_DEFAULT — verification solution  <!-- file: cases/SNAPSHOT_QUOTA_DEFAULT-addSnapshot-snapshotQuota--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DirectorySnapshottableFeature.java:188`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/DirectorySnapshottableFeature.java#L188) — `if (n + 1 > snapshotQuota)` in `DirectorySnapshottableFeature.addSnapshot(INodeDirectory, SnapshotManager, String, LeaseManager, long)` (row unit; this is also the main enforcement point) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent (order 39), 2026-11-24 |
| Estimate | `negative` — the check caps the **number** of snapshots of one snapshottable directory (hard-coded 65,536; 0 for a non-snapshottable root). Each snapshot carries only a small fixed NameNode-heap overhead; the heap and DataNode disk that snapshots actually hold (retained inodes, diffs, blocks of deleted/overwritten files) scale with the data captured per snapshot and are not bounded by the count. |
| Ground | The limit-side operand is an object count (`snapshotsByNames.size()` vs. `snapshotQuota`), not bytes. A single snapshot can pin an arbitrary amount of NameNode heap (every deleted inode and block under the directory) and DataNode disk (every block of every deleted or truncated file), so at any count ≤ 65,536 retained memory/disk is unbounded in the workload. Under steady churn (same bytes deleted between snapshots) retained usage does stop at q × (bytes per interval), but that ceiling is set by the churn size, not by the constraint. The fixed per-snapshot overhead the count does bound is a few hundred bytes of heap (order of 10–30 MB at the cap). The constant also cannot be tuned (no key, no admin command). |

## A. Constraint trace

**A1. The constraint.**
- Name: `SNAPSHOT_QUOTA_DEFAULT` (hard-coded constant), which initialises the per-directory field
  `snapshotQuota` that is the operand at the check.
- Kind: constant (`static final int`), package-private.
- First declared: [`DirectorySnapshottableFeature.java:62`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/DirectorySnapshottableFeature.java#L62)
  `static final int SNAPSHOT_QUOTA_DEFAULT = 1 << 16;` with Javadoc "Limit the number of snapshot per
  snapshottable directory". The field: [`DirectorySnapshottableFeature.java:71`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/DirectorySnapshottableFeature.java#L71)
  `private int snapshotQuota = SNAPSHOT_QUOTA_DEFAULT;`
- No `*-default.xml` entry (it is not a configuration key).
- Unit: number of snapshots (count). Default 65,536 (`1 << 16`).
- Values it can take at runtime (all writers of `snapshotQuota`, via `setSnapshotQuota`
  `DirectorySnapshottableFeature.java:156-162`, `INodeDirectory.java:277-279`):
  - 65,536 when a directory becomes snapshottable (`INodeDirectory.addSnapshottableFeature`,
    `INodeDirectory.java:319-329`, new feature uses the field initialiser) or when `allowSnapshot` is
    called on an already-snapshottable directory (`SnapshotManager.java:254-256`) or when the PB
    fsimage loader re-creates a snapshottable root (`FSImageFormatPBSnapshot.java:154-160`).
  - 0 for the root directory at namespace creation (`FSDirectory.java:123-124`) and after
    `disallowSnapshot /` (`SnapshotManager.java:301-302`): the root keeps the snapshottable feature but
    with quota 0, so the same check refuses any snapshot of `/` until `allowSnapshot /`.
  - Any value read from a legacy (pre-protobuf) fsimage (`SnapshotFSImageFormat.java:233-234`; written
    at `SnapshotFSImageFormat.java:68`). The current protobuf image does not store it.
- How it can be set: **not settable** by configuration, `-D`, or admin command. No RPC sets a quota
  other than 65,536/0. Changing it requires rebuilding the NameNode with a different constant, or, in a
  test JVM, calling the public `INodeDirectory.setSnapshotQuota(int)` directly. It is not persisted, so
  any in-memory change is lost on NameNode restart.
- Reader: the NameNode (`FSNamesystem` → `FSDirSnapshotOp.createSnapshot` → `SnapshotManager` →
  `INodeDirectory.addSnapshot` → `DirectorySnapshottableFeature.addSnapshot`), also during edit-log replay.
- Related limits on the same path (named here, not the subject): `dfs.namenode.snapshot.max.limit`
  (per directory, default 65536, `DFSConfigKeys.java:547-549`, `hdfs-default.xml:5527-5534`) and
  `dfs.namenode.snapshot.filesystem.limit` (whole namespace, default 65536, `DFSConfigKeys.java:550-555`,
  `hdfs-default.xml:5536-5543`), read in `SnapshotManager.java:155-162`; the constructor rejects
  max.limit > filesystem.limit (`SnapshotManager.java:185-191`). Also the 28-bit snapshot-ID space
  (`SnapshotManager.java:130`, `454-462`, `763-765`).

**A2. What it caps.** The number of snapshots that may exist at once on one snapshottable directory
(the size of `snapshotsByNames`). The quantity compared is `n + 1`, where
`n = getNumSnapshots() = snapshotsByNames.size()` (`DirectorySnapshottableFeature.java:76-78`, `187`),
against `snapshotQuota`. This is a count of objects. Each live snapshot holds a fixed set of NameNode
heap objects (`Snapshot`, its `Snapshot.Root` copy of the directory inode with name bytes and copied
ACL/XAttr/quota features, `Snapshot.java:162-183`, `239-248`; one `DirectoryDiff`,
`DirectoryWithSnapshotFeature.java:304-306`; list slots) and a fixed-size fsimage/edit-log record. The
**variable** memory and disk attributable to snapshots (diff lists of created/deleted children, copies of
modified inodes, `INodeFile`s and `BlockInfo`s of deleted files kept alive, and the DataNode block
replicas behind them) is not compared against anything here. So the constraint caps no memory or disk
quantity, only the count; the bounded fixed overhead is small.

**A3. Mechanism.**
1. Client `createSnapshot` RPC / WebHDFS `CREATESNAPSHOT` → `FSNamesystem.createSnapshot`
   (`FSNamesystem.java:7175`) → `FSDirSnapshotOp.createSnapshot` (`FSDirSnapshotOp.java:97-125`), which
   takes the FSDirectory write lock and calls `SnapshotManager.createSnapshot`.
2. `SnapshotManager.createSnapshot` (`SnapshotManager.java:448-471`): resolves the snapshottable root
   (`getSnapshottableRoot`, `SnapshotManager.java:318-327`, rejects non-snapshottable dirs), checks the
   snapshot-ID space (`:454-462`), then the **filesystem-wide** limit
   `checkFileSystemSnapshotLimit(numSnapshots)` (`:463-464`, `:473-475`, `:481-496`), then calls
   `srcRoot.addSnapshot(...)` (`:465`).
3. `DirectorySnapshottableFeature.addSnapshot` (`DirectorySnapshottableFeature.java:181-225`):
   `n = getNumSnapshots()` (`:187`), then the check
   [`if (n + 1 > snapshotQuota)`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/DirectorySnapshottableFeature.java#L188)
   throws `SnapshotException("Failed to add snapshot: there are already n snapshot(s) and the snapshot
   quota is q")` (`:188-192`). Only after it passes does it check the configured per-directory limit
   `snapshotManager.checkPerDirectorySnapshotLimit(n)` (`:193`, `SnapshotManager.java:477-479`; throws
   when `n >= dfs.namenode.snapshot.max.limit`, or only logs while the image is loading, `:483-494`), the
   name collision (`:196-200`), then allocates the `DirectoryDiff` (`:202-203`) and inserts the
   `Snapshot` into `snapshotsByNames` (`:204`).
4. Outcome at the limit: the request fails, nothing is allocated, `snapshotCounter`/`numSnapshots` are not
   incremented (`SnapshotManager.java:467-469` not reached), no edit is logged (the edit is logged after
   `createSnapshot` returns, `FSDirSnapshotOp.java:118-125`). The client sees a `SnapshotException`
   (`RemoteException` via RPC; a non-200 response with a `RemoteException` JSON body via WebHDFS).
   Unlike `checkSnapshotLimit`, this check has no "image loading → just log" branch, so it also throws
   during edit replay; since the quota is always 65,536 for user directories, replay of a valid edit log
   cannot reach it.
5. Ordering at defaults: with one directory and default config, `n` equals the filesystem count, and the
   filesystem limit (`numSnapshots >= 65536`) fires first at the 65,537th snapshot, before line 188. With
   several directories, or with `dfs.namenode.snapshot.filesystem.limit` and
   `dfs.namenode.snapshot.max.limit` raised above 65,536, line 188 is the binding check at the 65,537th
   snapshot of one directory. `max.limit` can only be lowered below the quota to bind earlier; raising it
   does not lift the 65,536 quota.
6. Count decreases: `removeSnapshot` (`DirectorySnapshottableFeature.java:238-277`) removes the entry
   (`:273`). With `dfs.namenode.snapshot.deletion.ordered=true`, deleting a non-earliest snapshot only
   marks/renames it (`SnapshotManager.java:511-540`); it stays in `snapshotsByNames` and keeps counting
   toward the quota until the GC removes it.
7. Bypass/overshoot of **memory/disk** (the point of the negative estimate): the check never looks at the
   size of what a snapshot pins. Deleting a file that is in the latest snapshot does not destroy it
   (`FSDirDeleteOp.java:257-260` → `INodeFile.cleanSubtree`, `INodeFile.java:753-781`): its inode,
   `BlockInfo`s and DataNode replicas remain, and no storage-space quota delta is subtracted. So with one
   snapshot, retained heap and disk grow linearly with what is deleted; the quota is irrelevant.

**A4. Other consumers.** NameNode heap is also used by the live namespace, the blocks map, the
retained-but-deleted inodes and diffs of all snapshots (unbounded by count), edit-log buffers, RPC
handling. DataNode disk is used by live blocks and snapshot-retained blocks equally. The only Hadoop
limits that bound snapshot-retained bytes are directory quotas: storage-space quota
(`hdfs dfsadmin -setSpaceQuota`) and namespace quota (`-setQuota`), since deletion of a snapshotted file
does not decrement the directory's usage (A3.7). Edit-log and fsimage disk grow with every
create/delete-snapshot op regardless of how many snapshots are live.

**A5. Evidence beyond the source.**
- HDFS Snapshots guide, `hadoop-hdfs/src/site/markdown/HdfsSnapshots.md:57`: "A snapshottable directory is
  able to accommodate 65,536 simultaneous snapshots" (published at
  https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/HdfsSnapshots.html). It states a
  count, not a memory or disk bound.
- `hdfs-default.xml:5527-5543` (the two configurable count limits, "the default limit ... is 65536").
- Tests: `TestSnapshot.java:439-445` assert `SNAPSHOT_QUOTA_DEFAULT` after `allowSnapshot`.
- WebHDFS `CREATESNAPSHOT`/`ALLOWSNAPSHOT` operations: `hadoop-hdfs/src/site/markdown/WebHDFS.md:1739-1763`.

## B. Verification solution

**B1. Claim under test.** The check at `DirectorySnapshottableFeature.java:188` refuses the
(q+1)-th snapshot of a directory whose quota is q, but the NameNode heap and DataNode disk held by that
directory's snapshots do not follow q: with the snapshot count held at or below q, retained heap
(inodes/blocks) and retained disk (block replicas) grow in proportion to the data deleted under the
snapshots, with no refusal from this check. The claim is wrong if retained usage saturates at a level set
by q independent of the data size, or if a write/delete is refused by the snapshot quota.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 8, Maven ≥ 3.3. Copy the tree to local disk first: `rsync -a ~/hadoop-3.4.2/ /mydata/s3o39/hadoop/`
  (any local directory with ≥ 10 GB free; never the shared copy).
- `cd /mydata/s3o39/hadoop && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`
- New test class (in the snapshot package so it can read the package-private constant):
  `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/snapshot/TestSnapshotQuotaRetention.java`.
- Run: `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestSnapshotQuotaRetention -DtrimStackTrace=false`
  (surefire fork heap is fine at the module default; the data sizes below total < 300 MB).
- `MiniDFSCluster` with 1 DataNode, `conf`:
  `dfs.replication=1`, `dfs.blocksize=1048576`, `dfs.namenode.snapshot.max.limit=200000`,
  `dfs.namenode.snapshot.filesystem.limit=200000` (so neither configured limit fires before line 188),
  `dfs.namenode.snapshot.capture.openfiles=false` (default). Base dir from `MiniDFSCluster` default under
  `target/test/data` (local disk).
- Setting the quota (the knob) inside the test, after `hdfs.allowSnapshot(dir)`:
  ```java
  FSNamesystem fsn = cluster.getNamesystem();
  fsn.writeLock();
  try {
    fsn.getFSDirectory().getINode4Write(dir.toString()).asDirectory().setSnapshotQuota(q);
  } finally { fsn.writeUnlock(); }
  ```
  Read back with `getDirectorySnapshottableFeature().getSnapshotQuota()` and also check
  `hdfs.getSnapshottableDirListing()` → `getSnapshotQuota()`.

**B2b. Knobs.**
- `q` (snapshot quota of the test directory): 4, 16, and 65,536 (= `SNAPSHOT_QUOTA_DEFAULT`, untouched).
  4 and 16 make the cap cheap to reach; 65,536 confirms the shipped value.
- `S` (bytes per file deleted under the snapshots): 1 MiB and 8 MiB, at fixed `q=4` and fixed file count
  `F=4` per round. This is the variable the claim says retained usage follows. One extra run at
  `q=16, S=1 MiB` separates the effect of q from S.
- `N` (empty files deleted under one snapshot, heap test): 1,000 and 10,000, at `q=4`, 1 snapshot.

**B2c. Workload.**
- T1 count: for each q, `mkdirs /t1_q`, put one 1-byte file, `allowSnapshot`, set q, then loop
  `hdfs.createSnapshot(dir, String.format("s%06d", i))` until `SnapshotException`. For q=65,536 this is
  65,536 in-JVM RPCs (edit-log sync each; expect minutes, give the test a 30-minute timeout, or put it
  behind `-Dsq.full=true`).
- T2 retained bytes: directory `/t2_q_S`; rounds r=1..q+2: write F=4 files `f_r_k` of S bytes
  (`DFSTestUtil.createFile(hdfs, p, S, (short)1, seed)`), try `createSnapshot("s"+r)` (rounds q+1 and q+2
  are refused by the quota; catch and record), `delete(p)` each file. Retained after round q =
  q × 4 × S: 16 MiB (q=4, S=1 MiB), 128 MiB (q=4, S=8 MiB), 64 MiB (q=16, S=1 MiB). The two rounds past the
  cap write and delete 4×S that no snapshot captured, so they must be freed.
- T3 retained inodes: `q=4`, `/t3_N/sub`; create N empty files (`hdfs.create(p).close()`),
  `createSnapshot("s1")`, `delete(/t3_N/sub, true)`.

**B2d. Observables and instruments.**
- Operand: `sf.getNumSnapshots()` (= n) and `sf.getSnapshotQuota()`, where
  `sf = fsdir.getINode(dir).asDirectory().getDirectorySnapshottableFeature()`; the accepted count and the
  exception message at refusal.
- Retained storage charged to the directory: `hdfs.getQuotaUsage(dir).getSpaceConsumed()` (deleted but
  snapshotted files are not subtracted, A3.7).
- Blocks in the NameNode: `fsn.getBlocksTotal()`; inodes: `fsn.getFilesTotal()` (inode-map size,
  `FSNamesystem.java:5409-5413`; snapshot-retained inodes stay in the map).
- DataNode disk: `FileUtils.sizeOfDirectory(cluster.getInstanceStorageDir(0, 0))` +
  `(0, 1)` (block + `.meta` files). After each delete, wait until stable: call
  `cluster.triggerHeartbeats()` and poll `getBlocksTotal()` and the DN directory size every 500 ms until
  two equal readings (≤ 30 s), because block invalidation is asynchronous.
- Heap of snapshot objects: optional, `jcmd <surefire-pid> GC.class_histogram` at the end of T1 (count of
  `org.apache.hadoop.hdfs.server.namenode.snapshot.Snapshot` and `Snapshot$Root` = n). Total test-JVM
  heap is too noisy (DN, client, cluster in one JVM) to attribute bytes; the inode/block counts above are
  the heap proxies.
- Cannot observe directly: the exact bytes of each retained object (use the counts).

**B2e. Procedure.**
1. Build (B2a). Write the test class with methods `testQuotaCount` (T1, over q), `testRetainedBytes`
   (T2 over (q,S), plus controls), `testRetainedInodes` (T3 over N), each starting a fresh
   `MiniDFSCluster` (`numDataNodes(1)`) in `@Before` and shutting it down in `@After`.
2. In each method, log one line per reading: `q, S|N, round, n, spaceConsumed, blocksTotal, filesTotal,
   dnBytes`, and the exception message when the quota refuses.
3. Encode the predictions (B2f) as assertions so the run fails loudly if contradicted; keep the logs.
4. Run with the command in B2a; copy `target/surefire-reports/*TestSnapshotQuotaRetention*` to the
   results location.

**B2f. Predictions.**
- T1: accepted count = q exactly (4, 16, 65,536); the (q+1)-th call throws `SnapshotException` with
  message `Failed to add snapshot: there are already q snapshot(s) and the snapshot quota is q`
  (from line 188, not the "per directory snapshot limit" or "file system snapshot limit" messages).
  `Snapshot`/`Snapshot$Root` instance counts = q.
- T2: spaceConsumed after round r ≤ q is r × 4 × S; blocksTotal grows by 4 × S/1 MiB per round; DN bytes ≈
  spaceConsumed + ~0.8% `.meta`. Rounds q+1, q+2: snapshot refused (quota message), totals unchanged
  after the deletes. Plateaus: 16 MiB (q=4,S=1 MiB), 128 MiB (q=4,S=8 MiB), 64 MiB (q=16,S=1 MiB). So at the
  same q=4 and the same n=4, retained bytes differ 8× with S: the level is q × (bytes per interval), set by
  the workload, with no byte bound from q.
- T3 (q=4, n=1): filesTotal after the delete stays ≈ baseline + N + 1 (+1,001 vs +10,001) with n=1 ≪ q.
  No refusal.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| T1 accepted = q, refusal message names "snapshot quota is q" | The check works as traced (mechanism confirmed). |
| T1 refused earlier with "per directory"/"file system" limit message | Config limits not raised as in B2a; fix and rerun (not a reading on the claim). |
| T2 retained bytes scale with S (≈8×) at the same n=q=4; T3 retained inodes scale with N at n=1 (positive control C1 stops growth) | **Claim confirmed**: usage does not follow the snapshot quota; the count is capped while bytes/inodes are not. |
| T2 plateau the same for S=1 MiB and S=8 MiB at q=4 (moves with q, not S); or a write/delete refused with the snapshot-quota message; or T3 inodes released at n=1 | **Claim refuted**: usage follows the quota. |
| Retained bytes back to baseline after each round's delete while snapshots exist | Snapshots did not capture the files (snapshot taken after delete, or wrong dir): **not confirmed**, fix the workload. |
| Positive control C1 does not stop growth | The instruments do not see a binding cap; **not confirmed**. |

**B2h. Controls.**
- C1 positive control (a cap known to bind, same T2 workload): directory `/t2_ctrl` with
  `hdfs.setQuota(dir, HdfsConstants.QUOTA_DONT_SET, 40L*1024*1024)` (40 MiB storage-space quota), q=4,
  S=8 MiB: round 1 (32 MiB) succeeds and is retained by `s1`; in round 2 the 2nd file fails with
  `DSQuotaExceededException`; spaceConsumed stays ≤ 40 MiB. Retained usage follows the space quota.
- No-snapshot control: the same rounds in a non-snapshottable dir → spaceConsumed and DN bytes return to
  baseline after each delete (deletion frees space when nothing pins it, so retention in T2 is due to
  snapshots).
- Release control: after T2, `deleteSnapshot` s1..sq → spaceConsumed, blocksTotal and DN bytes return to
  baseline (retention is attributable to those snapshots).
- Quota read-back: assert `getSnapshotQuota()==q` before the loop, so a refusal at q is not a coincidence.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux host, pseudo-distributed: NameNode + 1 DataNode (no YARN needed). JDK 8 (or 11 to run).
- Build the distribution from the local copy:
  `cd /mydata/s3o39/hadoop && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`;
  unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `/mydata/s3o39/dist/`;
  `export HADOOP_HOME=/mydata/s3o39/dist/hadoop-3.4.2 HADOOP_CONF_DIR=$HADOOP_HOME/etc/hadoop`
  `HADOOP_LOG_DIR=/mydata/s3o39/logs HADOOP_PID_DIR=/mydata/s3o39/pids`.
- `hadoop-env.sh`: `export HDFS_NAMENODE_OPTS="-Xms1g -Xmx1g -XX:+UseG1GC"`,
  `export HDFS_DATANODE_OPTS="-Xmx512m"`.
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=/mydata/s3o39/tmp`.
- `hdfs-site.xml`: `dfs.replication=1`, `dfs.namenode.name.dir=/mydata/s3o39/nn`,
  `dfs.datanode.data.dir=/mydata/s3o39/dn`, `dfs.namenode.snapshot.max.limit=200000`,
  `dfs.namenode.snapshot.filesystem.limit=200000` (so line 188 is the first check to bind at the
  65,537th snapshot of one directory; read at NameNode start, restart needed to change),
  `dfs.permissions.enabled=true` (default; run everything as one user who owns the test dirs).
- Disk: ≥ 12 GB free on `/mydata` (≤ 5 GiB of retained block data at once plus ~1.3 GiB of local source
  files); check with `df -h /mydata` first.
- Start: `hdfs namenode -format -nonInteractive`, `hdfs --daemon start namenode`,
  `hdfs --daemon start datanode`; wait for `hdfs dfsadmin -safemode get` = OFF.

**B3b. Knobs.**
- The constraint itself is fixed at 65,536 in a stock build (not settable; A1). The cluster tier therefore
  holds q = 65,536 and varies the data captured per snapshot:
  - `S` per file deleted under the snapshots: 64 MiB and 256 MiB (F=4 files per round, 4 rounds), at a
    snapshot count of 4.
  - `G`, data captured by the 65,536th (last allowed) snapshot of the capped directory: 1 GiB and 4 GiB,
    i.e. retained bytes at the cap.
  - `N` empty files deleted under one snapshot: 50,000 and 100,000.
- Optional (only if stage 4 wants q varied in a real daemon): rebuild with `SNAPSHOT_QUOTA_DEFAULT = 16`
  (one-line change at `DirectorySnapshottableFeature.java:62`), same workloads; prediction unchanged except
  the cap is 16.

**B3c. Workload.**
- Local source files: `head -c 64M /dev/urandom > /mydata/s3o39/src64`, `head -c 256M /dev/urandom > /mydata/s3o39/src256`,
  `head -c 1G /dev/urandom > /mydata/s3o39/src1g`.
- P1 (retained disk at a small count): `hdfs dfs -mkdir /r64 && hdfs dfsadmin -allowSnapshot /r64`; for
  r in 1..4: `for k in 1 2 3 4; do hdfs dfs -put /mydata/s3o39/src64 /r64/f_${r}_$k; done`,
  `hdfs dfs -createSnapshot /r64 s$r`, `hdfs dfs -rm -skipTrash "/r64/f_${r}_*"`. Retained = 16 × 64 MiB =
  1 GiB. Repeat in `/r256` with src256: 16 × 256 MiB = 4 GiB.
- P2 (count to the cap, then retained bytes at the cap): `hdfs dfs -mkdir /cap`,
  put a 1-byte file, `hdfs dfsadmin -allowSnapshot /cap`. Create snapshots 1..65,535 via WebHDFS (a CLI JVM
  per call is too slow):
  ```bash
  for i in $(seq -f %06g 1 65535); do
    curl -s -o /dev/null -w '%{http_code}\n' -X PUT \
      "http://localhost:9870/webhdfs/v1/cap?op=CREATESNAPSHOT&snapshotname=s$i&user.name=$USER"
  done | sort | uniq -c        # expect 65535 x 200
  ```
  Then put G into `/cap` (`src1g` once for G=1 GiB), `CREATESNAPSHOT s065536` (the 65,536th; must
  succeed), `hdfs dfs -rm -skipTrash /cap/g*`, then `CREATESNAPSHOT s065537` (must fail). Then, still at the
  cap, put another 1 GiB and delete it (not captured: must be freed). For G=4 GiB: `DELETESNAPSHOT s065536`
  (count back to 65,535, its 1 GiB freed), put `src1g` four times, `CREATESNAPSHOT s065536` again, delete
  the four files, `CREATESNAPSHOT s065537` (must fail).
  The 65,535 calls take roughly 10–30 minutes (curl process + one edit sync per op).
- P3 (retained heap at count 1): `hdfs dfs -mkdir -p /h50k/sub{0..9}`; `allowSnapshot /h50k`; create N
  files in batches of 5,000 paths per JVM: `hdfs dfs -touchz /h50k/sub0/f{1..5000}` … (10 batches for
  50,000; `/h100k` with 20 batches for 100,000); `hdfs dfs -createSnapshot /h50k s1`;
  `hdfs dfs -rm -r -skipTrash "/h50k/sub*"`.

**B3d. Observables and instruments.**
- Operand / count: `hdfs lsSnapshottableDir` (columns include snapshot number and snapshot quota,
  printed by `SnapshottableDirectoryStatus.print`), `curl -s 'http://localhost:9870/jmx?qry=Hadoop:service=NameNode,name=FSNamesystem'`
  → `Snapshots`, `SnapshottableDirectories`, `BlocksTotal`, `FilesTotal`; the HTTP code and
  `RemoteException.message` of the refused call.
- Retained disk charged to the directory: `hdfs dfs -count -q -v /r64` (SPACE_CONSUMED column) and
  `hdfs dfs -du -s /r64` (includes snapshots unless `-x`).
- Actual disk on the DataNode: `du -sb /mydata/s3o39/dn/current` after block deletion settles (poll
  every 5 s until two equal readings; the DN deletes asynchronously after a heartbeat), and `df -B1 /mydata`.
- NameNode heap: `jcmd <NNpid> GC.class_histogram | egrep 'snapshot\.Snapshot$|Snapshot\$Root|DirectoryDiff |INodeFile |BlockInfoContiguous '`
  (forces a full GC; instance counts and bytes per class) and `jcmd <NNpid> GC.run; jcmd <NNpid> GC.heap_info`
  (used heap after GC). `NNpid` from `jps | grep -w NameNode`.
- Sampling: after each round (P1); at n = 0, 16,384, 32,768, 49,152, 65,535, 65,536 and after the refused
  65,537th (P2); before the snapshot and after the delete (P3).
- Not directly observable: the exact heap of one snapshot (derive it from the histogram deltas over n).

**B3e. Procedure.**
1. `df -h /mydata`; `ss -ltn` for free ports; build and unpack (B3a); write configs; format; start NN, DN;
   `jps` shows both.
2. Baseline readings (JMX, `du -sb`, histogram).
3. Run P1 for S=64 MiB (`/r64`), readings after each round; then P1 for S=256 MiB (`/r256`).
4. Positive control C1 (B3h) in `/ctl`; no-snapshot control in `/plain`.
5. Release control: `hdfs dfs -deleteSnapshot /r64 s1` … `s4` (and `/r256`, `/ctl`); wait; `du -sb` back to
   baseline. This also frees disk before P2.
6. Run P2 (G = 1 GiB, then G = 4 GiB as described), readings at the listed n; record the 65,537th refusal
   message.
7. Run P3 for N = 50,000 and N = 100,000; histogram before the snapshot and after the delete.
8. Stop: `hdfs --daemon stop datanode`, `hdfs --daemon stop namenode`; `jps` shows neither.

**B3f. Predictions.**
- P1: after round r, SPACE_CONSUMED of `/r64` = r × 256 MiB (1 GiB after round 4); of `/r256` =
  r × 1 GiB (4 GiB after round 4); `du -sb dn/current` rises by the same (+~0.8% checksums) and does not
  fall after the `-rm`; 4 snapshots per dir. Ratio 4× at identical snapshot count. No quota refusal.
- P2: all creations up to 65,536 return 200; `Snapshots` = 65,536 (P1 snapshots deleted in step 5); the
  65,537th returns non-200 with message
  `Failed to add snapshot: there are already 65536 snapshot(s) and the snapshot quota is 65536`.
  `Snapshot`, `Snapshot$Root`, `DirectoryDiff` instance counts rise linearly to 65,536 and then stop; their
  total is on the order of 150–400 B per snapshot, roughly 10–30 MB of heap at the cap. After deleting G
  under the last snapshot, DN bytes stay ≈ G above baseline (1 GiB, then 4 GiB) with the count pinned at
  65,536; the uncaptured 1 GiB put/deleted at the cap is freed.
- P3: `INodeFile` instance count and `FilesTotal` stay ≈ baseline + N after the delete (≈ +50,000 vs
  +100,000) with 1 snapshot on that directory; used heap after GC is higher by roughly N × a few hundred
  bytes and differs ≈2× between the N values.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| P1/P2: retained DN bytes and SPACE_CONSUMED scale with S or G (4×) at the same snapshot count; P3 retained `INodeFile`s scale with N at count 1; while C1 stops growth at its space quota | **Claim confirmed**: usage does not follow the snapshot quota. |
| P2: 65,537th refused with the "snapshot quota is 65536" message; snapshot-object counts plateau at 65,536 | The check binds as traced, on the count (the only thing it caps). |
| Retained bytes equal for S=64 MiB and 256 MiB (or G=1 vs 4 GiB) at the same count, or the snapshot-quota message on a `put`/`rm`, or retained heap stops at a level set by the count rather than N | **Claim refuted**: usage follows the constraint. |
| DN bytes return to baseline after `-rm` while the snapshots exist | Snapshots did not capture the data (ordering error): **not confirmed**. |
| C1 does not stop growth at 1 GiB | Instruments/workload cannot show a binding cap: **not confirmed**. |
| 65,537th refused with "file system snapshot limit" or "per directory snapshot limit" message | Config limits not raised (B3a); the line-188 reading is not taken, rerun. |

**B3h. Controls.**
- C1 positive control (same P1 workload where a cap is known to bind): `hdfs dfs -mkdir /ctl`,
  `hdfs dfsadmin -allowSnapshot /ctl`, `hdfs dfsadmin -setSpaceQuota 1g /ctl` (applies live, no restart),
  then P1 rounds with S=256 MiB: round 1 (4 × 256 MiB = 1 GiB) cannot complete — the 4th put fails with
  `DSQuotaExceededException` once consumed + the 128 MiB block reservation exceeds 1 GiB; SPACE_CONSUMED
  and DN bytes stop at ≤ 1 GiB. Usage follows a byte cap; the same workload under only the snapshot quota
  (`/r256`) reaches 4 GiB.
- No-snapshot control: the same put/rm rounds in a non-snapshottable `/plain` → DN bytes return to
  baseline after each `-rm`.
- Release control: deleting the snapshots frees the retained bytes (step 5), attributing retention to them.
- The count and quota are read from `lsSnapshottableDir` before and after, so the cap value is observed,
  not assumed.

**B4. Risks and cleanup.**
- Disk: at most ~5 GiB of retained blocks at once plus ~1.3 GiB of source files; keep everything under
  `/mydata/s3o39` on local disk; never point `dfs.*.dir`, `hadoop.tmp.dir` or `HADOOP_LOG_DIR` at shared
  storage; check `df` before each phase.
- Memory: NN at 1 GiB heap is ample (≈10–30 MB for 65,536 snapshots, < 100 MB for 100,000 retained inodes);
  DN 512 MiB.
- Edit log: P2 writes 65,536+ edit ops (a few MB); harmless.
- Ports: 9000, 9870, 9864, 9866, 9867; check they are free (`ss -ltn`) before starting; if not, move them in
  `core-site.xml`/`hdfs-site.xml`.
- Unit tier: build only in the local copy; `mvn` writes `target/` there; the `MiniDFSCluster` is shut down in
  `@After`; check no surefire JVM remains (`jps`).
- Cleanup: `hdfs --daemon stop datanode; hdfs --daemon stop namenode`; `jps` shows no NameNode/DataNode;
  `rm -rf /mydata/s3o39/{nn,dn,tmp,logs,pids,src64,src256,src1g}` (keep the dist only if stage 4 reruns).

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/DirectorySnapshottableFeature.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/SnapshotManager.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/Snapshot.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/DirectoryWithSnapshotFeature.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/FSImageFormatPBSnapshot.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/SnapshotFSImageFormat.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/INodeDirectory.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/INodeFile.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirectory.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirSnapshotOp.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirDeleteOp.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSNamesystem.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/metrics/FSNamesystemMBean.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/SnapshottableDirectoryStatus.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/web/resources/PutOpParam.java
- hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/HdfsSnapshots.md
- hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/HdfsQuotaAdminGuide.md
- hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/WebHDFS.md
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/snapshot/TestSnapshot.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/snapshot/TestNestedSnapshots.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/MiniDFSCluster.java
- https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/HdfsSnapshots.html (same text as HdfsSnapshots.md)

## D. Stage-4 feedback

none yet
