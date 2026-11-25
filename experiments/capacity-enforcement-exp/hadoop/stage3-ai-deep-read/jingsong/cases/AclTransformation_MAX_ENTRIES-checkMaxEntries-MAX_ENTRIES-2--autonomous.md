# AclTransformation_MAX_ENTRIES — `AclTransformation.java:327` — verification solution  <!-- file: cases/AclTransformation_MAX_ENTRIES-checkMaxEntries-MAX_ENTRIES-2--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`AclTransformation.java:327`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/AclTransformation.java#L327) — `if (defaultEntries.size() > MAX_ENTRIES)` in `checkMaxEntries` (the default-scope half; the access-scope twin is line 323) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive` — on every client path that changes an ACL (modify/set/remove ACL entries over RPC or WebHDFS), the NameNode rejects any resulting ACL with more than 32 entries in a scope before it is stored, so the per-inode ACL object kept in NameNode heap (`AclFeature.entries`, an `int[]` of at most 29 + 32 = 61 elements) and the per-operation `OP_SET_ACL` edit-log record and fsimage ACL record are capped. The cap is per inode, not on total NameNode heap (the number of inodes with distinct ACLs is unbounded), the constant cannot be configured, and edit-log replay and fsimage load skip the check. |
| Ground | — |

> Naming note. `MAX_ENTRIES` is also a field name in `HarFileSystem.java:1251`, so the constraint is
> qualified as `AclTransformation_MAX_ENTRIES`. `[function]` = `checkMaxEntries` (the method that
> directly encloses line 327); `[operand]` = `MAX_ENTRIES`.

## A. Constraint trace

