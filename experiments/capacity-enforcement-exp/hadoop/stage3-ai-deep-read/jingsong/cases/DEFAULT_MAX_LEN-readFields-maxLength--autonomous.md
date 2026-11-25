# DEFAULT_MAX_LEN — verification solution  <!-- file: cases/DEFAULT_MAX_LEN-readFields-maxLength--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`Text.java:357`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/Text.java#L357) — `} else if (newLength >= maxLength) {` in `Text.readFields(DataInput in, int maxLength)` (row unit; no helper) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | agent, 2026-11-24 |
| Estimate | `positive` — the check rejects a length prefix ≥ `maxLength` before `readWithKnownLength` allocates `new byte[len]`, so the heap allocated for one deserialized delegation-token identifier field (owner, renewer, realUser) is capped below `Text.DEFAULT_MAX_LEN` = 1 MiB, regardless of the length the (untrusted) input claims. The capped object is small (≤ 1 MiB per field), but it is a daemon-heap allocation that would otherwise follow an attacker-chosen length up to ~2 GiB. |
| Ground | — |

Name parts: constraint `DEFAULT_MAX_LEN` (constant, unique in the tree, so not class-qualified),
function `readFields` (the overload `readFields(DataInput, int)` that encloses the check),
operand `maxLength` (as written at the check).

## A. Constraint trace

