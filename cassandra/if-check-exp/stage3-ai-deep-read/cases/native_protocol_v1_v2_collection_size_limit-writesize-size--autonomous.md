# native_protocol_v1_v2_collection_size_limit — verification solution  <!-- file: cases/native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`CodecUtils.java:101`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/CodecUtils.java#L101) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the literal 65535 is a wire-format limit on the element count of a collection serialized with the v1/v2 layout; it is not a memory or disk cap, and v1/v2 is not a protocol version the server accepts. |
| Ground | The check bounds a 16-bit count field, not bytes held. It is reached only if `ProtocolVersion.V1` or `V2` is passed to the driver-derived codecs, and the server's supported range starts at V3 (`transport/ProtocolVersion.java:67`, `:104-105`). For V3 to V6 the same method writes a 4-byte int with no cap (`CodecUtils.java:112`). The array of serialized elements is already fully allocated before the check runs (`CodecUtils.java:48-57`), so the check cannot prevent that allocation. |

## A. Constraint trace

**A1. The constraint.** Corrected reading of the earlier trace: there is no memory or disk constraint here, and the earlier text is right about that. What exists is a hard-coded literal `65535` in [`CodecUtils.java:101`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/CodecUtils.java#L101) (`if (size > 65535)`), inside `private static void writeSize(ByteBuffer output, int size, ProtocolVersion version)` (declared at `CodecUtils.java:95`; `case V1:` / `case V2:` at lines 99-100). Kind: constant, declared inline at that line, and its message at lines 102-105 names it ("supports up to 65535 elements in any collection"). Unit: elements in a collection. Value 65535 = largest unsigned 16-bit value; it matches the `output.putShort((short) size)` at line 106 that follows. It is not derived from anything and cannot be set by yaml key, `-D` property or JMX; changing it needs a source edit and rebuild. Not verified: whether any other file repeats the literal (only this file was checked for the caller path).

**A2. What it caps.** Nothing in memory or disk. It bounds the element count that the v1/v2 wire layout can express (a 2-byte count). The quantity compared is `size`, the `elements` argument passed down from `CodecUtils.pack` (`CodecUtils.java:48`, call at `:57`). Callers pass `value.size()` of a Java collection or map: `TypeCodec.java:2127` (list/set, in `AbstractCollectionCodec.serialize`, class at `:2083`) and `TypeCodec.java:2479` (map). Note the map call passes `value.size()` (entries) while the buffer array holds two buffers per entry.

**A3. Mechanism.**
1. A UDF/UDA-side codec (`cql3/functions/types/TypeCodec.java`) serializes a Java `List`/`Set`/`Map` into one `ByteBuffer[]` with one buffer per element (`TypeCodec.java:2099-2127`).
2. `CodecUtils.pack` sums element sizes (`CodecUtils.java:50-55`), allocates the whole result `ByteBuffer` (`:56`), then calls `writeSize` (`:57`).
3. `writeSize` switches on protocol version (`:97`). For V1/V2 the if statement is [`CodecUtils.java:101`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/CodecUtils.java#L101).
4. Outcomes: size above 65535 throws `IllegalArgumentException` (`:102-105`); otherwise writes a short (`:106`). For V3 to V6 the count is written as an int with no check (`:108-112`). Any other version throws (`:114`).
5. Bypass/overshoot: the check runs after the buffers and the result array are already allocated (`:50-56`), so it neither prevents nor reduces that allocation. V3 and later have no cap at all. Whether V1/V2 can reach this code in 5.0.9 is not verified beyond: `ProtocolVersion.V1`/`V2` exist in the enum and are marked "no longer supported" (`transport/ProtocolVersion.java:42-43`), and the supported array is `{V3, V4, V5, V6}` (`:66`), with decoding restricted to that range (`:104-105`). I did not trace whether a UDF can be handed a V1/V2 value; the unit tier below passes it directly.

**A4. Other consumers.** Heap used by the element buffers and the result buffer in the UDF codec path (`CodecUtils.java:50-56`) is bounded only by the collection the caller built, and by the UDF sandbox/limits, not by this literal. Collection size on the real server is bounded elsewhere (not traced here; not verified).

**A5. Evidence beyond the source.** The `ProtocolVersion` enum comments (`transport/ProtocolVersion.java:42-43`). Public native protocol spec documents the v1/v2 `[short]` collection count and the v3 `[int]` count (the spec file `doc/native_protocol_v3.spec` was not opened; not verified).

## B. Verification solution

**B1. Claim under test.** Usage does not follow the literal 65535: it limits only the count representable under V1/V2, and a collection with more than 65535 elements serializes with a count that grows with it under V3+ with no cap, so the 65535 check does not bound heap or disk.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tag to local disk (never build in the shared tree): `cp -r <source> /local/cass && cd /local/cass && ant jar`. Small Java program or JUnit test on the build classpath calling `TypeCodec` (the public `TypeCodec.list(...)`-style factory in `cql3/functions/types/TypeCodec.java`; exact factory name not verified) with `ProtocolVersion.V2`, then `V3`/`V4`. JVM options: `-Xmx512m -Xms512m -XX:+UseSerialGC` for stable heap numbers.

**B2b. Knobs.** (1) Protocol version: `V2`, `V3`, `V4`. (2) Element count N: 65535, 65536, 200000. (3) Element payload: 1-byte values (small) and 100-byte values (control for bytes). N values straddle the literal: at the limit, one over, and well over.

**B2c. Workload.** Build `ArrayList<Integer>` or `List<Byte>`-equivalent of N elements, call `serialize(list, version)`. Arithmetic: N=65536 exceeds the literal by exactly one, so V1/V2 must throw and V3+ must not.

> **Amendment 2026-10-28 (stage-4 audit, B2a-B2c; independent of any reading).** Factory names checked in `TypeCodec.java`: `TypeCodec.list(TypeCodec<T>)` (line 345) and `TypeCodec.blob()` (line 265, element type `ByteBuffer`). The probe therefore serializes `TypeCodec.list(TypeCodec.blob())` over `ByteBuffer` elements of 1 byte and 100 bytes, built before the measured call, and calls `codec.serialize(list, ProtocolVersion.V2 / V3 / V4)` (the codec is public API of the `cql3.functions.types` package). Each (version, N, payload) cell is measured 3 times in one JVM after a warm-up call, as a JUnit test run by `ant testsome` with `-Dtest.jvm.args="-Xmx512m -Xms512m -XX:+UseSerialGC"`.

**B2d. Observables and instruments.** Exception type/message; length and first bytes of the returned `ByteBuffer` (count field width); `Runtime.totalMemory()-freeMemory()` after `System.gc()` before and after, and allocation via `-Xlog:gc` or `ThreadMXBean.getThreadAllocatedBytes`. Per-call resource usage cannot be tied to the literal by this alone; hence the control.

**B2e. Procedure.** Run the program for each (version, N, payload). For each, record exception or buffer length; repeat 3 times; stop the JVM and confirm none left (`pgrep -f` the program).

**B2f. Predictions.** V2 with N=65535: succeeds, buffer starts with a 2-byte count of 65535. V2 with N=65536 and 200000: `IllegalArgumentException` with the "65535 elements" message. V3/V4 with N=65536 and 200000: succeed, 4-byte count equal to N. Allocated bytes scale with N times payload in every succeeding case, and by the same rule up to the point of the throw: the buffers array and result allocation happen before the throw (A3 step 5), so the V2 failing case still allocates roughly as much as V3 at the same N.

> **Amendment 2026-10-28 (stage-4 audit, B2d/B2f as numbers).** (i) Primary allocation instrument: `com.sun.management.ThreadMXBean.getThreadAllocatedBytes(currentThread)` before and after the call (exact); the heap delta of B2d is secondary and coarse. (ii) Result sizes: V2 success `2 + N*(2+S)` bytes (N = 65535, S = 1: 196 607), V3/V4 `4 + N*(4+S)` (N = 200 000, S = 1: 1 600 004). (iii) "Roughly as much" in B2f is fixed as: for the same N and S, allocated bytes of the failing V2 call >= 0.8 x the allocated bytes of the succeeding V3 call, and >= the V2 result size `2 + N*(2+S)` (the result buffer is allocated at `CodecUtils.java:56` before `writeSize` throws at line 101-105). "Far less" (refuted row) is a ratio < 0.5. (iv) Control: at V3, N = 200 000, the 100-byte payload allocates at least 0.9 x 99 x N = 17.8 MB more than the 1-byte payload (the result buffer grows from `4+5N` to `4+104N`). (v) Note for stage 3: the V2 failing call at N = 65536, S = 1 throws in `writeSize` after the buffer array, the `ByteBuffer[]` and the result buffer exist, so the check cannot reduce those allocations; the count message is the "65535 elements" text of line 102-105.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| V2 throws above 65535, V3/V4 do not | check works as traced; it is a count-width limit |
| V2 failing call still allocates about as much as V3 at same N | the literal does not bound memory (claim confirmed) |
| V2 failing call allocates far less than V3 at same N | allocation is cut by the check; trace of A3 step 5 wrong (claim refuted) |
| V3 throws at 65536 | trace wrong; claim refuted |
| Allocation flat while N and payload grow | control failed; reading not valid |
| N never exceeds 65535 in the run | limit not reached; not confirmed |

**B2h. Controls.** Positive control: payload size sweep (1 vs 100 bytes) at fixed N must move allocated bytes proportionally, showing the instrument sees memory. Same N, different version isolates the effect of the literal.

### B3. Cluster tier

**B3a. Environment and build.** One node built from the copy in B2a, heap `-Xmx1g`, data/commitlog on local disk of known size. Client: `cqlsh` or a driver pinned to V4/V5. A V1/V2 client cannot connect (see below).

**B3b. Knobs.** Client protocol version (V3, V4, V5; attempt V2 as a negative probe); collection size N in a `list<int>`/`set<int>` column: 1000, 65536, 500000. Server settings left default, except as the control (`collection_size_warn_threshold`, `collection_size_fail_threshold` if present in 5.0.9; not verified in the yaml).

**B3c. Workload.** `CREATE TABLE t (k int PRIMARY KEY, s set<int>)`; insert a row with N elements (batched inserts to build the set), then read it back. N=500000 is well above 65535 so a 16-bit count would not suffice.

**B3d. Observables and instruments.** Client result (success/error); heap via `jstat -gc <pid>` every 1 s; `nodetool tablestats` for on-disk size; node `system.log`.

> **Amendment 2026-10-28 (stage-4 audit, B3c/B3d/B3h: the workload as written does not reach the traced code).** Source check (`grep -rn "CodecUtils\." src/java` finds no caller outside `TypeCodec`; `TypeCodec` is reached on a node only from the UDF layer, `UDFDataType.decompose/compose`, `UDFDataType.java:175-199`, with the client's protocol version): a plain `INSERT` of a `set<int>` and its read-back use `SetType`, never `CodecUtils.writeSize`. So the cluster tier is run as two workloads: (W) the plain set write as in B3c, with a Byteman rule counting `CodecUtils.pack` calls (expected 0 during W), and (U) a Java UDF `RETURNS list<int>` of N elements (`user_defined_functions_enabled: true`; `SELECT mk(n) ...` with the client at protocol v4 and v3), which does reach `CodecUtils.pack` and `writeSize` with the client's version (Byteman lines `PACK`/`WRITESIZE`, expected `ver=V4`/`V3` and `size=N` with N above 65535, never V1/V2). Positive control B3h, replacing the unnamed knob: `collection_size_fail_threshold: 200KiB` (`Config.java:918`, a write-time guardrail on the same collection bytes), second node start, same W inserts: N = 1000 accepted, N = 65536 and 500 000 rejected by the guardrail (their serialized size is at least 4 B x N = 262 144 B > 200 KiB). The V2 probe uses the bundled python driver at `protocol_version=2`. Bytes per element (memtable data size / N, then SSTable bytes / N after flush) at N = 65 536 and 500 000 must be within 25 % of each other (no step at 65535).

**B3e. Procedure.** Start node; try connecting with protocol V2 and note rejection; with V4 run the workload for each N; record peak heap and data size; stop node (`nodetool drain`, kill), `pgrep -f cassandra` to confirm none left; delete data dirs.

> **Amendment 2026-10-28 (runbook defect found in run 1, control only; claim, predictions and rows unchanged).** The control as amended above did not bind: a first cluster run with `collection_size_fail_threshold: 200KiB` accepted the N = 65536 and 500 000 inserts and only logged "Guardrail collection_size violated ... exceeds the failure threshold of 204800" at flush. Cause, from the source: a guardrail is skipped for a superuser (`Guardrail.enabled(state)` -> `ClientState.isOrdinaryUser()`, `ClientState.java:594-604`) and `ClientState.isSuper()` is true whenever the authenticator does not require authentication (`ClientState.java:602-605`), i.e. with the shipped `AllowAllAuthenticator`. The control node therefore runs `authenticator: PasswordAuthenticator` and writes as an ordinary role (`CREATE ROLE ord WITH PASSWORD = 'ord' AND LOGIN = true AND SUPERUSER = false`, created by the default `cassandra` superuser); the prediction (N = 1000 accepted, 65536 and 500 000 rejected by the guardrail) is unchanged. The cluster tier restarted from its beginning.

**B3f. Predictions.** V2 connection is refused (`ProtocolVersion.java:104-105,128-129` reject outside V3..V6 or below CURRENT without older-protocol allowance). V4 and V5 accept N above 65535 without any error citing 65535. Heap peak and disk size grow with N; no step at 65535.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Error mentioning 65535 at N above 65535 on V3+ | claim refuted |
| Smooth growth across 65535, no 65535 error | claim confirmed |
| V2 accepted by the server | trace of supported range wrong |
| N never above 65535 achieved (other limits fail first) | not confirmed; note which limit |
| Positive control does not move usage | not confirmed |

**B3h. Controls.** Positive control: the same N sweep with larger values per element must raise heap/disk, and `column_value_size_*`-type limits (where a real cap binds) are the place to see a cap; exact knob name not verified. Repeat each N three times; fresh data dir between runs.

**B4. Risks and cleanup.** Unit tier: JVM heap only. Cluster tier: local disk only, keep dataset small (N=500000 ints is a few MB); never use shared storage; kill node and client, remove data/commitlog/hints dirs, remove `/local/cass` build copy.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/CodecUtils.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/TypeCodec.java (lines 2083-2130, 2465-2482)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ProtocolVersion.java (lines 40-70, grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/UDFunction.java (grep only)

## D. Stage-4 feedback

**2026-10-28, stage 4 (results: `stage4-runtime-verification/results/native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous.md`; run on `pc41`, tag `cassandra-5.0.9`).** Unit and cluster tiers **Confirmed, effect: does not cap**; outcome class **true negative** (estimate `negative`, effect `does not cap`). Audit: Ready after amendments (B2 note, B3 workload and control; dated 2026-10-28; one further dated amendment to the control mechanism during run 1, claim, predictions and rows unchanged).

- Unit (`TypeCodec.list(TypeCodec.blob()).serialize`, 18 cells x 3 reps): V2 throws the "65535 elements" message exactly for N = 65536 and 200 000; V3 and V4 succeed with length `4 + N*(4+S)` and count field N. The failing V2 call allocated 96.5 to 98.7 % of the succeeding V3 call at the same N and S (the result buffer is allocated before `writeSize` throws: A3 step 5 holds). Control: payload 100 B against 1 B at V3, N = 200 000: +19.8 MB allocated.
- Cluster: **the workload as written did not reach the traced code** (a plain `set<int>` write never calls `CodecUtils`; Byteman counted 0 `pack` calls during it). Only the UDF layer calls the driver-derived codecs, with the client's protocol version, so a Java UDF returning `list<int>` was added: `writeSize` was called with sizes 1000 / 65536 / 500 000 under V4 and V3, results `4 + 8N` bytes, no error. Plain writes on v4 at N = 1000 / 65536 / 500 000 are accepted, 24.0 B per element in the memtable and 4.01 B on disk with no step at 65535. A V2 client is refused by the server ("Invalid or unsupported protocol version (2)"). Control: `collection_size_fail_threshold: 200KiB` rejected N = 65536 and 500 000 and accepted 1000.
- For stage 3: (1) a write-time guardrail does not apply to a superuser, and with the shipped `AllowAllAuthenticator` every client is one (`ClientState.isSuper`, `ClientState.java:594-605`): a positive control built on a guardrail needs `PasswordAuthenticator` and an ordinary role (the first form of the control accepted everything and only logged the flush-time error); (2) cluster workloads for the UDF codecs must go through a UDF; (3) thread-allocated bytes are exact for large arrays but TLAB-granular for the many small element buffers (first measured cell noisy); (4) `test/unit/.../cql3/functions/types/` does not exist in the tag.
- Commits: none (uncommitted; the repository's latest commit at the run was `b68711e5`).
