# dfs.namenode.max.objects — verification solution  <!-- file: cases/dfs.namenode.max.objects-checkFsObjectLimit-maxFsObjects--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`FSNamesystem.java:5395`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSNamesystem.java#L5395-L5396): `if (maxFsObjects != 0 && maxFsObjects <= dir.totalInodes() + getBlocksTotal())` in `FSNamesystem.checkFsObjectLimit()` (row unit, no helper) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | stage-3 autonomous agent, 2026-11-24 |
| Estimate | `positive`: once `inodes + blocks` reaches `dfs.namenode.max.objects`, every create / mkdir / symlink / addBlock RPC is refused, so the namespace objects that make up most of the NameNode's long-lived heap stop growing. The cap is on an object **count**, not bytes, and is approximate: multi-level `mkdir -p` / create-with-parents, concurrent `addBlock`, copy-on-truncate and image/edit loading can exceed it. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- Name: `dfs.namenode.max.objects` (exact key; deprecated alias `dfs.max.objects`,
  `HdfsConfiguration.java:83-84` in hadoop-hdfs-client).
- Kind: configuration key.
- First declared: the string literal in
  [`HdfsClientConfigKeys.java:311`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/HdfsClientConfigKeys.java#L311)
  (`DeprecatedKeys.DFS_NAMENODE_MAX_OBJECTS_KEY = "dfs.namenode.max.objects"`), re-exported as
  [`DFSConfigKeys.java:222-224`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java#L222-L224)
  (`DFS_NAMENODE_MAX_OBJECTS_KEY`, `DFS_NAMENODE_MAX_OBJECTS_DEFAULT = 0`).
- `hdfs-default.xml:1136-1143`: value `0`, "The maximum number of files, directories and blocks dfs
  supports. A value of zero indicates no limit".
- Unit: a count of namespace objects (inodes of every kind + blocks). No unit suffix.
- Default: `0` = unlimited. The Java constant and `hdfs-default.xml` agree (both 0).
- Read once in the `FSNamesystem` constructor into the `final` field `maxFsObjects`
  (`FSNamesystem.java:614`, `FSNamesystem.java:964-965`, `conf.getLong`). Set in the NameNode's
  `hdfs-site.xml`. It is not among the NameNode's reconfigurable properties (no reference in
  `NameNode.java`) and the field is final, so **a change needs a NameNode restart**.
- Read by: the NameNode only (active and standby both construct `FSNamesystem`, but only the RPC
  write paths call the check; see A3).

**A2. What it caps.** The number of namespace objects held by the NameNode. The quantity compared is
`dir.totalInodes() + getBlocksTotal()` (`FSNamesystem.java:5396`), where
`FSDirectory.totalInodes()` = `inodeMap.size()` (`FSDirectory.java:1582-1588`): every file, directory
and symlink inode, including inodes kept alive only by snapshots; and `getBlocksTotal()` =
`BlockManager.getTotalBlocks()` = `blocksMap.size()` (`FSNamesystem.java:5172-5174`,
`BlockManager.java:4927-4929`). Each of these objects (`INodeFile` / `INodeDirectory` / `INodeSymlink`
with its name `byte[]`, `inodeMap` entry and parent children-list slot; `BlockInfo` with its storage
triplets and `blocksMap` entry) lives on the NameNode's Java heap for as long as it exists in the
namespace. So the resource is **NameNode heap (long-lived, old generation)**; the cap is indirect: a
count, with a per-object byte cost that varies with name length, replication, ACLs/xattrs, etc.

**A3. Mechanism.**
1. `maxFsObjects` is loaded at NameNode start (`FSNamesystem.java:964-965`).
2. The check,
   [`FSNamesystem.java:5395-5396`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSNamesystem.java#L5395-L5396),
   is skipped when `maxFsObjects == 0`. Otherwise, if `maxFsObjects <= inodes + blocks` it throws
   `IOException("Exceeded the configured number of objects <max> in the filesystem.")`
   (`FSNamesystem.java:5397-5398`); the RPC fails and nothing is created. If `inodes + blocks < max`
   the operation proceeds and adds its objects. Because the check runs **before** the insertion, a
   single-object operation can bring the total to exactly `max`, and the next one is refused.
3. Callers (all on the RPC write path):
   - `mkdirs`: `FSDirMkdirOp.java:70` (under `fsd.writeLock()`, `FSDirMkdirOp.java:49`), only when the
     final path component is missing; then `createParentDirectories` (`FSDirMkdirOp.java:125-148`)
     creates **all** missing ancestors plus the leaf after this one check. The code's own comment
     calls it "at best, a heuristic" (`FSDirMkdirOp.java:67-69`).
   - `create` / `startFile`: `FSDirWriteFileOp.java:392`, then `createAncestorDirectories`
     (`FSDirWriteFileOp.java:395`) may add missing parents before `addFile`.
   - `createSymlink`: `FSDirSymlinkOp.java:73`.
   - `addBlock` (each new block of a file): `analyzeFileState`, `FSDirWriteFileOp.java:606`, called both
     from `validateAddBlock` under the **read** lock (`FSNamesystem.java:3060-3066`) and again from
     `storeAllocatedBlock` under the write lock (`FSNamesystem.java:3080-3087`, `FSDirWriteFileOp.java:231`).
     A file whose create brought the total to exactly `max` is left open with no block: its first
     `addBlock` is refused.
4. Overshoot and bypass paths (objects added without the check, or several per check):
   - `mkdir -p a/b/.../z` with D missing components: one check, D inodes (D ≤ 1000 by
     `HdfsServerConstants.MAX_PATH_DEPTH`, `HdfsServerConstants.java:55`, enforced at
     `NameNodeRpcServer.java:1160-1161`). Same for a create with missing parents.
   - Copy-on-truncate (`FSDirTruncateOp.java:234-238`, `fsn.createNewBlock`) adds a block with no check.
   - Snapshot creation (`FSDirSnapshotOp.java:97-118`) has no check; snapshot diffs and copied
     attributes are not counted at all, and deleted-but-snapshotted inodes stay in `inodeMap`
     (counted, not freed).
   - Edit-log replay (`FSEditLogLoader.java:394` OP_ADD, `:565` OP_ADD_BLOCK, `:637` OP_MKDIR,
     `:717` OP_SYMLINK) and fsimage loading never call the check: a NameNode restarted with a `max`
     below its current count loads the whole namespace and then refuses all new objects; a standby
     with a different setting applies everything the active wrote.
   - The block side counts `BlockInfo`s: an erasure-coded block group counts once whatever its
     internal blocks; replicas per block are not counted.
   - Over the limit, deletes still work (no check on delete), so the count can be brought down again.

**A4. Other consumers.** NameNode heap is also used, outside this constraint, by RPC call queues and
handler buffers, edit-log buffers, the retry cache, the lease manager, `DatanodeDescriptor`s and block
reports in flight, the under-/over-replication and invalidation queues, snapshot diffs, xattrs/ACLs
(per inode, not bounded by this count), the inode-name byte arrays (length up to
`dfs.namenode.fs-limits.max-component-length`) and transient garbage. Related count limits on the same
objects: namespace quota (`hdfs dfsadmin -setQuota`, per directory),
`dfs.namenode.fs-limits.max-directory-items` (`hdfs-default.xml:467`),
`dfs.namenode.fs-limits.max-blocks-per-file`.

**A5. Evidence beyond the source.**
- Existing test `hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestFileLimit.java`
  (`testFileLimit`): with `max=5`, two one-block files fit (root + 2×2 = 5), the third create fails,
  deleting a file frees room, `mkdirs("/dir0/dir1")` adds 2, another `mkdirs` fails.
- `hadoop-common/src/site/markdown/DeprecatedProperties.md:38` (`dfs.max.objects` → `dfs.namenode.max.objects`).
- `hadoop-common/src/site/markdown/Metrics.md:285-286` (`BlocksTotal`, `FilesTotal` metrics).
- Hadoop 3.4.2 hdfs-default: https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/hdfs-default.xml

## B. Verification solution

**B1. Claim under test.** With `dfs.namenode.max.objects = M > 0`, the NameNode refuses to create
namespace objects once `FilesTotal + BlocksTotal` reaches `M`, so the count, and with it the NameNode's
retained (post-full-GC) heap held by inodes and blocks, stops growing at `M` (plus the multi-level
`mkdir -p` overshoot), while the same workload with `M = 0` keeps growing both.

### B2. Unit tier

**B2a. Environment and build.** JDK 8, Maven 3.3+. Copy the tree to local disk
(`rsync -a ~/hadoop-3.4.2/ /mydata/<run>/src/`); never build in the shared copy. Build once:
`cd /mydata/<run>/src && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
Add a test class
`hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestMaxObjectsCap.java`
in package `org.apache.hadoop.hdfs.server.namenode`, so the package-private `fsn.dir.totalInodes()` is
accessible (as in `TestFileLimit`). Surefire JVM defaults are enough; pass
`-Dtest.build.data=/mydata/<run>/testdata-<M>` so MiniDFSCluster data stays on local disk.

**B2b. Knobs.** `DFSConfigKeys.DFS_NAMENODE_MAX_OBJECTS_KEY` set on the test `Configuration` before
`new MiniDFSCluster.Builder(conf).numDataNodes(1).build()`, taken from a system property
`-Dcap.max=<M>`: `M ∈ {0, 1000, 5000}`. 0 is the unlimited positive control; 1000 and 5000 show that
the stopping point scales with the knob. One new cluster per value and per sub-test (the field is final).

**B2c. Workload.** Four sub-tests, each on a fresh cluster with `SimulatedFSDataset.setFactory(conf)`
(blocks cost no real disk) and `dfs.blocksize=1024`:
1. *Inodes only*: `fs.mkdirs(/w)` (total 2 = root + `/w`), then loop `i = 0 .. 2M-1` (for M = 0 use
   10000) `fs.create(new Path("/w/f"+i)).close()` (empty file = 1 inode, 0 blocks). Stop at the first
   `IOException` whose message contains "Exceeded the configured number of objects". 2M attempts is
   twice the limit, so the limit is reached.
2. *Inodes + blocks*: `fs.mkdirs(/b)` (total 2), loop
   `DFSTestUtil.createFile(fs, new Path("/b/f"+i), 1024, (short) 1, 0xDEADBEEFL)` (1 inode + 1 block
   each), same stopping rule, up to M attempts (10000 for M = 0).
3. *mkdir -p overshoot* (M > 0 only): create empty files as in 1 until the total equals `M-1`, then
   one `fs.mkdirs(new Path("/deep/d1/d2/.../d50"))` (51 missing directories: `/deep` + 50 levels),
   then one more `create`.
4. *Reload bypass* (M > 0 only): fill as in 1 to exactly M, then
   `cluster.getConfiguration(0).setLong(DFS_NAMENODE_MAX_OBJECTS_KEY, M/2)`,
   `cluster.restartNameNode(true)`, then try one more `create`.

**B2d. Observables and instruments.** After every operation: `fsn.dir.totalInodes()`,
`fsn.getBlocksTotal()`, their sum `T`, `fsn.getMaxObjects()` (re-fetch `fsn = cluster.getNamesystem()`
after a restart), the number of successful operations, and the message of the first failure. Print as
CSV lines (`subtest,M,i,inodes,blocks,T,ok`) to stdout (run with `-Dsurefire.useFile=false` or read
`target/surefire-reports/*-output.txt`). Optional, secondary: heap used from
`ManagementFactory.getMemoryMXBean()` after `System.gc()` at start and end, noisy because NameNode,
DataNode and client share the JVM; the operand `T` is the primary measurement. Not observable here:
heap per namespace object (cluster tier).

**B2e. Procedure.**
1. Write `TestMaxObjectsCap` with methods `inodesOnly`, `inodesAndBlocks`, `mkdirOvershoot`,
   `reloadBypass` as in B2c; each logs the CSV and the final values (no assertion that would stop the run).
2. For each `M` in `{0, 1000, 5000}`:
   `cd /mydata/<run>/src && mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestMaxObjectsCap -Dcap.max=$M -Dtest.build.data=/mydata/<run>/testdata-$M -Dsurefire.useFile=false | tee /mydata/<run>/unit-$M.log`
   (sub-tests 3 and 4 return immediately for `M=0`).
3. Sanity check with the stock test:
   `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestFileLimit#testFileLimit`.
4. Collect the CSV lines; then `rm -rf /mydata/<run>/testdata-*`.

**B2f. Predictions.**
- Sub-test 1: `M=0`: all 10000 creates succeed, final `T = 10002`. `M=1000`: exactly 998 creates succeed
  (T goes 2 → 1000), create #999 fails with "Exceeded the configured number of objects 1000", final
  `T = 1000`. `M=5000`: 4998 succeed, final `T = 5000`.
- Sub-test 2: each file adds 2. `M=0`: 10000 files, `T = 20002`. `M=1000`: 499 complete files
  (T = 2 + 998 = 1000), the 500th create fails; final `T = 1000`, blocks = 499. `M=5000`: 2499 files,
  `T = 5000`.
- Sub-test 3: the single `mkdirs` succeeds and `T` jumps from `M−1` to `M+50`, **50 above M**; the
  following create fails.
- Sub-test 4: the NameNode restarts with `T = M` although the new limit is `M/2` (no load-time check);
  `getMaxObjects()` = M/2; the next create fails; `T` stays `M`.
- In every capped run `T_final` does not depend on the number of attempts beyond the limit, and equals
  `M` (sub-tests 1, 2, 4) or `M + 50` (sub-test 3).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `T_final = M` for M = 1000 and 5000, while M = 0 completes all attempts | Claim confirmed at the mechanism level: the count follows the knob. |
| Creates succeed past `T = M` other than through sub-test 3's multi-level mkdir | Claim wrong: the check is not enforced on that path; re-trace. |
| `T_final` equal for M = 1000 and 5000, or M never reached | Workload did not reach the limit or the knob was not applied (check `getMaxObjects()`); not confirmed. |
| M = 0 control also stops early | Something else limits creation (quota, max-directory-items, disk); run invalid. |
| Sub-test 3 does **not** overshoot | Overshoot path closed in this tree; A3 item 4 wrong, the cap is tighter than traced. |
| Sub-test 4 NameNode refuses to start | A load-time check exists; A3 item 4 wrong. |

**B2h. Controls.** `M = 0` with the same workload (positive control: the count moves with the workload
when uncapped). `getMaxObjects()` logged to prove the value was applied. The failure message is matched
textually so a failure from another limit (quota; `max-directory-items` = 1048576, far above these
sizes) is not taken for this one. A fresh cluster per value and sub-test.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, pseudo-distributed HDFS: NameNode, SecondaryNameNode
and one DataNode (no YARN needed). JDK 8 for the build, JDK 8 or 11 to run. Build on local disk:
`cd /mydata/<run>/src && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`, then
`cp -r hadoop-dist/target/hadoop-3.4.2 /mydata/<run>/hadoop` and
`export HADOOP_HOME=/mydata/<run>/hadoop HADOOP_CONF_DIR=/mydata/<run>/conf PATH=$HADOOP_HOME/bin:$HADOOP_HOME/sbin:$PATH`
(copy `$HADOOP_HOME/etc/hadoop/*` to `/mydata/<run>/conf` first).
- `hadoop-env.sh`: `export JAVA_HOME=...`, `export HADOOP_LOG_DIR=/mydata/<run>/logs`,
  `export HADOOP_PID_DIR=/mydata/<run>/pids`,
  `export HDFS_NAMENODE_OPTS="-Xms1g -Xmx1g -XX:+UseParallelGC"` (fixed heap so post-GC figures are
  comparable), `export HDFS_DATANODE_OPTS="-Xmx512m"`.
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=/mydata/<run>/tmp`.
- `hdfs-site.xml`: `dfs.replication=1`, `dfs.namenode.name.dir=/mydata/<run>/nn`,
  `dfs.datanode.data.dir=/mydata/<run>/dn`, `dfs.namenode.max.objects=<M>`,
  `dfs.blocksize=1048576`.
- Passwordless `ssh localhost` for `start-dfs.sh`. Local disk needed: < 5 GB (mostly the build).

**B3b. Knobs.** `dfs.namenode.max.objects` in `hdfs-site.xml`, `M ∈ {0, 100000, 200000}`: 0 is the
uncapped positive control; 100k and 200k are large enough for the namespace's heap to rise clearly above
GC noise yet fit a 1 GB heap. Each value: stop the NameNode, edit, **restart** (not refreshable). A
freshly formatted namespace per value. For workload 2, `M ∈ {0, 20000}`.

**B3c. Workload.** All through the normal client (`hdfs dfs`).
1. *Inodes*: 300,000 empty files in 300 directories `/w/d000 .. /w/d299`, 1000 files each:
   ```
   hdfs dfs -mkdir -p /w
   for d in $(seq -w 0 299); do
     hdfs dfs -mkdir /w/d$d
     seq -f "/w/d$d/f%04g" 0 999 | xargs hdfs dfs -touchz 2>>/mydata/<run>/touchz-$M.err
   done
   ```
   About 300,302 objects attempted (> 200,000), so both capped values are reached. Duration: about 600
   client JVM launches plus 300k create/complete RPC pairs, tens of minutes.
2. *Blocks* (fresh namespace per M ∈ {0, 20000}): 15,000 one-byte local files
   (`mkdir /mydata/<run>/small && for i in $(seq 1 15000); do printf x > /mydata/<run>/small/s$i; done`)
   uploaded with `hdfs dfs -put /mydata/<run>/small /b 2>>/mydata/<run>/put-$M.err`: 15,001 inodes +
   15,000 blocks ≈ 30,000 > 20,000.
3. *Overshoot* (after workload 1 with `M=100000` has stopped): free one slot with
   `hdfs dfs -rm -skipTrash /w/d000/f0000`, then
   `hdfs dfs -mkdir -p /deep/$(seq -s/ -f 'd%g' 1 50)` (51 new directories), then
   `hdfs dfs -touchz /after`.
4. *Reload* (after workload 1 with `M=200000` has filled the namespace): `stop-dfs.sh`, set `M=100000`
   in `hdfs-site.xml`, `start-dfs.sh`, `hdfs dfsadmin -safemode wait`, try `hdfs dfs -touchz /x`.

**B3d. Observables and instruments.**
- Count: `curl -s 'http://localhost:9870/jmx?qry=Hadoop:service=NameNode,name=FSNamesystemState'`
  → `FilesTotal`, `BlocksTotal`, `MaxObjects` (`FSNamesystemMBean.java:52,83,185`); after every 10
  directories of workload 1 and at the end.
- Successes/failures: count of lines in `touchz-$M.err` / `put-$M.err` containing
  "Exceeded the configured number of objects".
- Retained NameNode heap: `NNPID=$(jps | awk '$2=="NameNode"{print $1}')`;
  `jcmd $NNPID GC.class_histogram > /mydata/<run>/hist-$M-<step>.txt` (forces a full GC; read instance
  counts and bytes of `org.apache.hadoop.hdfs.server.namenode.INodeFile`, `INodeDirectory`, `[B`,
  `org.apache.hadoop.hdfs.server.blockmanagement.BlockInfoContiguous`), then `jcmd $NNPID GC.run` and
  `jstat -gc $NNPID` → old-gen used `OU` after full GC. Take at baseline (after format + start, before the
  workload), after every 50 directories, and at the end.
- Not directly observable: heap per individual object; derived as the slope of post-GC `OU` against
  `FilesTotal + BlocksTotal` in the `M=0` run.

**B3e. Procedure.** For each `M` in (0, 100000, 200000):
1. `stop-dfs.sh` if running; `rm -rf /mydata/<run>/{nn,dn,tmp}`; set `dfs.namenode.max.objects=$M`.
2. `hdfs namenode -format -nonInteractive`; `start-dfs.sh`; `hdfs dfsadmin -safemode wait`; check that
   `jps` shows NameNode, DataNode, SecondaryNameNode; check JMX `MaxObjects = $M`.
3. Baseline: JMX query, class histogram, `jcmd GC.run`, `jstat -gc`.
4. Run workload 1, sampling as in B3d; record successes and failures.
5. End-of-run samples. For `M=100000` then do workload 3 and sample; for `M=200000` then do workload 4
   and sample.
6. Separately, for `M ∈ {0, 20000}` on a fresh namespace (steps 1-3), workload 2 with JMX before/after.
7. `stop-dfs.sh`; `jps` must list no NameNode, DataNode or SecondaryNameNode.

**B3f. Predictions.** A fresh namespace has total 1 (root). Let `s` be the slope of post-GC `OU` against
`FilesTotal + BlocksTotal` measured in the `M=0` run.
- `M=0`: all 300,000 `touchz` succeed; `FilesTotal = 300,302` (root + `/w` + 300 directories + 300k
  files), `BlocksTotal = 0`; `INodeFile` instances ≈ 300,000; post-GC `OU` grows about linearly, by
  ≈ `s × 300,000` above baseline.
- `M=100000`: `FilesTotal + BlocksTotal` stops at exactly `100,000` (in directory `d099`, after 99,898
  files); every later `touchz` and `mkdir` fails with the "Exceeded …" message; `INodeFile` count stops
  at 99,898; post-GC `OU` growth stops at ≈ `s × 100,000` (about one third of the control's growth) and
  stays flat over the rest of the workload.
- `M=200000`: stops at exactly `200,000`; `OU` growth ≈ `s × 200,000` (about two thirds of the control).
- Workload 3: after the delete (total 99,999) the `mkdir -p` succeeds and the total becomes `100,050`,
  **50 above M**; `/after` fails.
- Workload 4: the NameNode starts with a total of `200,000 > 100,000`; `MaxObjects = 100000`; `/x` fails.
- Workload 2: `M=0`: `FilesTotal ≈ 15,002`, `BlocksTotal = 15,000`. `M=20000`:
  `FilesTotal + BlocksTotal` stops at 20,000 (≈ 9,999 files with ≈ 9,999 blocks, possibly one file
  left without a block); `put` reports errors for the rest.
- The claim is wrong if, in a capped run, `FilesTotal + BlocksTotal` exceeds `M` other than through
  workload 3's multi-level mkdir, or if post-GC heap keeps rising with the namespace size while creates
  keep succeeding past `M`.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Count stops at M; post-GC `OU` and `INodeFile` count plateau at ≈ M/300k of the control's growth | Claim confirmed: the knob caps the heap retained by the namespace. |
| Count stops at M but post-GC `OU` keeps rising over the failed remainder of the workload | Count capped but heap not governed by it (other consumers, A4); claim refuted for memory. |
| Count exceeds M on single-level operations | Check not enforced as traced; claim refuted. |
| Control (`M=0`) shows no measurable `OU` growth | Instrument too coarse or workload too small; not confirmed; enlarge the workload. |
| Count never reaches M in a capped run | Workload too small or knob not applied (check `MaxObjects` in JMX); not confirmed. |
| Workload 3 overshoots by 50 | Confirms the approximate nature (A3 item 4); expected, not a refutation. |
| Workload 4 NameNode starts with the count above M | Confirms the load-path bypass; expected. |

**B3h. Controls.** The `M=0` run is the positive control (same workload, no cap; count and heap move).
`MaxObjects` read from JMX proves the configured value is live. Fixed `-Xms = -Xmx` and a full GC before
every heap reading remove young-generation noise. A fresh format per M so no earlier namespace or edit
log carries over. The error text is checked so quota or `max-directory-items` failures are not counted
as cap hits. No other client uses the NameNode during the run.

**B4. Risks and cleanup.** All data, logs and pids under `/mydata/<run>/` (local disk, < 5 GB); nothing
on shared storage. Ports 9000, 9870, 9864-9867 and 9868 must be free; check with `ss -ltnp` before
starting and change them in `*-site.xml` if taken. NameNode 1 GB + DataNode 512 MB + client JVMs:
confirm the host has ≥ 4 GB free. After the unit tier: `rm -rf /mydata/<run>/testdata*` and check with
`jps` that no surefire JVM is left. After the cluster tier: `stop-dfs.sh`, `jps` shows no NameNode,
DataNode or SecondaryNameNode (kill any leftover by PID), then
`rm -rf /mydata/<run>/{nn,dn,tmp,small,pids}` once the readings and logs are copied. Never write into
the shared source tree.

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSNamesystem.java (614, 955-970, 2790-2822, 3047-3090, 3249-3255, 5172-5174, 5372-5405, 5645-5669)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java (222-224)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/HdfsClientConfigKeys.java (311)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/HdfsConfiguration.java (80-86)
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml (1136-1143, 467-470)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirectory.java (1582-1588)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/BlockManager.java (4927-4929)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/BlocksMap.java (207-211)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirMkdirOp.java (49-80, 104-175)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirSymlinkOp.java (57-80)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirWriteFileOp.java (160-256, 357-400, 590-615)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirTruncateOp.java (219-245)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirSnapshotOp.java (97-118)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogLoader.java (394, 565, 637, 717)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/metrics/FSNamesystemMBean.java (52, 83, 185)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/NameNode.java (searched: no reference to the key)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/NameNodeRpcServer.java (1155-1171)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/common/HdfsServerConstants.java (54-55)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestFileLimit.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/NNThroughputBenchmark.java (option list only; not used)
- hadoop-common-project/hadoop-common/src/site/markdown/DeprecatedProperties.md (38)
- hadoop-common-project/hadoop-common/src/site/markdown/Metrics.md (285-286)
- https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/hdfs-default.xml

## D. Stage-4 feedback

none yet
