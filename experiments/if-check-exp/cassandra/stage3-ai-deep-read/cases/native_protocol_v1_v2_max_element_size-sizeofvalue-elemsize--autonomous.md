# native_protocol_v1_v2_max_element_size — verification solution  <!-- file: cases/native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`CodecUtils.java:250`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/CodecUtils.java#L250) (`if (elemSize > 65535)`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the 65535 is a protocol wire-format limit, not a resource cap, and it can only be reached with protocol V1/V2, which the server does not accept in 5.0.9. |
| Ground | The check guards a 2-byte length prefix (`CodecUtils.java:231-232`, `255`). It bounds no memory- or disk-significant object: the buffers are already allocated by the caller before the check, and V3 to V6 (the only versions the server supports, `ProtocolVersion.java:66`) have no such check (`CodecUtils.java:256-261`). |

## A. Constraint trace

**A1. The constraint.** The earlier trace is correct on the main points and is kept with corrections. There is no configuration entry, property or named constant. The limit is the integer literal `65535` in [`CodecUtils.java:250`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/CodecUtils.java#L250), inside `private static int sizeOfValue(ByteBuffer, ProtocolVersion)` (declared at `CodecUtils.java:243`). The same literal is repeated for the element count in `writeSize` (`CodecUtils.java:101`), so it is not declared once. Unit: bytes (element size). Default: none, not derived from anything. Not settable by yaml, `-D` or JMX; changing it needs a recompile. Correction to the earlier trace: the `sizeOfCollectionSize` lines are `CodecUtils.java:226-241` (V1/V2 return 2 at lines 230-233), and the case labels for the check are lines 247-248, not 246-251. Also note that `value.remaining()` at line 249 throws `NullPointerException` for a null element on V1/V2, while V3+ handle null (line 257), not verified beyond reading the code.

**A2. What it caps.** Other: the serialized size of one collection element, in bytes, so that it fits the 2-byte unsigned length written by `writeValue` for V1/V2 (`CodecUtils.java:141-148`, writing a short; `getUnsignedShort` at line 291 reads it back). The quantity compared is `elemSize = value.remaining()` (line 249). It is not a heap, off-heap or disk limit.

**A3. Mechanism.**
1. `CodecUtils.pack(ByteBuffer[], int, ProtocolVersion)` (`CodecUtils.java:48`) loops over the element buffers and calls `sizeOfValue` for each (line 53).
2. `pack` is called from the list/set and map codecs, `TypeCodec.java:2127` and `TypeCodec.java:2479`, after each element has already been serialized (e.g. `TypeCodec.java:2111-2121`), so the element buffers already exist on heap before the check.
3. In `sizeOfValue`, for `case V1`/`case V2` (lines 247-248), `elemSize = value.remaining()` (line 249); [`if (elemSize > 65535)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/CodecUtils.java#L250) throws `IllegalArgumentException` (lines 251-254); otherwise returns `2 + elemSize` (line 255).
4. For V3 to V6 (lines 256-260) it returns `4 + value.remaining()` (or 4 for null) with no limit check.
5. Outcomes: over the limit, serialization of the collection aborts with an exception and the result buffer (`ByteBuffer.allocate`, line 56) is never allocated; at or under the limit, the result is allocated at `sizeOfCollectionSize + sum` bytes.
6. Reachability: `ProtocolVersion` marks V1 and V2 as no longer supported (`ProtocolVersion.java:42-43`), and the server's supported set is `{V3, V4, V5, V6}` (`ProtocolVersion.java:66`, `73`). `decode` rejects V1/V2 with a `ProtocolException` (`ProtocolVersion.java:106-115`). `ProtocolVersion.CURRENT` is V5 (line 82). Not verified: whether any server-side caller (for example a Java UDF) can pass V1/V2 to these codecs; I found no use of `ProtocolVersion.V1`/`V2` that feeds `pack`. So on a 5.0.9 node this branch is effectively unreachable, except by calling the class directly.
Bypass: none needed, since V3+ never apply the check; the real bound on element size on a node is the 4-byte length (signed int, about 2 GiB) and other limits such as `max_value_size` (a different check, deserialization side; `conf/cassandra.yaml:1864`, commented out).


The check itself is the if statement at [`CodecUtils.java:250`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/CodecUtils.java#L250).

**A4. Other consumers.** The element buffers that `pack` receives, and the result buffer, are heap `ByteBuffer`s of the calling thread (UDF execution or driver-style codec use). Everything else on the heap (memtables, caches, request buffers) is independent of this check.

**A5. Evidence beyond the source.** The CQL native protocol spec describes collection elements as `[short bytes]` in v1/v2 and `[bytes]` (int length) in v3+ (https://github.com/apache/cassandra/blob/cassandra-5.0.9/doc/native_protocol_v3.spec, path not verified). Otherwise none. The code is a copy of the DataStax Java driver's `CodecUtils`, from memory, not verified.

## B. Verification solution

**B1. Claim under test.** The 65535-byte element check at `CodecUtils.java:250` does not bound memory or disk used by a node: it only rejects V1/V2 serialization of an oversized element, usage is unchanged by it, and it is never applied for V3 to V6. Falsified if heap held by serialization differs by protocol version in a way explained by this check, or if a 5.0.9 node ever evaluates the V1/V2 branch.

### B2. Unit tier

**B2a. Environment and build.** Copy the tree to local disk (for example `$HOME/work/cass-509`), JDK 11, `ant jar` (or `ant build`). Write a small Java main (kept outside the tree) compiled against `build/classes/main` plus `lib/*.jar`. JVM options: `-Xmx512m -XX:+UseSerialGC` for stable heap readings; `-XX:+PrintGCDetails` optional.

**B2b. Knobs.** The `ProtocolVersion` argument: V2 (check applies), V3 (no check). Element size: 65535, 65536 (boundary), and 8 MiB (far above). Collection: `TypeCodec.list(TypeCodec.blob())` or equivalent via `CodecUtils.pack` directly (it is public, `CodecUtils.java:48`; the class is public, line 27).

**B2c. Workload.** One `ByteBuffer[]` of N elements of size S with `elements = N`. Cases: N=1 with S in {65535, 65536, 8 MiB}; N=100 with S=65535 (about 6.5 MB, total far above 65535, to show the limit is per element, not per collection).

> **Amendment 2026-10-28 (stage-4 audit, B2b/B2c; independent of any reading).** `CodecUtils.pack(ByteBuffer[], int, ProtocolVersion)` and `ProtocolVersion` are public (checked), so the probe is a JUnit test run by `ant testsome` (`-Dtest.jvm.args="-Xmx512m -Xms512m -XX:+UseSerialGC"`); the null-element case of B2e step 3 passes `new ByteBuffer[]{null}` with V2 and V3 (the V3 branch handles null, `CodecUtils.java:257`). Allocation is read with `com.sun.management.ThreadMXBean.getThreadAllocatedBytes` around each call (exact; heap delta of B2d secondary), 3 repetitions per cell. Source detail for the prediction: in `pack` the loop `sizeOfValue` for all elements runs before `ByteBuffer.allocate` (`CodecUtils.java:50-56`), so a V2 throw happens with the result buffer never allocated: the failing S = 65536 V2 call allocates less than 16 KB (exception text and stack only), whereas the succeeding V3 call at the same S allocates the result `4 + (4+S)`.

**B2d. Observables and instruments.** Whether `pack` returns or throws (and the message); the returned buffer's `remaining()`; heap before/after via `Runtime.totalMemory()-freeMemory()` after `System.gc()`, and `-verbose:gc`. Cannot be observed: a node-level effect.

**B2e. Procedure.**
1. `ant jar`; compile the driver program with `javac -cp build/classes/main:lib/* -d /tmp/x Probe.java` (scratch dir, not the source tree).
2. For each (version, N, S) call `CodecUtils.pack(bufs, N, version)` in try/catch, print outcome and sizes, and the heap delta.
3. Call also with V2 and a null element to record the NPE (line 249).

**B2f. Predictions.** V2: S=65535 returns a buffer of `2 + N*(2+S)` bytes; S=65536 throws `IllegalArgumentException` with the "supports only elements with size up to 65535 bytes" message; N=100, S=65535 succeeds. V3 (and V4 to V6): all of S=65535, 65536 and 8 MiB succeed, returning `4 + N*(4+S)` bytes. Heap delta tracks the allocated result buffer size (about total payload) and is the same function of payload for V2 and V3, independent of the 65535 value.

> **Amendment 2026-10-28 (stage-4 audit, B2f as numbers).** Result sizes: V2, N=1, S=65535: 2+2+65535 = 65 539 bytes; V2, N=100, S=65535: 2 + 100*65537 = 6 553 702; V3, S=65536: 4+4+65536 = 65 544; V3, S=8 MiB: 8 388 616; V3, N=100, S=65535: 4 + 100*65539 = 6 553 904. Control reading (B2h): at V3 and V2 with S = 65535, allocated bytes of the call for N = 1, 10, 100, 1000 grow in proportion to N within 10 % (the result buffer dominates), with no step between N where `N*S` crosses 65535 (N = 1 vs 2). The V2 S = 65536 call throws `IllegalArgumentException` with the text "supports only elements with size up to 65535 bytes" and the V2 null element throws `NullPointerException`.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| V2 throws at S=65536, succeeds at 65535; V3 succeeds at 8 MiB | Mechanism as traced; it is a per-element wire-format check |
| Heap used by successful calls scales with payload for both versions, with no step at 65535 | Usage does not follow the constraint (claim confirmed) |
| Heap/result size capped near 65535 for V3 or V2 totals | Usage follows the knob (claim refuted) |
| Positive control (see B2h) moves heap while the 65535 check stays silent | Claim confirmed |
| V2 does not throw at 65536, or V3 throws | Trace wrong |
| Control heap does not move, or limit never reached | Not confirmed |

**B2h. Controls.** Positive control: the same program with a total payload that grows (N from 1 to 1000 at S=65535) shows heap growth, i.e. what measurable memory does exist is governed by payload, not by the check. A second control is a known memory cap in the tree, for example calling a different bounded structure, not selected here (not verified which is simplest); the payload growth control is sufficient for a first run.

### B3. Cluster tier

n/a: a 5.0.9 node cannot be driven with protocol V1/V2 (`ProtocolVersion.java:66`, `106-115`), so the V1/V2 branch cannot be reached through the client path, and the check never applies to V3+. Alternative: on a node, show with protocol V3 to V5 that collections with elements above 65535 bytes are accepted and that the node's heap/disk follows the written bytes, which answers whether the check limits real usage.

> **Amendment 2026-10-28 (stage-4 audit, B3: declared n/a for the traced branch; the file's own alternative is run).** The file declares that the V1/V2 branch cannot be reached through a node, and then gives an alternative (large elements accepted at v3-v5; usage follows bytes). That alternative is run, as a tier that does not exercise line 250 (it exercises the V3+ branch and the node's usage), and its verdict says so. Source check: a plain `set<blob>` insert does not go through `CodecUtils` (only the UDF layer calls `TypeCodec`, `UDFDataType.java:175-199`), so the alternative adds a Java UDF `RETURNS list<blob>` that builds one element of S bytes (the UDF sandbox allows `java.nio.ByteBuffer`, `UDFunction.java:111`), `user_defined_functions_enabled: true`; a Byteman rule at entry of `CodecUtils.sizeOfValue` prints `SIZEOF ver=<V> remaining=<n>`, which shows the V3+ branch evaluated with n above 65535 and shows that no V1/V2 evaluation occurs. Positive control, replacing `max_value_size` (a deserialization-side check on sstable/stream reads, `AbstractType.java:590-597`, not a write-time cap): `column_value_size_fail_threshold: 512KiB` (`Config.java:916`) on a second node start, same inserts: S = 65535 and 65536 accepted, S = 1 MiB rejected with a guardrail error. The V2 probe uses the bundled python driver at `protocol_version=2`. Writes: 100 rows per size as in B3c. Disk and memtable bytes per element are compared across sizes: (bytes written)/(rows x S) within 25 % between S = 65536 and 1 MiB (no step at 65535).

**B3a. Environment and build.** One node, JDK 11, `ant jar` from a local copy, data/commitlog/hints on local disk of known size (at least 10 GiB free), `-Xms2g -Xmx2g`. Python driver or `cqlsh` with an explicit `--protocol-version` (3 and 4) and a request for 2 to confirm the rejection.

**B3b. Knobs.** Protocol version (2 for the rejection control, 4 for the test). Element size: 65535, 65536, 1 MiB. Not a yaml knob. Note `native_transport_max_message_size`-style limits may reject large frames before the data reaches storage; set them explicitly and record (not verified for the exact key names in 5.0.9).

**B3c. Workload.** Table `(k int primary key, s set<blob>)`; insert rows with a single blob element of each size, 100 rows each (about 100 MiB at 1 MiB), followed by flush.

**B3d. Observables and instruments.** Client acceptance/rejection; `nodetool tablestats` (memtable data size, disk space used); `nodetool info` heap; on-disk size of the data directory (`du`). Cannot be observed: the V1/V2 branch, since it is not reachable.

**B3e. Procedure.** Start the node; create the table; try a V2 connection (expect protocol error); with V4, insert the three sizes; record tablestats and `du` after flush; stop the node and check no process is left.

> **Amendment 2026-10-28 (runbook defect found in run 1, control only; claim, predictions and rows unchanged).** Same defect as in the sibling file `native_protocol_v1_v2_collection_size_limit`: a guardrail is skipped for a superuser, and `ClientState.isSuper()` is true when the authenticator does not require authentication (`ClientState.java:594-605`), so the `column_value_size_fail_threshold: 512KiB` control of the amendment above would not reject anything under the shipped `AllowAllAuthenticator`. The control node runs `authenticator: PasswordAuthenticator` and the writer is an ordinary role `ord` (`SUPERUSER = false`); the prediction (S = 65535 and 65536 accepted, 1 MiB rejected by the guardrail) is unchanged. Found by the sibling's run before this file's control ran; the cluster tier restarted from its beginning.

**B3f. Predictions.** V2 connection refused with a protocol-version error, never an element-size error. V4 inserts of 65536-byte and 1 MiB elements succeed (subject to message-size limits). Disk and memtable size grow roughly linearly with bytes written and show no step at 65535.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| V2 refused; V4 accepts elements above 65535; usage linear in bytes | Claim confirmed |
| V4 rejects elements just above 65535 with the message from line 253 | Claim refuted (check reached on a server path) |
| Usage plateaus at a size related to 65535 | Usage follows the constraint, refuted |
| Positive control (a column with a real cap, for instance exceeding `max_value_size` if set low, which rejects the write) rejects while this case does not | Claim confirmed |
| Large writes rejected by another limit before reaching this code | Not confirmed for those sizes |

**B3h. Controls.** Positive control: lower a limit known to bind (`max_value_size`, `cassandra.yaml:1864`, set small) and show the same insert is rejected, proving the workload does reach a bound when one exists. Repeat with the same data on a clean data directory per run.

**B4. Risks and cleanup.** Unit tier: heap of the probe JVM only; use scratch dirs under the scratchpad; no files in the source tree. Cluster tier: bounded data (at most about 1 GiB) on local disk; after the run, `nodetool drain`, kill the Cassandra process, check with `pgrep -f CassandraDaemon`, delete the data, commitlog and hints directories.

## C. Sources read

- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/INSTRUCTIONS.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/playbook-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/_TEMPLATE-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-in/125.md
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/CodecUtils.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/TypeCodec.java (lines 2105-2130, grep hits)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ProtocolVersion.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/UDFunction.java (grep)
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml (grep)

## D. Stage-4 feedback

**2026-10-28, stage 4 (results: `stage4-runtime-verification/results/native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous.md`; run on `pc41`, tag `cassandra-5.0.9`).** Unit tier **Confirmed, effect: does not cap**; cluster tier (the file's declared-n/a alternative, run anyway; it **does not reach line 250**) **Confirmed, effect: does not cap**; outcome class **true negative** (estimate `negative`, effect `does not cap`). Audit: Ready after amendments (B2 notes, B3 alternative and control; dated 2026-10-28; one further dated amendment to the control mechanism before the file's own cluster run, claim, predictions and rows unchanged).

- Unit (`CodecUtils.pack`, 27 cells x 3 reps): V2 throws the "supports only elements with size up to 65535 bytes" message for S = 65536 and 8 MiB (allocating 2.2 KB: the result buffer is never allocated, as A3 step 5 says) and succeeds at 65535; V3 and V4 succeed to 8 MiB with exact lengths `4 + N*(4+S)`; a null element is an `NullPointerException` on V2 and 4 bytes on V3 (A1's note holds). Allocated bytes per element are flat to 0.2 % for N = 1..1000 at S = 65535.
- Cluster alternative: V2 refused by the server; v4 accepted 100 rows each with one element of 65535 / 65536 / 1 048 576 bytes, disk bytes 1.005 per payload byte at all three; a Java UDF returning `list<blob>` made the node evaluate `sizeOfValue` at V4 and V3 with 65535, 65536 and 1 048 576 bytes (Byteman), never at V1/V2. Control: `column_value_size_fail_threshold: 512KiB` rejected the 1 MiB insert and accepted 65535 and 65536.
- For stage 3: (1) `max_value_size` (named as the control in B3h) is a deserialization-side check (`AbstractType.java:590-597`), not a write-time cap; `column_value_size_fail_threshold` is, but it is skipped for a superuser and every client is one under `AllowAllAuthenticator` (`ClientState.java:594-605`), so the control needs `PasswordAuthenticator` and an ordinary role; (2) a plain `set<blob>` write never calls `CodecUtils`: only a UDF does; (3) `tablestats` memtable data size is invalid across a `MEMTABLE_LIMIT` flush (hit by 100 x 1 MiB inserts at 256 MiB heap space); use the sum of `Data.db` bytes; (4) `test/unit/.../cql3/functions/types/` does not exist in the tag.
- Commits: none (uncommitted; the repository's latest commit at the run was `b68711e5`).
