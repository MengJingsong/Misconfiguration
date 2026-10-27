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

**B2d. Observables and instruments.** Exception type/message; length and first bytes of the returned `ByteBuffer` (count field width); `Runtime.totalMemory()-freeMemory()` after `System.gc()` before and after, and allocation via `-Xlog:gc` or `ThreadMXBean.getThreadAllocatedBytes`. Per-call resource usage cannot be tied to the literal by this alone; hence the control.

**B2e. Procedure.** Run the program for each (version, N, payload). For each, record exception or buffer length; repeat 3 times; stop the JVM and confirm none left (`pgrep -f` the program).

**B2f. Predictions.** V2 with N=65535: succeeds, buffer starts with a 2-byte count of 65535. V2 with N=65536 and 200000: `IllegalArgumentException` with the "65535 elements" message. V3/V4 with N=65536 and 200000: succeed, 4-byte count equal to N. Allocated bytes scale with N times payload in every succeeding case, and by the same rule up to the point of the throw: the buffers array and result allocation happen before the throw (A3 step 5), so the V2 failing case still allocates roughly as much as V3 at the same N.

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

**B3e. Procedure.** Start node; try connecting with protocol V2 and note rejection; with V4 run the workload for each N; record peak heap and data size; stop node (`nodetool drain`, kill), `pgrep -f cassandra` to confirm none left; delete data dirs.

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

`none yet`