**A1. The constraint.**
- Name: `MAX_ENTRIES` in class `org.apache.hadoop.hdfs.server.namenode.AclTransformation`.
- Kind: hard-coded constant (`private static final int`), declared at
  [`AclTransformation.java:64`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/AclTransformation.java#L64)
  (`private static final int MAX_ENTRIES = 32;`). No `*-default.xml` entry and no configuration key.
- Unit: number of ACL entries **per scope** (access scope and default scope are counted separately,
  HDFS-7582), counting every entry of the logical ACL in that scope: owner (`user::`), named users,
  owning group (`group::`), named groups, `mask::`, `other::`.
- Default: 32. Since it is a compile-time constant it is inlined by `javac`; it can only be changed by
  editing the source and rebuilding `hadoop-hdfs` (and restarting the NameNode with the new jar).
  Not settable by `*-site.xml`, `-D`, or any refresh command.
- Related setting (gate, not the limit): `dfs.namenode.acls.enabled` (`DFSConfigKeys.java:373-374`,
  default `true`; `hdfs-default.xml:602-603` `true`; read once in `FSDirectory.java:336-338`, restart
  needed). If `false`, every ACL operation is rejected earlier (`FSDirAclOp.java:200-206`) and the check
  is never reached.
- Read by: the NameNode only (the class is `@InterfaceAudience.Private`, package-private, in the
  `namenode` package). Documented user-side in `HdfsPermissionsGuide.md:224` ("The maximum number is 32
  for access and 32 for default entries which is 64 in total.").

**A2. What it caps.**
- The quantity compared at line 327 is `defaultEntries.size()`, the number of **default-scope** entries
  of an ACL (after sorting; in `buildAndValidateAcl`, after the transformation has added inferred
  default base entries and the automatic default mask). Line 323 does the same for access entries.
- The memory object it bounds: the NameNode-heap `AclFeature` attached to an inode
  (`AclFeature.java:38`, `private final int [] entries`). `AclStorage.createAclFeature`
  (`AclStorage.java:319-337`) stores the access entries except owner, mask and other
  (`subList(1, size-2)`, so at most 32 − 3 = 29) plus **all** default entries (at most 32), one packed
  `int` per entry (`AclEntryStatusFormat.toInt`, `AclEntryStatusFormat.java:114-120`). Hence at most 61
  ints = 16 + 244 → 264 bytes for the array (64-bit JVM, compressed oops) + 24 bytes for the
  `AclFeature` object, per distinct ACL. Identical ACLs are shared through
  `AclStorage.UNIQUE_ACL_FEATURES` (`AclStorage.java:67-68`, a `ReferenceCountMap` backed by a
  `ConcurrentHashMap`, `ReferenceCountMap.java:40`; inodes attach the shared instance via
  `INodeWithAdditionalFields.java:366-371`).
- Disk side of the same object: each accepted change is logged as `OP_SET_ACL` carrying the full new
  ACL (`FSDirAclOp.java:53`, `:144`), and the fsimage stores the same packed ints per inode
  (`fsimage.proto:95-109`, `repeated fixed32 entries`). So the per-inode, per-operation size of those
  records is capped as well.
- What it does **not** cap: total NameNode heap or total edit/fsimage bytes from ACLs; those grow with
  the number of inodes carrying distinct ACLs, which no limit here bounds.

**A3. Mechanism.**
1. Client calls `modifyAclEntries`/`setAcl`/`removeAclEntries`/`removeDefaultAcl` (RPC via
   `FSNamesystem.java:7966-7978`, `:8064`; WebHDFS via the same NameNode RPC methods; the
   `aclspec` WebHDFS parameter has only a syntax regex, `HdfsClientConfigKeys.java:40-41`, no count limit).
2. `FSDirAclOp.modifyAclEntries` (`FSDirAclOp.java:36-60`) takes the write lock, reads the existing
   logical ACL (`AclStorage.readINodeLogicalAcl`; minimal 3 entries for an inode with no ACL) and calls
   `AclTransformation.mergeAclEntries` (`FSDirAclOp.java:50`). `setAcl` goes through
   `unprotectedSetAcl(..., fromEdits=false)` → `replaceAclEntries` (`FSDirAclOp.java:179-195`).
3. **Pre-check on the raw spec.** `mergeAclEntries`/`replaceAclEntries`/`filterAclEntriesByAclSpec`
   first build `new ValidatedAclSpec(inAclSpec)` (`AclTransformation.java:139`, `:201`), which sorts
   the spec and calls `checkMaxEntries(new ScopedAclEntries(aclSpec))` (`AclTransformation.java:462-465`).
   A spec with more than 32 default entries already fails here, at line 327.
4. Transformation: entries are merged/replaced; `copyDefaultsIfNeeded` (`AclTransformation.java:409-438`)
   adds missing `default:user::`, `default:group::`, `default:other::` copied from the access entries
   (up to +3); `calculateMasks` (`AclTransformation.java:355-402`) adds an automatic `default:mask::`
   when named default entries exist (+1). So the stored default ACL can be up to 4 entries larger than
   the spec. The comment at `AclTransformation.java:452-458` says exactly this: the spec check alone is
   insufficient.
5. **Post-check on the result.** `buildAndValidateAcl` (`AclTransformation.java:271-315`) sorts, checks
   duplicates, builds `ScopedAclEntries` and calls `checkMaxEntries` (`AclTransformation.java:291-292`).
   The check:
   [`AclTransformation.java:327`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/AclTransformation.java#L327)
   `if (defaultEntries.size() > MAX_ENTRIES)` (access twin at line 323).
6. Outcomes:
   - `> 32`: throws `AclException("Invalid ACL: ACL has N default entries, which exceeds maximum of 32.")`
     (`AclTransformation.java:328-329`). In `FSDirAclOp` the exception propagates out before
     `AclStorage.updateINodeAcl` and before `logSetAcl` (`FSDirAclOp.java:50-55`), so nothing is
     allocated in the inode, nothing is logged, and the client receives a `RemoteException` wrapping
     `org.apache.hadoop.hdfs.protocol.AclException` with " Path: <src>" appended.
   - `≤ 32`: the ACL is stored (`AclStorage.updateINodeAcl`, `AclStorage.java:270-295` →
     `createAclFeature` → `new AclFeature(int[n])`), deduplicated through `UNIQUE_ACL_FEATURES`, and
     logged.
7. Bypasses / overshoot:
   - Edit-log replay: `FSEditLogLoader.java:975` calls `unprotectedSetAcl(..., true)`; with
     `fromEdits=true` the transformation (and therefore the check) is skipped (`FSDirAclOp.java:192-195`).
   - Fsimage load: `FSImageFormatPBINode.java:184-186` and `:549-551` build `AclFeature` straight from
     the protobuf entries with no count check.
   - Inheritance: `AclStorage.copyINodeDefaultAcl` (`AclStorage.java:76-140`) copies the parent's default
     entries into each new child's access ACL (and, for directories, default ACL) without re-checking;
     this cannot exceed the cap because the parent's default ACL was itself capped (≤ 32 → child access
     feature ≤ 29 + default ≤ 32).
   - So on a NameNode whose namespace was only ever modified through the client path, no stored ACL
     can exceed 32 per scope; a hand-crafted edit log or fsimage could.

**A4. Other consumers.** Of NameNode heap per inode outside this constraint: the inode objects
themselves, the `Feature[]` array that grows by one slot when an `AclFeature` is attached
(`INodeWithAdditionalFields.java:123-124`), the `ConcurrentHashMap` node per distinct `AclFeature`
(k-independent), the global user/group name string tables (`SerialNumberManager`, names packed as a
24-bit id, `AclEntryStatusFormat.java:42`), xattrs (separately limited), and the edit-log/fsimage
bytes of everything else. The number of inodes is not limited here. RPC payload size is bounded
separately by `ipc.maximum.data.length` (`core-default.xml:2585-2586`, 128 MiB) — without
`MAX_ENTRIES` that would be the only ceiling on one ACL.

**A5. Evidence beyond the source.**
- `hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/HdfsPermissionsGuide.md:224` (32 access + 32
  default); published at https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/HdfsPermissionsGuide.html
- HDFS-7582 (per-scope counting, cited in the code comment at `AclTransformation.java:317-318`):
  https://issues.apache.org/jira/browse/HDFS-7582 (not opened; relied on only via the in-tree comment).
- Existing tests: `TestAclTransformation.java:45-53` (`ACL_SPEC_TOO_LARGE`, `ACL_SPEC_DEFAULT_TOO_LARGE`,
  33 entries), `:352`, `:363`, `:731`, `:741`, `:1131`, `:1141`, and `testReplaceAclEntriesResultTooLarge`
  (`:1144-1161`, 32-entry spec pushed to 33 by the automatic mask). `FSAclBaseTest.java:89-93` shows how
  to start a `MiniDFSCluster` with ACLs enabled.

## B. Verification solution

**B1. Claim under test.** Through the normal client path, the NameNode stores an ACL only if each
scope has at most 32 entries: for a fresh directory and a spec of `k` named default-user entries, the
stored default ACL has `k + 4` entries, `k ≤ 28` is accepted and allocates exactly one `AclFeature`
whose `int[]` has `k + 4` elements (heap and fsimage/edit bytes rising about 4 bytes per entry), while
every `k ≥ 29` is rejected with no heap, edit-log or fsimage growth for that inode. Shown wrong if any
stored default ACL ever exceeds 32 entries, if a `k ≥ 29` request succeeds, or if a rejected request
still leaves an `AclFeature` / `OP_SET_ACL` behind.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 8, Maven ≥ 3.3. Copy the tree to local disk (not the shared tree):
  `rsync -a ~/hadoop-3.4.2/ $WORK/hadoop-src/` with `$WORK` on local disk with ≥ 15 GB free.
- Build: `cd $WORK/hadoop-src && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
- New test file (in the copy only):
  `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestAclMaxEntriesProbe.java`,
  package `org.apache.hadoop.hdfs.server.namenode` (needed to reach the package-private
  `AclTransformation`, `FSDirAclOp`, `AclFeature.getEntriesSize()`, `FSDirectory.writeLock()`).
  Use the static helper `AclTestHelpers.aclEntry(scope, type, name, perm)` (same package).
- Run: `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestAclMaxEntriesProbe -DfailIfNoTests=false`.
  Default surefire heap is fine. Print every reading with `System.out.println("READING ...")` and read
  `target/surefire-reports/org.apache.hadoop.hdfs.server.namenode.TestAclMaxEntriesProbe-output.txt`.

**B2b. Knobs.**
- Primary (workload-side, since the constant is fixed): `k` = number of named default-user entries in
  the spec, swept over `1..40` in U1 and `{8, 16, 28, 29, 32, 33, 40}` in U2. 28 is the last accepted
  value (28 + 4 = 32), 29–32 isolate the post-transformation call at line 292 (spec passes the
  pre-check, result 33–36 does not), 33+ hit the pre-check at line 464. The same sweep on access-scope
  entries (`ACCESS, USER, "u"+i`) exercises the twin at line 323.
- Optional constraint knob: a second local copy with `AclTransformation.java:64` edited to
  `MAX_ENTRIES = 16` (rebuild `hadoop-hdfs` only, `mvn -pl hadoop-hdfs-project/hadoop-hdfs install -DskipTests`).
  Shows the acceptance boundary moves with the constant (last accepted `k` = 12). Never edit the
  shared tree.

**B2c. Workload.**
- U1 (pure transformation, no cluster): `existing = [ACCESS USER ALL, ACCESS GROUP READ_EXECUTE,
  ACCESS OTHER READ_EXECUTE]` (what `readINodeLogicalAcl` returns for a plain directory); spec =
  `k` entries `aclEntry(DEFAULT, USER, "u"+i, READ_EXECUTE)`, `i = 0..k-1`, in a fresh `ArrayList`
  (the call sorts it in place). Call `AclTransformation.mergeAclEntries(existing, spec)` and,
  separately, `replaceAclEntries(existing, spec)`. Arithmetic: result default scope = `k` named +
  `default:user::` + `default:group::` + `default:other::` (copied, lines 409-438) + `default:mask::`
  (lines 355-402) = `k + 4`; limit 32 reached at `k = 28`, passed at `k = 29`.
- U2 (in-JVM NameNode): `MiniDFSCluster` with `numDataNodes(0)` and
  `dfs.namenode.acls.enabled=true`. For each `k`: `fs.mkdirs(new Path("/u2/k"+k))`, then
  `fs.modifyAclEntries(path, spec_k)` through `DistributedFileSystem` (real RPC client path). Then read
  `cluster.getNamesystem().getFSDirectory().getINode("/u2/k"+k).getAclFeature()`.
  Distinct-ACL variant: repeat for `M = 1000` directories `/u2b/k<k>/d<j>`, with entry `i < 4` given
  permission `FsAction.values()[(j >> (3*i)) & 7]` so every directory's ACL differs (8^4 = 4096 > 1000).
- U3 (bypass probe, control): under `fsd.writeLock()`, call
  `FSDirAclOp.unprotectedSetAcl(fsd, fsd.getINodesInPath("/u3", DirOp.WRITE), list, true)` on an
  existing directory `/u3` with a sorted list of 3 access base entries + `default:user::`, 40 named
  default users, `default:group::`, `default:mask::`, `default:other::` (44 default entries), then
  `fsd.writeUnlock()`.

**B2d. Observables and instruments.**
- U1: on success, `new ScopedAclEntries(result).getDefaultEntries().size()` (and access size); on
  failure, the `AclException` message and the top `AclTransformation` frames of its stack trace
  (`checkMaxEntries` called from `buildAndValidateAcl` vs from `ValidatedAclSpec.<init>`).
- U2: `AclFeature.getEntriesSize()` (exact length of the `int[]`); `fs.getAclStatus(path).getEntries().size()`;
  `AclStorage.getUniqueAclFeatures().size()` before/after (number of distinct `AclFeature`s);
  computed array bytes `align8(16 + 4·n)`. For the distinct variant also
  `MemoryMXBean.getHeapMemoryUsage().getUsed()` after `System.gc()` ×3 before/after (coarse, supporting
  only).
- Not directly observable here: real NameNode process heap/RSS and on-disk edits/fsimage (cluster tier).

**B2e. Procedure.**
1. Copy and build (B2a).
2. Write the test with three `@Test` methods `u1Sweep`, `u2Cluster`, `u3ReplayBypass`; `@BeforeClass`
   starts the `MiniDFSCluster` (as in `FSAclBaseTest.java:89-93` with `numDataNodes(0)`), `@AfterClass`
   shuts it down. Each U1/U2 call is wrapped in try/catch so every `k` produces a reading.
3. Run (B2a command). Collect `READING` lines.
4. Optional: in the `MAX_ENTRIES = 16` copy, run `u1Sweep` only.
5. Remove the test's `target/test/data` dir in the copy when done; no daemons remain (in-JVM only).

**B2f. Predictions.**

| k (named default users) | spec size | result default size | U1 outcome | thrown from | U2 `getEntriesSize()` | int[] bytes |
|---|---|---|---|---|---|---|
| 1 | 1 | 5 | accepted | — | 5 | 40 |
| 8 | 8 | 12 | accepted | — | 12 | 64 |
| 16 | 16 | 20 | accepted | — | 20 | 96 |
| 28 | 28 | 32 | accepted | — | 32 | 144 |
| 29 | 29 | 33 | rejected "has 33 default entries" | `buildAndValidateAcl` → line 327 | no feature (null) | 0 |
| 32 | 32 | 36 | rejected "has 36 default entries" | `buildAndValidateAcl` → line 327 | null | 0 |
| 33 | 33 | — | rejected "has 33 default entries" | `ValidatedAclSpec.<init>` → line 327 | null | 0 |
| 40 | 40 | — | rejected "has 40 default entries" | `ValidatedAclSpec.<init>` → line 327 | null | 0 |

- Access-scope sweep: same boundary (k ≤ 28 accepted, result `k + 4`), message "access entries",
  line 323; U2 `getEntriesSize()` for accepted access-only ACLs = `k + 1` (named users + owning group;
  owner/mask/other live in the permission bits).
- U2 distinct variant: `getUniqueAclFeatures().size()` rises by exactly `M = 1000` for each accepted `k`
  and by 0 for each rejected `k`; heap-used delta for `k = 28` minus `k = 8` ≈ 1000 × 80 B ≈ 80 KB
  (coarse, may be lost in noise — supporting only).
- `MAX_ENTRIES = 16` copy: last accepted `k = 12`, `k = 13` rejected "has 17 default entries".
- U3: succeeds; `getEntriesSize() = 44` (> 32) — the replay path is unchecked.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Table B2f reproduced (accepted ≤ 28, stored size `k + 4` ≤ 32; rejected ≥ 29 with no `AclFeature`) | Claim confirmed at the mechanism level |
| Any accepted call with stored default size > 32, or `getEntriesSize()` > 32 after a client call | Claim wrong: the check does not cap the stored ACL |
| `k = 29..32` accepted (only spec-level check active) | Claim wrong for line 327's post-transformation role; the effective cap would be 32 + 4 |
| A rejected `k` still leaves an `AclFeature` on the inode or raises `getUniqueAclFeatures().size()` | Claim wrong: rejection happens after allocation |
| `getUniqueAclFeatures()` rises by 1 instead of M in the distinct variant | Workload error (ACLs not distinct); fix the permission encoding before reading heap |
| U3 shows 44 entries | Expected: confirms replay bypass (A3.7); does not refute the client-path claim |
| U3 throws at line 327 | A3.7 bypass statement wrong (replay also checked) — record it |
| `MAX_ENTRIES = 16` copy boundary does not move to 12 | The boundary comes from somewhere else; claim about this constant wrong |

**B2h. Controls.**
- `k = 8, 16, 28` accepted values are the positive control: they show the probe does allocate an
  `AclFeature` growing 4 bytes per entry, so the zero for rejected `k` is a real refusal, not a broken probe.
- Same `k` on access scope (line 323) separates the two branches of `checkMaxEntries`.
- Stack-frame check separates the pre-check (line 464) from the post-check (line 292), so line 327's
  post-transformation role is exercised specifically by `k = 29..32`.
- `dfs.namenode.acls.enabled=true` set explicitly so an `AclException` cannot come from the config gate
  (its message differs: "Support for ACLs has been disabled").
- U3 shows the measured object can exceed 32 when the check is skipped, so the cap seen on the client
  path is due to the check, not to some other structural limit.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux host (pseudo-distributed HDFS only; YARN not needed). JDK 8 (or 11 to run).
- Build the distribution in the local copy:
  `cd $WORK/hadoop-src && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`;
  use `hadoop-dist/target/hadoop-3.4.2` as `$HADOOP_HOME`.
- `$RUN` = a fresh directory on local disk (≥ 2 GB free), e.g. `/mydata/<you>/acl-max`.
- `$HADOOP_HOME/etc/hadoop/hadoop-env.sh` (or exported): `HADOOP_LOG_DIR=$RUN/logs`,
  `HADOOP_PID_DIR=$RUN/pids`, `HADOOP_HEAPSIZE_MAX=1g`,
  `HDFS_NAMENODE_OPTS="-Xms1g -Xmx1g"` (fixed heap so GC sizing does not change between readings).
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=$RUN/tmp`.
- `hdfs-site.xml`: `dfs.replication=1`, `dfs.namenode.name.dir=file://$RUN/name`,
  `dfs.datanode.data.dir=file://$RUN/data`, `dfs.namenode.acls.enabled=true` (explicit),
  `dfs.webhdfs.enabled=true` (default), `dfs.namenode.checkpoint.dir=file://$RUN/snn` (unused).
- Daemons: NameNode and one DataNode (`hdfs --daemon start namenode|datanode`); no SecondaryNameNode.
  Ports 9000, 9870 (NN HTTP/WebHDFS), 9866/9864/9867 (DN) must be free.
- Client: `hdfs dfs` for boundary points and `python3` (stdlib `urllib`) as a WebHDFS driver for the
  bulk heap runs.

**B3b. Knobs.**
- `k` ∈ {0 (dirs only, baseline), 8, 16, 28, 29, 32, 33} named default-user entries per directory,
  applied by `MODIFYACLENTRIES` (= `hdfs dfs -setfacl -m`). Changing `k` needs no restart.
- `MAX_ENTRIES` itself is fixed at 32 in this distribution (not configurable; A1). Optional: a second
  distribution from the `MAX_ENTRIES = 16` copy (B2b) run with k ∈ {12, 13}; requires NameNode restart
  with that build.
- `M = 20,000` directories per `k` (enough for a clear heap and fsimage signal, see B3c).

**B3c. Workload.**
- Boundary points (CLI, one directory each):
  `hdfs dfs -mkdir -p /b/k$k` then
  `hdfs dfs -setfacl -m "$(python3 -c "print(','.join('default:user:u%d:r-x'%i for i in range($k)))")" /b/k$k`
  for k ∈ {28, 29, 32, 33}; then `hdfs dfs -getfacl /b/k$k`.
- Bulk (per k): create `M` directories `/acl/k$k/d$j` (`j = 0..M-1`) via WebHDFS `MKDIRS`, take the
  heap histogram, then send one `MODIFYACLENTRIES` per directory with spec
  `default:user:u0:P0,...,default:user:u{k-1}:P{k-1}` where `P_i` = rwx string of digit
  `(j >> 3i) & 7` for `i < 5` and `r-x` for `i ≥ 5` (8^5 = 32,768 > M ⇒ every ACL distinct, so no
  dedup). Driver (`$RUN/drive.py`, run with `python3 -I`; the parent path is an argument):
  ```python
  import sys, urllib.request, urllib.error, collections
  parent, k, M, phase, user = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5]
  # phase: mkdir | acl (distinct ACL per dir) | acl-same (one ACL for all dirs)
  P = ["---", "--x", "-w-", "-wx", "r--", "r-x", "rw-", "rwx"]
  codes, last = collections.Counter(), None
  for j in range(M):
      if phase == "mkdir":
          q = "op=MKDIRS"
      else:
          jj = 0 if phase == "acl-same" else j
          spec = ",".join("default:user:u%d:%s" % (i, P[(jj >> (3 * i)) & 7] if i < 5 else "r-x")
                          for i in range(k))
          q = "op=MODIFYACLENTRIES&aclspec=" + spec
      url = "http://localhost:9870/webhdfs/v1%s/d%d?%s&user.name=%s" % (parent, j, q, user)
      try:
          codes[urllib.request.urlopen(urllib.request.Request(url, method="PUT")).status] += 1
      except urllib.error.HTTPError as e:
          codes[e.code] += 1; last = e.read()[:300]
  print("parent=%s k=%d M=%d phase=%s codes=%s" % (parent, k, M, phase, dict(codes)))
  if last: print("last error body:", last)
  ```
- Arithmetic: stored default ACL per accepted directory = `k + 4` entries ⇒ `int[k+4]` =
  align8(16 + 4(k+4)) bytes: k=8 → 64 B, k=16 → 96 B, k=28 → 144 B. Over M = 20,000: 1.28 MB, 1.92 MB,
  2.88 MB of `[I`; plus k-independent `AclFeature` 24 B, `Feature[1]` 24 B, CHM node 32 B per directory
  (≈ 1.6 MB). Rejected k (29, 32, 33): 0. Each phase is ~20,000 HTTP calls, a few minutes.

**B3d. Observables and instruments.**
- Heap object counts/bytes: `jcmd <nn-pid> GC.class_histogram > $RUN/histo-<k>-<phase>.txt` (forces a
  full GC; live objects only). Read rows `org.apache.hadoop.hdfs.server.namenode.AclFeature`
  (instances, bytes), `[I` (bytes), `[Lorg.apache.hadoop.hdfs.server.namenode.INode$Feature;`.
  Taken after the mkdir phase and after the ACL phase of each k; the difference isolates ACL heap.
- Process-level heap: `jstat -gc <nn-pid>` old-gen used (`OU`) right after each histogram (which ran a
  full GC); and `/proc/<nn-pid>/status` `VmRSS` (context only; RSS does not shrink and is dominated by
  the fixed 1 g heap).
- NameNode JMX: `curl -s 'http://localhost:9870/jmx?qry=java.lang:type=Memory'` (`HeapMemoryUsage.used`)
  as a cross-check.
- Edit log: after the runs, `hdfs dfsadmin -rollEdits`, then `hdfs oev -i <finalized edits_* segment> -o $RUN/oev-<n>.xml`
  for each segment; count `OP_SET_ACL` records whose path is under each `/acl/k$k` and the `<ENTRY>`
  elements per record. Plus `du -b $RUN/name/current` before/after each ACL phase.
- Fsimage: after all runs, `hdfs dfsadmin -safemode enter && hdfs dfsadmin -saveNamespace && hdfs dfsadmin -safemode leave`;
  `ls -l $RUN/name/current/fsimage_*` and `hdfs oiv -p XML -i <fsimage> -o $RUN/oiv.xml`, count ACL
  entries under each `/acl/k$k` (ACL entries per inode). A fsimage saved right after the k=0 baseline
  (same commands) gives the comparison point.
- Client side: HTTP status counts from the driver; CLI exit code and stderr for the boundary points;
  `hdfs dfs -getfacl` line count.
- Not observable directly: the retained size of an individual `AclFeature` (histogram aggregates per
  class); per-inode attribution in the fsimage beyond the `oiv` dump.

**B3e. Procedure.**
1. Build distribution (B3a), write configs, `hdfs namenode -format -nonInteractive`
   (name dir under `$RUN`), `hdfs --daemon start namenode`, `hdfs --daemon start datanode`, wait for
   `hdfs dfsadmin -safemode get` = OFF. `NN=$(jps | awk '/ NameNode$/{print $1}')`. Check the NN log
   for "ACLs enabled? true".
2. Boundary points (B3c CLI) for k ∈ {28, 29, 32, 33}; record exit code, error message, `getfacl` output.
3. For k in 0 8 16 28 29 32 33:
   `hdfs dfs -mkdir -p /acl/k$k`; `python3 -I $RUN/drive.py /acl/k$k $k 20000 mkdir $USER` →
   `jcmd $NN GC.class_histogram > $RUN/histo-$k-mkdir.txt`; `jstat -gc $NN`; `du -b $RUN/name/current`.
   If k = 0: `saveNamespace` (B3d) for the baseline fsimage.
   If k > 0: `python3 -I $RUN/drive.py /acl/k$k $k 20000 acl $USER` → `histo-$k-acl.txt`, `jstat -gc`, `du -b`.
4. Dedup control: `/acl/k28same`, k = 28, `mkdir` then `acl-same`; histograms as in step 3.
5. `hdfs dfsadmin -rollEdits`; `hdfs oev` on the finalized segments; count `OP_SET_ACL` per prefix.
6. `saveNamespace` (B3d) and `hdfs oiv` dump; record fsimage size and per-prefix ACL entry counts.
7. Optional: restart the NameNode (`hdfs --daemon stop namenode; hdfs --daemon start namenode`) and
   confirm `getfacl /b/k28` still shows 32 default entries (loaded through the unchecked fsimage path,
   A3.7, but values came from checked writes).
8. Cleanup (B4).

**B3f. Predictions.** (Δ = ACL phase minus mkdir phase of the same k; M = 20,000.)

| k | driver codes | Δ AclFeature instances | Δ `[I` bytes (≈) | `OP_SET_ACL` records / entries per record | fsimage ACL entries per dir |
|---|---|---|---|---|---|
| 0 | — (no ACL phase) | 0 | 0 | 0 | 0 |
| 8 | 20,000 × 200 | +20,000 | +1.28 MB | 20,000 / 15 (3 access + 12 default) | 12 |
| 16 | 20,000 × 200 | +20,000 | +1.92 MB | 20,000 / 23 | 20 |
| 28 | 20,000 × 200 | +20,000 | +2.88 MB | 20,000 / 35 | 32 |
| 29 | 20,000 × non-2xx, body `AclException` "has 33 default entries" | 0 | ≈ 0 | 0 | 0 |
| 32 | 20,000 × non-2xx, "has 36 default entries" | 0 | ≈ 0 | 0 | 0 |
| 33 | 20,000 × non-2xx, "has 33 default entries" | 0 | ≈ 0 | 0 | 0 |
| 28same | 20,000 × 200 | +1 | ≈ +144 B (plus `Feature[]` arrays in their own row) | 20,000 / 35 | 32 |

- Relation: Δ`[I` grows linearly in `k` among accepted values with slope ≈ M × 4 B (k=28 minus k=8 ≈
  1.6 MB); it is flat at ≈ 0 for every k ≥ 29. Δ old-gen used tracks Δ`[I` + ≈ M × 80 B
  (k-independent objects) for accepted k, and ≈ 0 for rejected k.
- Fsimage: grows from the k=0 baseline by roughly M × (4·(k+4) + a few bytes protobuf framing) per
  accepted k (k=28 ⇒ ≈ 2.6–2.8 MB), not at all for rejected k. Edits: each accepted request appends one
  `OP_SET_ACL` whose size grows with the entry count (names are written as strings in the edit op);
  rejected requests append nothing.
- CLI: `-setfacl` at k=28 exits 0 and `getfacl` lists 32 `default:` lines; at k=29/32/33 exits non-zero
  with "Invalid ACL: ACL has N default entries, which exceeds maximum of 32. Path: /b/k..".
- The claim is wrong if any accepted directory shows > 32 default entries, any k ≥ 29 request
  returns 200, or a rejected k shows Δ AclFeature > 0 or `OP_SET_ACL` records.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Table B3f reproduced | Claim confirmed: the NameNode's stored ACL (heap, edits, fsimage) is capped at 32 per scope |
| Any k ≥ 29 accepted, or `getfacl` > 32 default lines | Claim refuted: the cap is not enforced on the client path |
| Rejected k shows Δ AclFeature or Δ `[I` near the accepted slope | Claim refuted: memory is consumed before/despite rejection |
| Accepted k shows Δ AclFeature ≈ +1 instead of +M | Dedup collapsed the workload (ACLs not distinct); heap reading invalid, fix spec encoding |
| Δ`[I` noisy but AclFeature counts exact | Use the instance counts and `oiv` entry counts as the primary reading; heap bytes supporting |
| Accepted k=8/16/28 do not move heap or fsimage (positive control did not move) | Instruments not sensitive; claim not confirmed either way |
| 28same moves +1 AclFeature while 28 moves +M | Confirms the measured object is the per-distinct-ACL feature |
| Optional MAX_ENTRIES=16 build: k=12 accepted, k=13 rejected | Boundary follows the constant |

**B3h. Controls.**
- k = 0 directories-only phase gives the baseline heap and fsimage; every heap reading is a difference
  against the mkdir phase of the same k, so inode costs cancel.
- Accepted k (8, 16, 28) are the positive control: the same workload and instruments show heap,
  edits and fsimage moving where storage is allowed; rejected k must stay flat against them.
- Dedup control (28same) separates "per distinct ACL" from "per inode" costs.
- `dfs.namenode.acls.enabled=true` explicit and checked in the NN log ("ACLs enabled? true",
  `FSDirectory.java:339`), so rejections cannot come from the gate.
- Error message text distinguishes line 327 (default) from line 323 (access) and from other ACL
  validation errors (duplicates, missing mask).
- Fixed `-Xms1g -Xmx1g` and `GC.class_histogram` (full GC) before each reading reduce GC-timing noise.

**B4. Risks and cleanup.**
- Disk: < 1 GB under `$RUN` (namespace, edits, a few-MB fsimage, logs, histograms, `oev`/`oiv` XML);
  build tree ≈ 10–15 GB under `$WORK`. Never on shared storage, never in the shared source tree.
- Memory: NameNode 1 GB heap, DataNode default; unit tier one surefire JVM.
- Ports: 9000, 9870, 9866, 9864, 9867 — check with `ss -ltn` before starting; pick others in the site
  files if busy.
- Cleanup: `hdfs --daemon stop datanode; hdfs --daemon stop namenode`; `jps` must show no `NameNode`,
  `DataNode` (and no surefire `ForkedBooter` from the unit tier); then `rm -rf $RUN` (after copying
  results out) and, when no longer needed, `$WORK/hadoop-src`.

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/AclTransformation.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirAclOp.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/AclStorage.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/AclFeature.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/AclEntryStatusFormat.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/INodeWithAdditionalFields.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogLoader.java (line 975)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogOp.java (SetAclOp entries)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSImageFormatPBINode.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirectory.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSNamesystem.java (modifyAclEntries, setAcl)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/SerialNumberManager.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/util/ReferenceCountMap.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
- hadoop-hdfs-project/hadoop-hdfs/src/main/proto/fsimage.proto
- hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/HdfsPermissionsGuide.md
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestAclTransformation.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/FSAclBaseTest.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/web/resources/AclPermissionParam.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/HdfsClientConfigKeys.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/AclException.java
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/permission/ScopedAclEntries.java (located)
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/HarFileSystem.java (line 1251, name collision only)
- hadoop-common-project/hadoop-common/src/main/resources/core-default.xml (ipc.maximum.data.length)
- BUILDING.txt
- https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/HdfsPermissionsGuide.html (cited, same text as the in-tree markdown)
- https://issues.apache.org/jira/browse/HDFS-7582 (cited via the code comment; not opened)

## D. Stage-4 feedback

none yet
