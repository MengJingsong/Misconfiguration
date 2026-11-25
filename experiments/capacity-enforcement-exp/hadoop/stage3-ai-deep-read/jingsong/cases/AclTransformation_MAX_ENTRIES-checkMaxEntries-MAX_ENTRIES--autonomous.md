# AclTransformation_MAX_ENTRIES — verification solution  <!-- file: cases/AclTransformation_MAX_ENTRIES-checkMaxEntries-MAX_ENTRIES--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`AclTransformation.java:323`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/AclTransformation.java#L323) (`if (accessEntries.size() > MAX_ENTRIES)` in `checkMaxEntries`; the twin check for the default scope is [`AclTransformation.java:327`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/AclTransformation.java#L327)) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive`. Every NameNode ACL-modifying RPC (setAcl, modifyAclEntries, removeAclEntries, removeDefaultAcl) runs its result through `checkMaxEntries`. The check rejects any ACL with more than 32 access or 32 default entries before the `AclFeature` is created, so the per-inode ACL object on the NameNode heap (an `int[]` of at most 29 + 32 = 61 packed entries) and its `OP_SET_ACL` edit-log and fsimage records are capped. The cap is per ACL object only. It does not bound the total ACL heap, which scales with the number of distinct ACLs. It is also not enforced when edits or fsimage are loaded. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- Name: `MAX_ENTRIES` in `org.apache.hadoop.hdfs.server.namenode.AclTransformation`. It is qualified as `AclTransformation_MAX_ENTRIES` because another `MAX_ENTRIES` exists in the tree (`hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/HarFileSystem.java:1251`, an LRU-cache field that is unrelated).
- Kind: hard-coded constant, `private static final int`.
- Declaration: [`AclTransformation.java:64`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/AclTransformation.java#L64) `private static final int MAX_ENTRIES = 32;`. It has no `*-default.xml` entry and no configuration key.
- Unit: ACL entries per scope (access, default), counted separately per scope.
- Default: 32 (a literal), so the logical ACL can hold at most 64 entries. This is documented in `hadoop-hdfs/src/site/markdown/HdfsPermissionsGuide.md:224`: "The maximum number is 32 for access and 32 for default entries which is 64 in total."
- How it is set: not settable. Changing it needs a source edit, a rebuild of the `hadoop-hdfs` jar and a NameNode restart.
- Reader: the NameNode, on the ACL RPC paths. The only related configuration is the feature switch `dfs.namenode.acls.enabled` (`hdfs-default.xml:602`, default `true`), checked at `FSDirAclOp.java:200-207`.

**A2. What it caps.**
- The resource is NameNode heap: the `AclFeature` attached to an inode (`AclFeature.java:38`, `private final int[] entries`, one packed 32-bit int per entry per `AclEntryStatusFormat.java:30-42`). It also caps the on-disk size of the inode's ACL in the edit log (`FSEditLog.java:1269-1274`, `OP_SET_ACL` carries the full list) and in the fsimage (`FSImageFormatPBINode.java:634`, `buildAclEntries`).
- The compared quantity is the number of entries in each scope of the *resulting* logical ACL (`ScopedAclEntries.getAccessEntries().size()` and `getDefaultEntries().size()`, `AclTransformation.java:321-322`). That count includes owner, group, other and mask. The same method is also applied to the raw input spec (`AclTransformation.java:464`).
- Mapping from logical to stored entries: `createAclFeature` (`AclStorage.java:319-338`) stores the access entries minus owner, mask and other (`subList(1, size-2)`, at most 32 − 3 = 29), plus all default entries (at most 32). So the stored array holds at most 61 ints, about 16 + 244 = 260 bytes, rounded to 264, plus a 24-byte `AclFeature` object.

**A3. Mechanism.**
1. RPC entry: `NameNodeRpcServer.java:2193` (modifyAclEntries), `:2200` (removeAclEntries) and `:2219` (setAcl) call `FSNamesystem.modifyAclEntries` (`FSNamesystem.java:7966`), `setAcl` (`:8064`) and the related methods. Each takes the namesystem write lock and calls `FSDirAclOp` (`FSNamesystem.java:7978`, `:8003`, `:8027`).
2. `FSDirAclOp.modifyAclEntries` → `AclTransformation.mergeAclEntries` (`FSDirAclOp.java:50`). `removeAclEntries` → `filterAclEntriesByAclSpec` (`:76`). `removeDefaultAcl` → `filterDefaultAclEntries` (`:101`). `setAcl` → `unprotectedSetAcl(..., fromEdits=false)` → `replaceAclEntries` (`:194`).
3. Pre-check on the input: `merge`, `filter` and `replace` wrap the user's spec in `ValidatedAclSpec` (`AclTransformation.java:81`, `:139`, `:201`). Its constructor sorts the spec and calls `checkMaxEntries(new ScopedAclEntries(aclSpec))` (`AclTransformation.java:462-466`). The comment there says this runs early so that a huge spec is not processed under the namesystem lock.
4. Post-check on the result: each transformation builds the new list, adds the copied default entries (`copyDefaultsIfNeeded`, `:409-439`) and the computed mask (`calculateMasks`, `:355-401`), then calls `buildAndValidateAcl` (`:271`). That method calls `checkMaxEntries(scopedEntries)` at `:292`.
5. The check: [`AclTransformation.java:323`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/AclTransformation.java#L323) `if (accessEntries.size() > MAX_ENTRIES)` throws `AclException("Invalid ACL: ACL has N access entries, which exceeds maximum of 32.")`. The default-scope twin is at [`:327`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/AclTransformation.java#L327).
   - **When the check fails:** the exception propagates out of `FSDirAclOp` (rewrapped with the path at `FSDirAclOp.java:54-56`). This happens before `AclStorage.updateINodeAcl` (`:52`) and before `logSetAcl` (`:53`), so the inode keeps its old ACL. No `AclFeature` is created, no user or group name is interned in `SerialNumberManager` (interning happens in `AclEntryStatusFormat.toInt`, `:94`, called only from `createAclFeature`), and no edit is written. The client gets an `AclException` (`DFSClient.java:2739` etc. unwrap it).
   - **When the check passes:** `AclStorage.updateINodeAcl` (`AclStorage.java:270-304`) replaces the feature with `createAclFeature(...)`. The new feature is deduplicated through `AclStorage.addAclFeature` → `UNIQUE_ACL_FEATURES` (`AclStorage.java:67-68`, `:391-392`; `INodeWithAdditionalFields.java:366-372`).
6. Arithmetic at the boundary: an access ACL with *k* named entries has *k* + 4 entries (owner, group, mask, other). So *k* ≤ 28 is accepted and *k* = 29 is rejected. A spec of 32 entries without a mask passes the pre-check but fails the post-check once the automatic mask makes 33 (the existing test `TestAclTransformation.testReplaceAclEntriesResultTooLarge`, `TestAclTransformation.java:1145-1161`).

Paths that skip or exceed the check:
- **Edit-log replay** (`FSEditLogLoader.java:972-976` → `FSDirAclOp.unprotectedSetAcl(..., fromEdits=true)`): `newAcl = aclSpec` is stored without any transformation or check (`FSDirAclOp.java:191-196`).
- **Fsimage load** (`FSImageFormatPBINode.java:109-116`, `:184-186`, `:549-551`): the stored ints are wrapped in `AclFeature` with no count check.
  An edit log or fsimage produced by a NameNode with a different limit, or crafted offline, therefore loads ACLs of any size.
- **Default-ACL inheritance** (`AclStorage.copyINodeDefaultAcl`, `AclStorage.java:76-149`) does not call the check. It copies at most the parent's ≤32 default entries into the child's access scope, plus the same ≤32 default entries for a child directory, so it stays within the cap.
- **Transient input:** the RPC's `List<AclEntry>` is fully deserialized before the pre-check. Its size is bounded only by `ipc.maximum.data.length` (`core-default.xml:2585`, 128 MiB). The constant does not bound this short-lived memory.
- **External `INodeAttributeProvider`:** an ACL it returns at read time is not stored by the NameNode and is outside this check.

**A4. Other consumers.**
- The total ACL heap is the number of *distinct* ACLs × at most about 330 bytes, which this constant does not cap. The number of distinct ACLs is bounded only by the inode count (`dfs.namenode.max.objects`, default 0 = unlimited).
- The user and group name string tables (`SerialNumberManager`, 24-bit name field per `AclEntryStatusFormat.java:42`) grow with distinct names and are never shrunk.
- Other inode heap: the inode itself, xattrs (capped separately) and blocks.
- Edit-log and fsimage disk on `dfs.namenode.name.dir` and `dfs.namenode.edits.dir`.

**A5. Evidence beyond the source.**
- `HdfsPermissionsGuide.md:224` (Hadoop 3.4.2 docs: https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/HdfsPermissionsGuide.html) states the limit of 32 + 32.
- HDFS-7582 (https://issues.apache.org/jira/browse/HDFS-7582) is cited in the comment at `AclTransformation.java:318` as the change that made the count per scope. It is referenced only through that comment; the JIRA page was not opened.
- Existing unit tests `TestAclTransformation.java:346`, `:356`, `:725`, `:735`, `:745`, `:763`, `:1125`, `:1135`, `:1145` (`*InputTooLarge`, `*ResultTooLarge`) assert that `AclException` is thrown at 33 entries.

## B. Verification solution

**B1. Claim under test.** No ACL-modifying client operation can make the NameNode store an `AclFeature` with more than 29 access-derived plus 32 default packed entries (61 ints), so per-inode ACL heap and `OP_SET_ACL` record size stop growing at the 32-per-scope boundary. Requests past it are rejected with no heap or edit-log change. Removing the cap (positive control) lets the same workload grow heap and edits in proportion to the requested entry count.

### B2. Unit tier

**B2a. Environment and build.**
- Toolchain: JDK 8 and Maven 3.3+.
- Copy the tree to local disk: `rsync -a ~/hadoop-3.4.2/ /mydata/<run>/src/` (never the shared copy), then `cd /mydata/<run>/src`.
- Build: `mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
- New test file: `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestAclMaxEntriesProbe.java`. It must be in this package to reach the package-private `AclTransformation`, `AclFeature.getEntriesSize()` and `FSDirAclOp.unprotectedSetAcl`.
- Run: `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestAclMaxEntriesProbe -DfailIfNoTests=false`.
- JVM options: Surefire's defaults are enough, since the test heap is tiny.
- `MiniDFSCluster` setup: `new MiniDFSCluster.Builder(conf).numDataNodes(0).build()`, with `conf.set("hdfs.minidfs.basedir", "/mydata/<run>/minidfs")` and `dfs.namenode.acls.enabled=true` (the default).

**B2b. Knobs.**
- The constant cannot be set, so the swept variable is the requested entry count.
- k = number of named user entries in an access spec: k ∈ {1, 27, 28, 29, 30, 60, 1000}. These bracket the boundary 28/29, given *k* + 4 ≤ 32.
- The same k for the default scope on a directory.
- An incremental variant: one entry per `modifyAclEntries` call, 40 calls.
- Optional second knob: a patched copy with `MAX_ENTRIES = 1024` (`sed -i 's/MAX_ENTRIES = 32;/MAX_ENTRIES = 1024;/' .../AclTransformation.java` in the local copy only, then rebuild hadoop-hdfs). This shows the check alone is what stops growth.

**B2c. Workload.** Four parts in one JUnit class.
- **Part 1, direct.** Build `existing` = minimal ACL `[user::rwx, group::r-x, other::---]`. Build `spec` = `user::rwx` + k × `user:u<i>:r--` + `group::r-x` + `other::---` (k + 3 entries; the mask is added automatically). Call `AclTransformation.replaceAclEntries(existing, spec)` and `mergeAclEntries(existing, spec)`. Record whether `AclException` is thrown and its message (the message carries the operand N = k + 4), or else the result size.
- **Part 2, MiniDFSCluster.**
  - Per k, create file `/p/f_k`, then `fs.setAcl(path, spec)`. Read `fsd.getINode("/p/f_k").getAclFeature()`, which is `null` if minimal, and record `getEntriesSize()` and `fs.getAclStatus(path).getEntries().size()`.
  - Directory `/p/d_k`: the same, plus k default named entries.
  - Incremental: directory `/p/inc`, then 40 × `fs.modifyAclEntries(path, [user:v<i>:r--])`. Record the iteration of the first `AclException` and `getEntriesSize()` after each call.
  - Inheritance: under `/p/d_28` (full default), `mkdirs /p/d_28/child` and `create /p/d_28/childfile`, and record their `getEntriesSize()`.
- **Part 3, positive control without a rebuild.**
  - Inside `fsn.writeLock(); try { ... } finally { fsn.writeUnlock(); }` (`FSNamesystem.java:1815`, `:1825`; `unprotectedSetAcl` asserts the lock at `FSDirAclOp.java:181`, and `FSDirectory.writeLock()` is only an assertion, `FSDirectory.java:271-273`), call `FSDirAclOp.unprotectedSetAcl(fsd, fsd.getINodesInPath("/p/ctl", DirOp.WRITE), fullSortedAcl(k=1000), true)`. This is the edit-replay path, which skips the check (A3).
  - `fullSortedAcl` must be sorted with `AclTransformation.ACL_ENTRY_COMPARATOR` and include the mask.
  - Record `getEntriesSize()` → expect 1001.
- **Part 4, heap per ACL.**
  - For each of 2,000 directories `/h/d<i>`, set a unique full ACL: 27 shared named users + `user:x<i>:r--` (unique name, defeats dedup) + full default with 28 named.
  - Measure `AclStorage.getUniqueAclFeatures().getUniqueElementsSize()` (`ReferenceCountMap.java:95`).
  - Measure `Σ getEntriesSize()`.
  - Arithmetic: 2,000 × 61 ints = 122,000 ints ≈ 488 KB of `int[]` payload.

**B2d. Observables and instruments.**
- Exception presence and message: the operand N is printed in it.
- `AclFeature.getEntriesSize()`, the stored-array length.
- `AclStatus.getEntries().size()`.
- Unique feature count in `UNIQUE_ACL_FEATURES`.
- Optional: `jmap -histo:live <surefire-pid> | grep -E 'AclFeature|\[I '` at a pause point (`Thread.sleep` behind a system property) for live bytes.
- Not directly observable: the check's local `accessEntries.size()` when it passes, because it is not logged. It is inferred as `AclStatus` size + 3 (owner, group and other are reported via permission bits, not entries).
- Print every reading as `READING k=<k> part=<p> accepted=<bool> stored=<n> msg=<msg>` to stdout so it is parsable from `target/surefire-reports/*-output.txt`.

**B2e. Procedure.**
1. Copy the tree and build as in B2a.
2. Write `TestAclMaxEntriesProbe` with Parts 1–4 as separate `@Test` methods sharing one `@BeforeClass` `MiniDFSCluster`.
3. Run `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestAclMaxEntriesProbe`.
4. Run `grep READING hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports/*TestAclMaxEntriesProbe-output.txt`.
5. Optional: apply the patched constant (B2b), rebuild hadoop-hdfs (`mvn -pl hadoop-hdfs-project/hadoop-hdfs install -DskipTests -o`), and rerun steps 3–4.
6. Clean up: `rm -rf /mydata/<run>/minidfs`.

**B2f. Predictions (stock, MAX_ENTRIES = 32).**

| k (named) | logical access size | setAcl/merge outcome | stored ints (file) | stored ints (dir, full default with same k) |
|---|---|---|---|---|
| 1 | 5 | accepted | 2 | 2 + 5 = 7 |
| 27 | 31 | accepted | 28 | 28 + 31 = 59 |
| 28 | 32 | accepted | 29 | 29 + 32 = 61 |
| 29 | 33 | `AclException`, "ACL has 33 access entries" (post-check; spec of 32 passes the pre-check) | unchanged (none) | unchanged |
| 30 | 34 | `AclException`, "ACL has 33 access entries" (pre-check: spec = 33) | unchanged | unchanged |
| 60 / 1000 | 64 / 1004 | `AclException`, pre-check message "ACL has 63 / 1003 access entries" | unchanged | unchanged |

- Incremental: calls 1–28 succeed. The first call adds the mask, so after it the logical size is 5. Call 29 throws, and `getEntriesSize()` stays at 29 for calls 29–40.
- Inheritance: child dir of `/p/d_28` has 61 stored ints; child file has 29.
- Part 3 control: stored ints = 1001 (unbounded path).
- Part 4: unique features = 2,000 and Σ stored ints = 122,000 (never above 61 per inode).
- Patched (1024) build: k = 29, 60 and 1000 accepted, with stored ints k + 1 for files.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Accepted up to k = 28, rejected from k = 29, stored ints never > 61 per inode | Claim confirmed at unit level: the check caps the stored object |
| Any client-path call stores > 29 access-derived or > 32 default ints | Claim wrong: a bypass on the client path |
| Rejection but `getEntriesSize()` changed, or `UNIQUE_ACL_FEATURES` grew | Claim wrong in part: state mutated before the throw |
| Part 3 stores 1001 ints | Positive control OK: storage has no other bound, so the cap is the only limit on the client path |
| Part 3 fails or stores ≤ 61 | Control did not move. Another limit exists; result is not confirmed and needs re-tracing |
| Patched build accepts 1000 and stores 1001 | Confirms the constant, not something else, is what binds |

**B2h. Controls.**
- k = 1 and k = 27 show that the instrument sees growth below the cap.
- Part 3 and the patched build show growth when the check is absent.
- The incremental variant rules out a pre-check-only effect.
- The unique `x<i>` name rules out deduplication hiding growth.
- `dfs.namenode.acls.enabled=true` is asserted at start, so a disabled-ACL rejection cannot be mistaken for the cap (its message differs: "Support for ACLs has been disabled").

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux host, pseudo-distributed HDFS: NameNode + 1 DataNode. YARN is not needed.
- Build the distribution in the local copy: `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`, then unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `/mydata/<run>/hadoop-stock`.
- For the control, copy it to `/mydata/<run>/hadoop-patched` and replace `share/hadoop/hdfs/hadoop-hdfs-3.4.2.jar` with the jar built after the 1024 patch (B2b).
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=/mydata/<run>/tmp`.
- `hdfs-site.xml`:
  - `dfs.replication=1`
  - `dfs.namenode.name.dir=/mydata/<run>/nn`
  - `dfs.datanode.data.dir=/mydata/<run>/dn`
  - `dfs.namenode.acls.enabled=true`
  - `dfs.namenode.checkpoint.period=86400`, so no checkpoint mid-run; the period is in seconds, so this is 24 h.
- `hadoop-env.sh`:
  - `HADOOP_LOG_DIR=/mydata/<run>/logs`
  - `HADOOP_PID_DIR=/mydata/<run>/pids`
  - `HDFS_NAMENODE_OPTS="-Xms1g -Xmx1g -XX:+UseParallelGC"` (a fixed heap for stable histograms)
  - `HADOOP_HEAPSIZE_MAX=512m` for other daemons.
- Disk: under 2 GB, mostly edits.
- Load client: `AclLoad.java`, a small program that is not in the tree.
  - Input: `mode` (`set` or `modify`), `D`, `k`, `kDefault` and `prefix`.
  - For each i < D it calls `FileSystem.setAcl(new Path(prefix + "/d" + i), spec(i))`, where `spec(i)` = `user::rwx`, (k − 1) × `user:u<j>:r--` (shared names) + `user:x<i>:r--` (unique), `group::r-x`, `other::---`, plus a default spec with kDefault named entries when kDefault > 0.
  - It counts accepted and rejected calls and prints the first exception message.
  - Compile: `javac -cp $(bin/hadoop classpath) -d /mydata/<run>/cls AclLoad.java`.
  - Run: `java -cp /mydata/<run>/cls:$(bin/hadoop classpath) AclLoad ...`.

**B3b. Knobs.**
- Requested entries per directory:
  - Phase 1, at the cap: k = 28, kDefault = 28 (61 stored ints).
  - Phase 2, past the cap: k = 29, then 100, then 1000 (kDefault = 0).
- Constant: stock (32) vs patched (1024), the positive control.
- Changing the build means stopping HDFS, switching `HADOOP_HOME` and restarting the NameNode. The constant cannot be refreshed.
- D = 10,000 directories per phase.

**B3c. Workload.**
- Create `/acl/d0…d9999` with `AclLoad mkdirs`, or with one `hdfs dfs -mkdir -p` call over a brace-expanded list in chunks of 500.
- Phase 1 arithmetic: 10,000 × 61 ints × 4 B = 2.44 MB `int[]` payload. Each array is 264 B, so `[I` grows by 2.64 MB, plus 10,000 `AclFeature` instances (24 B each, 240 KB) and 10,000 unique `x<i>` user strings.
- Phase 2 (stock): every call is rejected, so expect zero growth.
- Phase 2 control (patched, k = 1000, access only): about 1001 ints × 4 B ≈ 4,020 B → 4,024 B per directory. Total ≈ 40 MB of `[I` on top of phase 1, clearly above histogram noise. The edit log gains about 10,000 `OP_SET_ACL` records of about 1004 entries each, roughly 12 B per entry, ≈ 120 MB of edits.
- Duration: about 10–20 minutes per phase over RPC from one client.

**B3d. Observables and instruments.**
- NameNode heap per class:
  - `jmap -histo:live $(jps | awk '/ NameNode$/{print $1}')`. This forces a full GC.
  - Record the rows for `org.apache.hadoop.hdfs.server.namenode.AclFeature` (instances, bytes) and `[I` (bytes).
  - Take one sample after each phase, three samples 30 s apart to read noise.
- Live heap: `jcmd <pid> GC.heap_info` and `jstat -gc <pid>` after `jcmd <pid> GC.run`.
- Edit-log disk:
  - `du -b /mydata/<run>/nn/current/edits_inprogress_*` before and after each phase. The file is preallocated in 1 MB chunks, so instead use `hdfs dfsadmin -rollEdits` and `du -b` the finalized segments.
  - `hdfs oev -i <segment> -o seg.xml` then `grep -c OP_SET_ACL seg.xml` and count `<ENTRY>` per op.
- Fsimage disk: after each phase run `hdfs dfsadmin -safemode enter; hdfs dfsadmin -saveNamespace; hdfs dfsadmin -safemode leave` and `ls -l /mydata/<run>/nn/current/fsimage_*`.
- Client: AclLoad accepted and rejected counts plus the first error message (carries N).
- Sample check: `hdfs dfs -getfacl /acl/d0 | grep -c '^user:x\|^user:u'` gives the named count, which stays ≤ 28 per scope on stock.
- Not observable directly: the check's local operand on success. It is inferred from `getfacl` (number of lines).

**B3e. Procedure.**
1. Build and unpack (B3a). Run `hdfs namenode -format -nonInteractive`, then `start-dfs.sh` from `hadoop-stock`. Run `jps` and confirm NameNode, DataNode and SecondaryNameNode are up.
2. Create the D directories. Take baseline H0 (histo ×3), roll edits, record E0 and fsimage size F0.
3. Phase 1: `AclLoad set 10000 28 28 /acl`. Expect 10,000 accepted. Take H1, E1, F1.
4. Phase 2: `AclLoad set 10000 29 0 /acl`, then `... 100 ...`, then `... 1000 ...`. Expect all rejected. Take H2, E2, F2. Also run `AclLoad modify` with 1 extra entry on dirs at k = 28 and expect all rejected.
5. Control:
   - `stop-dfs.sh`, then check `jps`.
   - Set `HADOOP_HOME=/mydata/<run>/hadoop-patched` with the same configuration directory and data directories (the format is unchanged; the jar differs only in the constant).
   - Run `start-dfs.sh`, then `AclLoad set 10000 1000 0 /acl`. Expect 10,000 accepted. Take H3, E3, F3.
6. Optional bypass check:
   - `stop-dfs.sh`, then restart with `hadoop-stock` on the same `nn` directory.
   - The NameNode should load the 1001-int ACLs from fsimage and edits with no error, and `getfacl /acl/d0` should show 1000 named entries (A3, load paths skip the check).
   - Take H4.
7. `stop-dfs.sh`. Confirm with `jps` that no `NameNode`, `DataNode` or `SecondaryNameNode` remains.

**B3f. Predictions.**
- H1 − H0:
  - `AclFeature` instances +10,000 (± a few).
  - `[I` bytes +2.6 MB ± noise. The noise is the spread of the three H0 samples, expected under 0.5 MB.
  - Edits E1 − E0: 10,000 `OP_SET_ACL` ops, each with 64 entries (the full logical ACL is logged).
- H2 − H1: `AclFeature` +0 and `[I` within noise. AclLoad reports 0 accepted and messages "ACL has 33 access entries", then "ACL has 103…", then "1003…". E2 − E1 has 0 `OP_SET_ACL`. F2 ≈ F1.
- H3 − H2 (patched control): `AclFeature` count unchanged, since old features are replaced and dedup keeps them unique. `[I` grows by ≈ 10,000 × (4,024 − 264) ≈ 37.6 MB (the old 61-int arrays are freed, the new 1001-int arrays are live). E3 − E2 ≈ 100–150 MB. F3 − F2 ≈ 10,000 × 1001 × about 1–5 B (varint) ≈ 10–50 MB.
- H4 (stock reload): ≈ H3, and the NameNode starts with no ACL error.
- Ratio test: per-directory growth when rejected (H2 − H1) is 0. With the cap removed (H3 − H2) it is about 1,000 × 4 B. The claim is wrong if H2 − H1 shows growth of more than 0.5 MB, or if any directory's `getfacl` shows more than 28 named entries per scope after phase 2 on stock.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Phase 1 accepted, phase 2 all rejected, H2 ≈ H1, no new `OP_SET_ACL` | Claim confirmed: the cap governs real per-inode heap and edit bytes |
| Phase 2 on stock shows accepted calls or `[I` growth > 0.5 MB | Claim wrong: the cap does not bind on some client path |
| Phase 2 rejected but edits contain `OP_SET_ACL` for those paths | Claim wrong in part: the rejection happens after logging |
| Control H3 − H2 ≈ +37 MB and edits ≈ +100 MB | Positive control moved: without the check the same workload grows usage linearly, so the constant is the binding limit |
| Control did not move (patched build still rejects, or no growth) | Not confirmed: the patch did not take effect (check the jar) or another limit binds; re-trace |
| H4 loads oversized ACLs without error | Confirms the A3 bypass: the cap is write-path-only and not checked on edit or fsimage load |
| H4 fails to load | A load-time check exists that the trace missed; amend A3 |

**B3h. Controls.**
- Three baseline histograms give the noise band.
- The unique `x<i>` name per directory prevents dedup through `UNIQUE_ACL_FEATURES` from masking growth.
- The same D, the same paths and the same client are used across phases.
- A fixed `-Xms` = `-Xmx` heap and `histo:live` (full GC) remove garbage from the readings.
- The patched build differs only in the constant (verify with `unzip -p hadoop-hdfs-3.4.2.jar ...AclTransformation.class | javap`, or by checking that k = 29 is accepted).
- No checkpoint runs mid-phase (period set to 24 h).
- Edits are rolled before each `du`.

**B4. Risks and cleanup.**
- Everything lives under `/mydata/<run>/` on local disk (about 2 GB of edits and fsimage at most), never on shared storage.
- Ports 9000, 9870, 9864, 9866, 9867 and 9868 must be free. Check them with `ss -ltnp` before starting.
- The NameNode heap is capped at 1 GB.
- The Surefire JVM ends with the test, but delete `/mydata/<run>/minidfs` afterwards.
- Cluster cleanup:
  - `stop-dfs.sh` for each `HADOOP_HOME` that was started.
  - `jps` must list no NameNode, DataNode or SecondaryNameNode. Otherwise run `kill <pid>` using `/mydata/<run>/pids/*.pid`.
  - `rm -rf /mydata/<run>/{nn,dn,tmp,logs,pids}` once the readings are copied off.
- Do not run the patched jar against any shared NameNode metadata. Its edit log contains ACLs that stock writers would reject.

## C. Sources read

hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/AclTransformation.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirAclOp.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/AclStorage.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/AclFeature.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/AclEntryStatusFormat.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/SerialNumberManager.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/INodeWithAdditionalFields.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogLoader.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLog.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSImageFormatPBINode.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSNamesystem.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/NameNodeRpcServer.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirectory.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/util/ReferenceCountMap.java
hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/HdfsPermissionsGuide.md
hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestAclTransformation.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DFSClient.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/AclException.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/permission/ScopedAclEntries.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/HarFileSystem.java (name collision check only)
hadoop-common-project/hadoop-common/src/main/resources/core-default.xml (`ipc.maximum.data.length`)
https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/HdfsPermissionsGuide.html (same text as the in-tree markdown; not fetched)
https://issues.apache.org/jira/browse/HDFS-7582 (cited from the code comment; not fetched)

## D. Stage-4 feedback

none yet