**A1. The constraint.**
- Name: `Text.DEFAULT_MAX_LEN` (`org.apache.hadoop.io.Text`).
- Kind: hard-coded constant (`static final public int`), not a configuration key.
- Declared: [`Text.java:549`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/Text.java#L549) — `static final public int DEFAULT_MAX_LEN = 1024 * 1024;`. No `*-default.xml` entry.
- Unit: bytes (UTF-8 encoded length of one `Text` field). Value 1048576. Because the check is
  `newLength >= maxLength`, the largest accepted field is 1048575 bytes.
- How it reaches the check: the `maxLength` parameter of `Text.readFields(DataInput, int)`
  (Text.java:352). In the pinned tree the only production callers of that overload are
  `AbstractDelegationTokenIdentifier.readFields` for `owner`, `renewer` and `realUser`
  (AbstractDelegationTokenIdentifier.java:196-198), each passing `Text.DEFAULT_MAX_LEN`.
  (`grep -rn "readFields(.*DEFAULT_MAX_LEN"` finds no other.)
- How it can be set: not settable (compile-time constant; changing it means rebuilding
  hadoop-common). The `maxLength` argument itself can be any int for a direct caller of the
  public method, which is what the unit tier varies.
- Who reads it: any JVM that deserializes a Writable-format `AbstractDelegationTokenIdentifier`
  (HDFS `DelegationTokenIdentifier`, MapReduce/JHS `MRDelegationTokenIdentifier`, the web
  `DelegationTokenIdentifier` used by KMS/HttpFS, old-format YARN identifiers): the NameNode on
  `renewDelegationToken`/`cancelDelegationToken` RPCs and on SASL DIGEST token auth
  (SaslRpcServer.java:197), on edit-log replay of token ops (FSEditLogOp.java:3103-3104,
  3182-3183, 3253), and clients (`Token.decodeIdentifier`, Token.java:165-176; `hadoop dtutil print`).

**A2. What it caps.** Daemon (or client) heap: the `byte[]` that `Text.readWithKnownLength`
allocates to hold one identifier field. The quantity compared against the limit is `newLength`,
the variable-length int read from the stream (Text.java:353) — i.e. the length the serialized data
*claims*, not the number of bytes actually present.

**A3. Mechanism.**
1. A token identifier arrives as raw bytes (e.g. `TokenProto.identifier` in an RPC,
   PBHelperClient.java:1738-1743, no decoding there). The secret manager wraps them in a
   `DataInputStream` and calls `id.readFields(in)` on a fresh identifier
   (AbstractDelegationTokenSecretManager.java:592-597 renew, 654-659 cancel).
2. `AbstractDelegationTokenIdentifier.readFields` checks the version byte, then calls
   `owner.readFields(in, Text.DEFAULT_MAX_LEN)` and the same for renewer and realUser
   (AbstractDelegationTokenIdentifier.java:190-198).
3. `Text.readFields(in, maxLength)` reads `newLength = WritableUtils.readVInt(in)`
   (Text.java:353). Negative → `IOException` (Text.java:354-356).
   **The check**: [`Text.java:357`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/Text.java#L357)
   `else if (newLength >= maxLength)` → `IOException("tried to deserialize <n> bytes of data, but maxLength = <max>")`
   (Text.java:357-360). Nothing has been allocated for the field yet.
4. Otherwise `readWithKnownLength(in, newLength)` (Text.java:361, 383-388) calls
   `ensureCapacity(len)` (Text.java:319-335), which for a fresh `Text` (`bytes = EMPTY_BYTES`,
   Text.java:79-81) allocates `new byte[max(len, 1.5*0)] = new byte[len]` (Text.java:327-331),
   **then** `in.readFully(bytes, 0, len)`. So without the check, a short input that claims a large
   length triggers the full allocation before the `EOFException`; with it, the per-field
   allocation is ≤ 1048575 bytes.
- Outcomes at the limit: claimed length ≥ 1048576 → `IOException`, the identifier is not
  built; on the NameNode the RPC fails with that message and nothing else changes.
- Overshoot / bypass:
  - Per field, not per identifier: up to 3 × (1 MiB − 1) per identifier, plus whatever later
    fields allocate.
  - Writer/reader mismatch: `AbstractDelegationTokenIdentifier.write` refuses only lengths
    `> DEFAULT_MAX_LEN` (lines 219-227), so a field of exactly 1048576 bytes is written but cannot
    be read back (`>=` at the check). Not a memory issue; noted as an observable in B2.
  - A caller using `Text.readFields(DataInput)` (Text.java:346-349) goes straight to
    `readWithKnownLength` with no cap (only `ensureCapacity`'s `ARRAY_MAX_SIZE` bound,
    Text.java:77, 328).
  - YARN `YARNDelegationTokenIdentifier.readFields` parses protobuf first (lines 53-67) and only
    the old-format fallback (line 70-72) reaches this check.

**A4. Other consumers.** Same heap, outside this constraint:
- `Token.readFields` allocates `identifier` and `password` with unbounded vint lengths and reads
  `kind`/`service` via the uncapped `Text.readFields(DataInput)` (Token.java:308-320) — credential
  files and Writable-serialized tokens.
- On the RPC path the identifier bytes themselves are bounded by the IPC frame limit
  `ipc.maximum.data.length` (134217728, core-default.xml:2585-2586), and the RPC buffers/protobuf
  copies of those bytes are allocated before the check runs.
- `Text.readString(in, maxLength)` has its own bound via `WritableUtils.readVIntInRange`
  (Text.java:566-572), used with `DEFAULT_MAX_LEN` by `PermissionStatus` (PermissionStatus.java:98-99)
  and distcp's `CopyListingFileStatus` — a different check line.
- All other NameNode heap (namespace, block map, RPC queues).

**A5. Evidence beyond the source.** In-tree test `TestDelegationToken#testOverlongDtidSerialization`
(hadoop-common/src/test/java/org/apache/hadoop/security/token/delegation/TestDelegationToken.java:602-614,
round-trip helper 573-590) expects a round trip with a field of `DEFAULT_MAX_LEN + 1` bytes to
fail. No JIRA or doc relied on (the introducing JIRA was not identified in the release notes under
`hadoop-common/src/site/markdown/release/`).

## B. Verification solution

**B1. Claim under test.** When an `AbstractDelegationTokenIdentifier` (here the HDFS
`DelegationTokenIdentifier`) is deserialized, the heap allocated for its owner field follows the
claimed length up to 1048575 bytes and is not allocated at all for a claimed length ≥ 1048576
(`Text.DEFAULT_MAX_LEN`), however large the claim; in a running NameNode, a 1 GiB claim in a
cancel-token RPC is rejected with the `maxLength = 1048576` message and causes no ~1 GiB
allocation or `OutOfMemoryError`. The claim is wrong if allocation for a claim ≥ 1048576 is
≥ the claim (or an OOM occurs), or if a claim of 1048575 is rejected.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 8 (build and test), Maven 3.3+. Copy the tag to local
disk (`rsync -a <source>/ /mydata/<run>/hadoop-src/`), never build in the shared tree. Then
`cd /mydata/<run>/hadoop-src && mvn -pl hadoop-common-project/hadoop-common -am install -DskipTests -Dmaven.javadoc.skip=true`.
New test file:
`hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/io/TestTextMaxLenProbe.java`.
Run it with a reduced heap so an uncapped 1 GiB claim cannot be satisfied:
`mvn -pl hadoop-common-project/hadoop-common test -Dtest=TestTextMaxLenProbe -Dmaven-surefire-plugin.argLine="-Xmx512m"`
(the property is defined in hadoop-project/pom.xml:187 and used at :2469).
*Amendment (stage-4 audit, 2026-11-25, A1):* on a node set up per the Hadoop stage-4 `environment.md` (§2–3), the
local copy is made with `copy-source.sh /mydata/jingsong-s4/<stem>-run1/hadoop-src`, and the `-am install` step is
skipped: every module is already in `~/.m2/repository` as `3.4.2` from the node's full base build of the same source,
so `mvn -pl hadoop-common-project/hadoop-common test ...` compiles hadoop-common and its tests in the copy and resolves
the rest from `~/.m2` (and does not overwrite the shared artifacts). The `-Xmx512m` override is checked by the
1 GiB uncapped control: under the default `-Xmx2048m` that control would not throw `OutOfMemoryError`.

**B2b. Knobs.**
- `maxLength` passed directly to `Text.readFields(in, maxLength)`: 1024, 1048576
  (= `DEFAULT_MAX_LEN`), 67108864 (64 MiB) — shows the allocation bound moves with the limit.
- Claimed length `L` relative to the limit `M`: `M-1`, `M`, `M+1`, and 1073741824 (1 GiB, more
  than the 512 MiB heap).
- Real caller (limit fixed at `DEFAULT_MAX_LEN`): owner `L` ∈ {524288, 1048575, 1048576, 1073741824}.

**B2c. Workload.** Crafted byte streams, built with `DataOutputBuffer`:
- Direct: `WritableUtils.writeVInt(out, L)` then `A` payload bytes, where `A = L` for
  `L < M` with `L ≤ 64 MiB` (complete field) and `A = 8` otherwise (short input — the dangerous
  case, since allocation happens before `readFully`).
- Real caller: `new org.apache.hadoop.security.token.delegation.web.DelegationTokenIdentifier(new Text("PROBE"))`
  (hadoop-common main code, extends `AbstractDelegationTokenIdentifier`), `readFields` on
  `[byte 0 (VERSION, AbstractDelegationTokenIdentifier.java:41)][vint L][A owner bytes]` followed,
  when `A = L`, by `vint 0` (renewer), `vint 0` (realUser), `vlong 0`, `vlong 0`, `vint 0`, `vint 0`.
  With `A = 8` the stream ends early on purpose.
- Arithmetic: 1 GiB claim > `-Xmx512m`, so if it were allocated the test JVM throws
  `OutOfMemoryError`; 1048575 ≪ 512 MiB, so an accepted claim always fits.

**B2d. Observables and instruments.**
- Bytes allocated by the test thread around each `readFields` call:
  `((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId())`
  before and after; subtract a baseline measured on the same call with `L = 0`
  (exception objects and message strings, expected < 64 KiB). Repeat each case 5 times, report the median.
- Outcome: exception class and message, or for success `owner.getLength()`/`text.getLength()`.
- Not directly observable: which array was allocated (inferred from the size, since one `byte[L]` dominates).

**B2e. Procedure.**
1. Build per B2a.
2. Write `TestTextMaxLenProbe` with: helper `long allocDelta(Callable<?>)` (catches `Throwable`,
   returns delta and outcome); helper `byte[] crafted(int L, int A)`; test methods
   `directLimit()` (loops `M` × `L` from B2b), `realCaller()` (identifier cases),
   `writerReaderMismatch()` (an identifier with an owner of exactly 1048576 bytes: `write()` succeeds,
   `readFields` throws), `uncappedControl()` (B2h). Each prints one line
   `case M L A outcome allocBytes` to stdout.
3. Run the `mvn ... test` command of B2a; collect the lines from
   `hadoop-common-project/hadoop-common/target/surefire-reports/org.apache.hadoop.io.TestTextMaxLenProbe-output.txt`.
4. Delete the test file from the local copy when done.

**B2f. Predictions.**
| Case | Outcome | Allocation (minus baseline) |
|---|---|---|
| `M` any, `L = M-1`, complete | success, length `M-1` | ≈ `M-1` (+ ≤ 64 KiB) |
| `M` any, `L = M`, `L = M+1` | `IOException` "tried to deserialize L bytes of data, but maxLength = M" | < 64 KiB |
| `M = 64 MiB`, `L = 1 GiB`, short | same `IOException` | < 64 KiB, no OOM |
| identifier owner 524288 / 1048575 complete | success | ≈ 0.5 MiB / ≈ 1 MiB |
| identifier owner 1048576 | `IOException` "... 1048576 bytes of data, but maxLength = 1048576" | < 64 KiB |
| identifier owner 1 GiB, short | same message with 1073741824 | < 64 KiB, no OOM |
| writer/reader mismatch | `write()` ok, `readFields` throws | — |
| control: uncapped `readFields(in)`, L = 256 MiB short | `EOFException` | ≈ 256 MiB |
| control: uncapped, L = 1 GiB short | `OutOfMemoryError` | — |

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| Allocation ≈ L below the limit, < 64 KiB at/above it, for all three `M` | claim confirmed; the bound moves with `maxLength` |
| Allocation ≈ L (or OOM) for some `L ≥ M` | claim refuted: the check does not prevent the allocation |
| `L = M-1` rejected | claim refuted (off-by-one other than traced) |
| Rejection, but allocation ≫ 64 KiB | something else allocates by claimed length before the check (e.g. a stream buffer); claim refuted for the allocation |
| Uncapped control does not allocate ≈ 256 MiB / OOM | instrument or workload broken; result not confirmed |

**B2h. Controls.** (1) Uncapped control: the same crafted streams through
`Text.readFields(DataInput)` (Text.java:346-349) — same code downstream of the check — must
allocate ≈ L (256 MiB) or OOM (1 GiB): shows the measurement sees the allocation and that the
cap, not the short input, prevents it. (2) Baseline with `L = 0` removes exception/string cost.
(3) Three `M` values show the bound tracks the parameter, not an unrelated limit.
(4) Run each case 5 times in fresh `Text` objects so `ensureCapacity` growth from earlier calls does not mix in.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, pseudo-distributed, non-secure
(`hadoop.security.authentication=simple`). Distribution from the local copy:
`mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`, unpack
`hadoop-dist/target/hadoop-3.4.2.tar.gz` to `/mydata/<run>/hadoop`.
*Amendment (stage-4 audit, 2026-11-25, A2):* on a node set up per the Hadoop stage-4 `environment.md`, the distribution
is `cp -a /mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2 /mydata/<run>/hadoop` (the same `-Pdist`
build of the same pinned source, environment.md §4), not a second build. `HADOOP_PID_DIR=/mydata/<run>/pids` is also
set, and `hadoop.security.authentication=simple` is written into `core-site.xml` explicitly. Runtime JDK 11 (for
`jcmd JFR.*`; JDK 8u262 or later also has JFR). Daemons: **NameNode only** (no DataNode needed —
the RPC under test touches no blocks). Config (`$HADOOP_CONF_DIR` = `/mydata/<run>/conf`):
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9820` (pick a free port, `ss -ltn`),
  `hadoop.tmp.dir=/mydata/<run>/tmp`.
- `hdfs-site.xml`: `dfs.namenode.name.dir=/mydata/<run>/name`, `dfs.replication=1`,
  `dfs.namenode.http-address=localhost:9871` (free port).
- `hadoop-env.sh`: `export HADOOP_LOG_DIR=/mydata/<run>/logs`,
  `export HDFS_NAMENODE_OPTS="-Xms512m -Xmx512m -XX:+UseG1GC -XX:G1HeapRegionSize=1m -Xlog:gc*:file=/mydata/<run>/logs/nn-gc.log"`
  (JDK 11 syntax), `export JAVA_HOME=<jdk11>`.
Probe client `NnTokenProbe.java` (in `/mydata/<run>/probe/`), compiled with
`javac -cp "$(/mydata/<run>/hadoop/bin/hadoop classpath)" NnTokenProbe.java`, run with
`java -cp "$(hadoop classpath):/mydata/<run>/probe" NnTokenProbe <L> <A> <count>`. It builds the
identifier bytes `[0][vint L][A bytes 'a']`, wraps them in
`new Token<DelegationTokenIdentifier>(id, new byte[0], DelegationTokenIdentifier.HDFS_DELEGATION_KIND, new Text("probe"))`,
gets `ClientProtocol nn = ((DistributedFileSystem) FileSystem.get(conf)).getClient().getNamenode()`
(DFSClient.java:1124) and calls `nn.cancelDelegationToken(token)` `count` times, tallying the first
line of each `RemoteException`/`IOException`. Server path: NameNodeRpcServer.java:781-784 →
FSNamesystem.cancelDelegationToken (6402-6420) → AbstractDelegationTokenSecretManager.cancelToken
(654-659) → the check. The DT secret manager exists without security (FSNamesystem.java:1037), and
`readFields` runs before any ownership or running-state check.

**B3b. Knobs.** Claimed owner length `L` with a fixed short payload `A = 8` (so every RPC is the
same ~40 bytes and only the claim varies): 600000 and 1048575 (below the cap, allocation expected),
1048576 (at the cap), 1073741824 (1 GiB, double the NN heap). The cap itself cannot be changed
(constant). No restart between arms.

**B3c. Workload.** 200 cancel RPCs per arm for 600000, 1048575, 1048576; 5 for 1 GiB.
Arithmetic: 200 × 1 MiB ≈ 200 MiB of short-lived allocations below the cap (collectable, fits a
512 MiB heap across young GCs); one 1 GiB allocation cannot fit at all. Duration < 2 min per arm.

**B3d. Observables and instruments.**
- Client tally of error messages per arm (probe stdout).
- JFR on the NameNode: `jcmd <nnpid> JFR.start name=probe settings=profile filename=/mydata/<run>/nn-<arm>.jfr`
  before an arm, `jcmd <nnpid> JFR.stop name=probe` after; `jfr print --events jdk.ObjectAllocationOutsideTLAB nn-<arm>.jfr`.
  Count events with `objectClass = byte[]`, `allocationSize ≥ 500000` whose stack contains
  `org.apache.hadoop.io.Text.readWithKnownLength`.
  *Amendment (stage-4 run 1, 2026-11-25, runbook defect 1; predictions and readings unchanged):* `jfr print` shows the
  class as `byte[]`, but a counter written against the `jdk.jfr.consumer` API sees `RecordedClass.getName()` = `[B`;
  match either spelling, otherwise the below-cap arms read 0 events (the B3g "instrument not seeing the allocation" row). (With 1 MiB G1 regions, arrays ≥ 512 KiB are
  humongous and always allocated outside a TLAB, so each one is recorded.)
- GC log: humongous allocations / "Humongous regions" lines per arm (secondary).
- NN health: `jps` shows NameNode; `grep -c OutOfMemoryError $HADOOP_LOG_DIR/*namenode*.log`;
  `jcmd <nnpid> GC.heap_info` after each arm.
- Not directly observable: the per-call allocation outside JFR's attribution (other RPC buffers),
  which is why `A` is fixed across arms.

**B3e. Procedure.**
1. Build and unpack (B3a); write the config files; `hdfs namenode -format -nonInteractive`.
2. `hdfs --daemon start namenode`; wait for `hdfs dfsadmin -safemode get` → OFF
   (`hdfs dfsadmin -safemode leave` if needed). `NNPID=$(jps | awk '$2=="NameNode"{print $1}')`.
3. For each arm in order 600000, 1048575, 1048576, 1073741824: JFR.start → run probe → JFR.stop →
   `jcmd $NNPID GC.heap_info` → record tally and event count.
4. Check `jps`, the NN log for `OutOfMemoryError`.
5. `hdfs --daemon stop namenode`; `jps` shows no NameNode; remove `/mydata/<run>/{name,tmp}` if not kept.

**B3f. Predictions.**
| Arm | Client messages | JFR `byte[]` events via `Text.readWithKnownLength` | NN |
|---|---|---|---|
| L = 600000 | 200 × `java.io.EOFException` | ≈ 200, size ≈ 600016 | alive |
| L = 1048575 | 200 × `java.io.EOFException` | ≈ 200, size ≈ 1048591 | alive |
| L = 1048576 | 200 × `IOException: tried to deserialize 1048576 bytes of data, but maxLength = 1048576` | 0 | alive |
| L = 1 GiB | 5 × same message with 1073741824 | 0 | alive, no `OutOfMemoryError`, heap used unchanged within noise |

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| Events ≈ count at sizes ≈ L below the cap; 0 at/above; NN alive | claim confirmed on the daemon |
| Events or OOM in the 1048576 / 1 GiB arms | claim refuted |
| 1048575 arm rejected with the maxLength message | claim refuted (boundary differs from trace) |
| Below-cap arms show 0 events | instrument not seeing the allocation (JFR settings, region size) or path not reached; not confirmed — fix before reading the at-cap arms |
| Messages other than EOF/maxLength (e.g. safe mode, standby) | the RPC did not reach the check; rerun after fixing the NN state |

**B3h. Controls.** The below-cap arms are the positive control: same NameNode, same RPC, same
payload size and instrument, and the allocation is seen and tracks `L` (600000 vs 1048575). Fixed
`A` makes the RPC size identical across arms, so a difference can only come from the claimed
length meeting the check. The error message names `maxLength = 1048576`, tying the rejection to
this line rather than the IPC frame limit (`ipc.maximum.data.length` is never approached:
~40-byte requests). The NN process stays the same PID across arms.

**B4. Risks and cleanup.**
- Unit: the 1 GiB uncapped control intentionally throws `OutOfMemoryError` in the surefire JVM
  (512 MiB); surefire's `-XX:+HeapDumpOnOutOfMemoryError` is replaced by the `-Dmaven-surefire-plugin.argLine`
  override, so no ~512 MiB heap dump is written; if one appears, delete it. Remove the test file afterwards.
- Cluster: name dir, logs, JFR files under `/mydata/<run>/` (tens of MB). Ports 9820/9871 — check
  free first. Stop the NameNode with `hdfs --daemon stop namenode` and confirm with `jps`; kill any
  leftover probe JVM. Nothing on shared storage; no Kerberos; no DataNode started.

## C. Sources read

hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/Text.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/WritableUtils.java (signatures)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/security/token/delegation/AbstractDelegationTokenIdentifier.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/security/token/delegation/AbstractDelegationTokenSecretManager.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/security/token/delegation/web/DelegationTokenIdentifier.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/security/token/Token.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/security/token/DtFileOperations.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/security/SaslRpcServer.java (grep)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/permission/PermissionStatus.java (grep)
hadoop-common-project/hadoop-common/src/main/resources/core-default.xml (ipc.maximum.data.length)
hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/security/token/delegation/TestDelegationToken.java
hadoop-common-project/hadoop-common/src/site/markdown/release/ (CHANGELOG grep)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSNamesystem.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/NameNodeRpcServer.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogOp.java (grep)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/security/token/delegation/DelegationTokenSecretManager.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/protocolPB/ClientNamenodeProtocolServerSideTranslatorPB.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSUtil.java
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/security/token/delegation/DelegationTokenIdentifier.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocolPB/PBHelperClient.java
hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DFSClient.java
hadoop-yarn-project/hadoop-yarn/hadoop-yarn-common/src/main/java/org/apache/hadoop/yarn/security/client/YARNDelegationTokenIdentifier.java
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/IFile.java (grep, ARRAY_MAX_SIZE)
hadoop-project/pom.xml (surefire argLine)

## D. Stage-4 feedback

**2026-11-25 — run 1 (node `pc82`), verdict: Confirmed — caps (unit and cluster); outcome class true positive.**
Results: `hadoop/stage4-runtime-verification/jingsong/results/DEFAULT_MAX_LEN-readFields-maxLength--autonomous.md`
(written outside the repository first, `~/writeup-hadoop/out/o7/results.md`). Frozen version (after A1–A3):
sha256 `8755de1ce16ff8ea0eb5396fec8ff072a9d8f5693c0750376c879c128a5c797d`.
- Unit (B2g row 1): below the limit the allocation equals the claim (net 1064 / 1048632 / 67108920 B for
  M = 1024 / 1 MiB / 64 MiB at L = M−1; real caller 524344 / 1048632 B); at and above it (L = M, M+1, 1 GiB) the
  `maxLength = M` `IOException` fires with ≤ 2.3 KiB allocated and no OOM under `-Xmx512m`. Uncapped control: 256 MiB
  allocated, 1 GiB → `OutOfMemoryError`. Writer/reader mismatch observed (owner of 1048576 bytes written, not readable).
- Cluster (B3g row 1): NameNode `cancelDelegationToken` with an 8-byte payload — 200/200 `byte[]` allocations of
  600016 and 1048592 B via `Text.readWithKnownLength` for claims 600000 and 1048575 (EOFException); 0 for 1048576 and
  1 GiB (`tried to deserialize … maxLength = 1048576`); NN alive, no `OutOfMemoryError`, heap unchanged.
- Amendments: A1 (B2a), A2 (B3a) from the audit; A3 (B3d) from runbook defect 1 (the harness's JFR counter matched
  `byte[]` but the consumer API names it `[B`; cluster tier restarted). Predictions and readings tables unchanged.
- The A3 bypasses (uncapped `readFields(DataInput)`, per-field cap) were not part of B1; the uncapped control confirms
  that overload allocates the claimed length in full.
