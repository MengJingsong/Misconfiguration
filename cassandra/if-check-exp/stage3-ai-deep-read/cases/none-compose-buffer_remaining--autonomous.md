# none — verification solution  <!-- file: cases/none-compose-buffer_remaining--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`UDFDataType.java:177`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/UDFDataType.java#L177) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`. The line is a null/empty-value normalisation, not a limit; the byte count of the value (`buffer.remaining()`) is compared with the literal 0. The deserialized object is as large as the value, and nothing at this line bounds that. |
| Ground | There is no constraint at this line: no configuration entry, property or constant is read. The only memory-significant object nearby is the Java object that `typeCodec.deserialize` ([`UDFDataType.java:180`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/UDFDataType.java#L180)) builds from the argument bytes; its size follows the argument size, which is capped only upstream (request frame size), not here. |

> **Link rule.** Followed: the declaration (A1) and the if statement (Entry pointer, A3) are permalinks at `cassandra-5.0.9`.

## A. Constraint trace

**A1. The constraint.** None at the target. The condition at [`UDFDataType.java:177`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/UDFDataType.java#L177), in `UDFDataType.compose(ProtocolVersion, ByteBuffer)` (declared at UDFDataType.java:175), is `buffer == null || (buffer.remaining() == 0 && abstractType.isEmptyValueMeaningless())`. It returns null for a null buffer, or for a zero-length buffer of a type where empty means "no value"; otherwise it calls `typeCodec.deserialize(buffer, protocolVersion)` (UDFDataType.java:180). The earlier trace was checked and holds: `remaining()` is compared with 0, not a limit. `isEmptyValueMeaningless()` is declared at [`AbstractType.java:458`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L458) (body to line 461, default `false`) and overridden in, among others, Int32Type.java:56, LongType.java:53, DoubleType.java:52, BooleanType.java:48, UUIDType.java:69, ReversedType.java:64 (delegates to the base type, line 66). Declaration "of the constraint": none exists; the nearest declared limits are not read here (see A4). No default, no settable key, no restart question. Unit: n/a.

Nearest memory-significant object (used for the design): the Java value created by `typeCodec.deserialize` at UDFDataType.java:180, whose size scales with the argument bytes.

**A2. What it caps.** Nothing. It compares a buffer length with zero. The only resource touched is heap: the object produced at line 180 for non-empty arguments of a non-primitive Java type (blob, text, collection, UDT, tuple).

**A3. Mechanism.** The if statement is [`UDFDataType.java:177`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/UDFDataType.java#L177).
1. `UDFDataType.getArgumentDeserializer()` (UDFDataType.java:292-298) returns the `AbstractType`'s own deserializer for primitive Java types (line 295-296) and otherwise `this::compose` (line 298).
2. `FunctionArguments.newInstanceForUdf` stores one deserializer per UDF argument (FunctionArguments.java:60-72, using `getArgumentDeserializer()` at line 70). So non-primitive UDF arguments reach line 177 through that method reference. Where `FunctionArguments.set` calls the deserializer: not verified (`set` is declared at FunctionArguments.java:140; its body was not read).
3. `UDFunction.execute` runs the function only if UDFs are enabled (`assertUdfsEnabled`, UDFunction.java:429-430, reading `user_defined_functions_enabled`, Config.java:588, default false).
4. `UDAggregate` calls `compose` directly for the initial state (UDAggregate.java:211).
Outcomes: null or (empty and meaningless-when-empty) returns null, which for `RETURNS NULL ON NULL INPUT` skips the call (UDFunction.java:368, `isCallableWrtNullable` at UDFunction.java:563); otherwise the full value is deserialized with no size test. Bypass/overshoot: not applicable; there is no limit. Similar checks exist at AbstractType.java:789, ToJsonFct.java:63, CastFcts.java:393 and CreateAggregateStatement.java:233.

**A4. Other consumers.** The size of the argument is bounded elsewhere, not here: the native-protocol envelope limit `native_transport_max_frame_size` (declared Config.java:285, default 16MiB; enforced at Envelope.java:429 against `MAX_TOTAL_LENGTH` set at Envelope.java:197) and `max_value_size` (Config.java:310, default 256MiB, applied when reading values from sstables, AbstractType.java:572 and 582-596, check at line 594). Values built inside the node (rows read from sstables, concatenated results) can be larger than one frame. Other heap users during UDF execution: the UDF's own allocations and result serialisation (`decompose`, UDFunction.java:603-605), sandbox threads when `user_defined_functions_threads_enabled` is true (Config.java:627), and the normal read path.

**A5. Evidence beyond the source.** none.

## B. Verification solution

**B1. Claim under test.** The check at UDFDataType.java:177 does not limit memory: for a non-empty argument, heap allocated by `compose` grows with the argument size, with no cap introduced at this line; only the upstream limit (`native_transport_max_frame_size`, the positive control) stops oversized requests.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Copy the tag to local disk (`rsync -a ~/cassandra-5.0.9/ $WORK/cassandra-5.0.9/`), `cd $WORK/cassandra-5.0.9 && ant jar` (or `ant build`). Write a small Java main `ComposeProbe` in a separate directory (not in the tree), compile against `build/classes/main` plus `lib/*.jar`, run with `java -Xmx512m -XX:+UseSerialGC -Dcassandra.config=file:///$WORK/cassandra.yaml`. `UDFDataType.wrap` and `compose` are public (UDFDataType.java:120, 175). `DatabaseDescriptor.daemonInitialization()` may be needed if driver codecs touch config: not verified.

**B2b. Knobs.** (1) Argument byte length L of a blob buffer: 0, 1, 1 KiB, 1 MiB, 16 MiB, 64 MiB (the last two exceed the default frame limit, to show the line does not stop them). (2) Type: `BytesType` (buffer is non-primitive; `isEmptyValueMeaningless` false), `Int32Type` (meaningless-when-empty true, Int32Type.java:56), `ListType<Int32Type>` frozen. (3) Config: `max_value_size` and `native_transport_max_frame_size` set to the defaults and to 1MiB, to show they do not influence `compose` (set in the yaml file).

**B2c. Workload.** For each type and L, build `ByteBuffer.allocate(L)` (for the list: a serialised list of N ints, N = L/8) and call `UDFDataType.wrap(type, false).compose(ProtocolVersion.CURRENT, buf)` 100 times. Arithmetic: L = 64 MiB is four times the 16 MiB default frame limit and well under the 512 MB heap, so it fits if the line caps nothing.

**B2d. Observables and instruments.** Per-call allocated bytes via `com.sun.management.ThreadMXBean.getThreadAllocatedBytes(Thread.currentThread().getId())` before and after each call; return value (null or not) and its class; exceptions. Retained size of the result: `System.gc()` then `Runtime.totalMemory()-freeMemory()` with the result held. Not observable: native memory of the driver codec, if any.

**B2e. Procedure.**
1. Build as in B2a.
2. For each type: call with `null`, with a zero-length buffer, then each L; record allocated bytes, result.
3. Repeat with the yaml limits at 1MiB.
4. Positive control (unit): call `BytesType.instance.read(in, 1024)` (`read`, AbstractType.java:582) on a stream whose vint length is 2048 and observe the `IOException` at AbstractType.java:594 - a real cap rejecting oversize input, unlike `compose`.

**B2f. Predictions.** Null buffer: null result for every type, ~0 bytes allocated. Zero-length: null for `Int32Type` and `ListType`? (ListType meaningless-when-empty: not verified, treat as an open question), non-null empty for `BytesType`. For L >= 1: result non-null, allocated/retained bytes grow roughly linearly with L (at least L when the codec copies; whether it copies is not verified), for 16 MiB and 64 MiB too, identical with `max_value_size` and frame limit at 1MiB. The control throws (check at AbstractType.java:594).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Allocation/retained bytes rise with L and are unchanged by the yaml limits; control throws | Claim confirmed: the line caps nothing |
| 64 MiB call throws or returns null although it is non-empty | Claim refuted: some limit applies on this path |
| Allocation changes when `max_value_size` or frame limit changes | Claim refuted: the limit reaches this path |
| Allocation flat in L while control works | Codec does not materialise the value (e.g. view); re-measure with a collection type |
| L never reaches the size, or control does not throw | Not confirmed; fix harness |

**B2h. Controls.** Empty-buffer rows show the only behaviour the line has (null vs empty value). Primitive type (`Int32Type`) shows no growth. Control on a real cap in B2e step 4. JVM warmed with 20 calls before measuring; fixed heap and SerialGC to reduce noise.

### B2 amendment: design audit, 2026-10-29 (stage 4; applies `stage4-runtime-verification/none-type-design.md` sections 3 and 4)

The estimate (`negative`) is unchanged. This block supersedes B2a-B2h where they differ; the filed text stays as the record.

**U0. Kind corrected: 2 (emptiness flag), with the data size as a secondary kind 1.** The branch at UDFDataType.java:177 differs only at length 0: for a buffer of length L >= 1 the right operand `buffer.remaining() == 0` is false and line 180 (`typeCodec.deserialize`) runs on both sides of the check. The only value-dependent part is `abstractType.isEmptyValueMeaningless()` (AbstractType.java:458, default false; true for `IntegerType` at IntegerType.java:90 and for `Int32Type` at Int32Type.java:56). The reading that matters for the claim is therefore (i) what the branch changes at L = 0 and (ii) that at L >= 1 the allocation does not depend on the check. "caps" is used only if the true branch reduces or refuses an allocation that the false branch would make at equal operand; the true branch here returns null, so it can only save one small object at L = 0.

**U1. Audit corrections to the filed B2.** (a) Citations re-read in `cassandra/cassandra-5.0.9/`: UDFDataType.java:120, 175-181; AbstractType.java:458-461, 582, 594; Int32Type.java:56 and the other overrides listed in A1 (grep of `isEmptyValueMeaningless`: DateType, FloatType, TimestampType, AbstractTimeUUIDType, Int32Type, LongType, CounterColumnType, InetAddressType, IntegerType, LexicalUUIDType, UUIDType, DoubleType, DecimalType, ReversedType, BooleanType) all hold; the control line is `if (l > maxValueSize)` at AbstractType.java:594 inside `read(ValueAccessor, DataInputPlus, int)` at 582. (b) The filed sweep uses `Int32Type` at lengths 1 KiB to 64 MiB: an int32 value is 4 bytes, so a long `Int32Type` buffer is not a valid value (the driver codec rejects it); the type that is "meaningless when empty" and accepts any length is `IntegerType` (varint, a `BigInteger`), so the sweep uses `IntegerType` (check can be true at L = 0) against `BytesType` (check never true) and keeps `Int32Type` only at L = 0 and L = 4. (c) The filed B2b(3) yaml variants (`max_value_size`, `native_transport_max_frame_size` at 1MiB) are dropped: `compose` reads no configuration (A1), so a yaml variant cannot be a branch flip, and the unit JVM has no frame decoder. (d) The ListType question in B2f is dropped from the prediction (open question, not needed). (e) `-XX:+UseSerialGC` is dropped (G1 default).

**U2. Launcher.** Plain `java -Xmx1g`, not `ant testsome`, `-Dcassandra.config=` the copy's `test/conf/cassandra.yaml`, the JDK 11 module flags of `conf/jvm11-server.options`, `DatabaseDescriptor.daemonInitialization()` first; probe compiled by `javac` into a separate directory (`UDFDataType.wrap` and `compose` are public); never copied into a tree. Build: `copy-source.sh ~/s4-none`, `ant build-test`, on `pc41` only. Pass A (no agent) for allocation, pass B (Byteman, a rule at `UDFDataType.compose` line 180 calling a static counter) for the reach counter: line 180 must run for every call except the null buffer and the L = 0 `IntegerType` call.

**U3. Sweep, arms, instruments.** Length L in {0, 1, 1 KiB, 1 MiB, 16 MiB, 64 MiB}; types `BytesType` (check false at L = 0) and `IntegerType` (check true at L = 0); `Int32Type` at L = 0 (check true, null) and L = 4 (value); a null buffer (check true by `buffer == null`). Per call a window `getThreadAllocatedBytes` before and after `UDFDataType.wrap(type, false).compose(ProtocolVersion.CURRENT, buffer)` (the `wrap` outside the window); record the result class (null or not). 5 repetitions per cell, 20 warm-up calls (2 for L >= 1 MiB). The buffer content is a positive `BigInteger` pattern (first byte 0x01) for IntegerType. Arm order in one JVM: EMPTY (two readings with nothing between), then null buffer, then every cell in the order listed, then L = 0 and L = 1 MiB cells repeated once (the noise floor: two identical calls). Branch-flip pair at L = 0: `IntegerType` (check true) against `BytesType` (check false); at L >= 1 the same-type comparison is the sweep itself (no branch change).
Control (positive, design section 3.5): `BytesType.instance.read(ByteBufferAccessor.instance, in, 1024)` on a `DataInputBuffer` whose vint length is 2048 must throw `IOException` ("exceeds the maximum of 1024", AbstractType.java:594-597): a real size cap in the same harness, shown to refuse an allocation that `compose` has no counterpart for. Positive allocation control C1: `new byte[L]` through the same window reads L + 16.

**B2f (amended). Frozen predictions.** Bytes, medians of five repetitions, pass A.
- R1 (reach, pass B): line 180 runs for every call except the null buffer and the `IntegerType` and `Int32Type` L = 0 calls.
- R2 (the check's own effect at L = 0): the null buffer and the L = 0 `IntegerType` and `Int32Type` calls return null and allocate at most 256 each; the L = 0 `BytesType` call returns a non-null empty value and allocates at most 1024; their difference is at most 1024, which is below the heap noise of about 16 MiB by four orders.
- R3 (data follows the codec, not the check): for `IntegerType`, allocation divided by L lies in [1.0, 4.0] for L >= 1 MiB; for `BytesType`, allocation at every L is at most 4 L + 1024 (a view or a copy; which of the two is not predicted).
- R4 (noise floor): two identical L = 0 calls differ by at most 64; two identical L = 1 MiB `IntegerType` calls differ by at most 1 percent of L; EMPTY at most 16.
- R5 (controls): C1 in [L + 16, L + 32]; the 2048-length read throws `IOException` whose message contains "exceeds the maximum of 1024".
- R6 (Int32Type): L = 4 returns a non-null value; its allocation is at most 1024.

**B2g (amended). Conclusions table.** The first matching row, in this order.

| Reading | Meaning | Verdict | Effect on the constraint |
|---|---|---|---|
| R1 fails (line 180 not reached where predicted), or a result class differs from R2/R6 | the check did not run as traced | Invalid | undetermined |
| C1 outside R5, the 2048 read does not throw, or EMPTY above 16 | the instrument could not show an effect | Not confirmed | undetermined |
| R1 to R6 hold | the check saves at most one small object at L = 0 and changes nothing at L >= 1; the allocation follows the codec and the data | Confirmed | does not cap |
| Any L >= 1 cell shows an allocation difference between the two types that cannot come from the codec, or the L = 0 difference exceeds 1024 | the check gates more than traced | Refuted | caps if the true branch is the smaller one at equal operand, otherwise undetermined |
| A difference below the noise floor of R4 | not resolved | Not confirmed | undetermined |

**B2h (amended). Controls.** C1, the 2048-length read (positive), EMPTY, the null buffer, `Int32Type`, and the repeated cells as the noise floor.

**U4. Unit-tier limit (kind 2).** This is a unit-tier measurement only. The cluster tier is `n/a` (B3).

### B3. Cluster tier

**B3 amendment, 2026-10-29: `n/a: operand has no size.`** The branch differs only at length 0, an object of tens of bytes, which is below the heap noise of about 16 MiB with G1; the filed B3 only restates that heap follows the argument data (the expected operand effect, not a finding), and enabling UDFs (`user_defined_functions_enabled`) adds a sandbox for no information about the check. The filed B3a-B3h below are not run; they stay as the record. The unit tier alone settles this case.


**B3a. Environment and build.** One node (second optional) built from the local copy, JDK 11, `ant jar`; data, commitlog, hints under `$WORK/data` on local disk. `cassandra.yaml`: `user_defined_functions_enabled: true` (Config.java:588; needs restart), `user_defined_functions_threads_enabled` left true (default Config.java:627). JVM: `-Xms1g -Xmx1g`, G1, `-Xlog:gc*:file=$WORK/gc.log`. Client: `cqlsh` plus a small driver script.

**B3b. Knobs.** Value size S per blob: 1 KiB, 1 MiB, 8 MiB, 14 MiB (below the 16MiB frame limit); concurrent readers C: 1, 8, 32. Positive control knob: `native_transport_max_frame_size` (yaml, Config.java:285) 16MiB vs 4MiB, restart between.

**B3c. Workload.** Schema: `CREATE TABLE ks.t (k int PRIMARY KEY, v blob);` and `CREATE FUNCTION ks.f(v blob) CALLED ON NULL INPUT RETURNS int LANGUAGE java AS 'return v == null ? -1 : v.remaining();'` (blob maps to a non-primitive type, so `compose` is used, UDFDataType.java:298). Insert 1 row per size S (inserts of 14 MiB stay under the frame limit). Then `SELECT ks.f(v) FROM ks.t WHERE k=?` repeated 200 times at each C. Arithmetic: C=32 x S=14 MiB = about 448 MiB of live argument objects if they overlap, about 45% of a 1 GiB heap, so growth with S and C is visible. Duration 2 minutes per cell.

**B3d. Observables and instruments.** Heap used after GC and allocation rate from `gc.log`; `jcmd <pid> GC.class_histogram` (bytes of `byte[]`/`HeapByteBuffer`) at peak; `nodetool tpstats`, `nodetool info` (heap). Server-side error text for oversize requests. Not observable: attribution of heap to line 180 specifically (use the histogram delta against the S=1 KiB baseline).

**B3e. Procedure.**
1. Build, start the node with the yaml above; check `nodetool status`.
2. Create schema and function; insert the rows.
3. Take a baseline histogram and GC log mark; run the select loop for each (S, C); sample every second; record peak heap-after-GC.
4. Positive control: restart with `native_transport_max_frame_size: 4MiB`; try to insert the 8 MiB and 14 MiB rows and observe "Request is too big" style rejection (message format at Envelope.java:484); the 1 MiB row still works.
5. Stop the node (`nodetool drain`, kill), confirm no process remains.

**B3f. Predictions.** Peak heap-after-GC and allocation rate increase with S and with C; at S = 14 MiB, C = 32 they approach the arithmetic above and are not clamped to any value tied to the line. The UDF call returns S for each row. With the 4MiB frame limit, 8 MiB and 14 MiB inserts are rejected, while reads of already-stored rows are not tied to this check.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Heap and allocation grow with S and C; control rejects oversize inserts | Claim confirmed |
| Heap flat in S and C while the control works | Not confirmed as written; the value may not be materialised (check byte[] histogram) |
| A cap on S or C appears with no config change | Claim refuted |
| Usage follows the frame setting for reads of stored rows | Claim refuted for that path |
| Large S never reached, or control inserts accepted at 4MiB | Not confirmed |

**B3h. Controls.** Baseline S = 1 KiB. Same query without the UDF (`SELECT v`) to separate read-path heap from UDF-argument heap. Same UDF on an `int` column (primitive, `Int32Type` deserializer, UDFDataType.java:295-296) as a no-growth control. Fresh JVM per cell or forced GC before each.

**B4. Risks and cleanup.** Disk: 14 MiB x few rows, plus commit log, on local disk of known size; keep `$WORK` under 2 GiB. UDFs run in the node's sandbox; enable only on the test node, never shared. A mis-set `user_function_timeout_policy` default `die` (Config.java:662) can shut the node down on a slow UDF; keep the function trivial. Cleanup: stop Cassandra and any driver script, `pgrep -f CassandraDaemon` and `pgrep -f ComposeProbe` must return nothing, delete `$WORK`.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/UDFDataType.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/FunctionArguments.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/UDFunction.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/UDAggregate.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/JavaUDF.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Envelope.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/schema/CreateAggregateStatement.java
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml

## D. Stage-4 feedback

`done 2026-10-29` (unit tier only, kind 2; B3 amended `n/a: operand has no size`). Results: [`results/none-compose-buffer_remaining--autonomous.md`](../../stage4-runtime-verification/results/none-compose-buffer_remaining--autonomous.md). **Verdict: Confirmed - does not cap; outcome class true negative** (estimate `negative`, effect `does not cap`). The check changes the outcome only at length 0: null buffer, `IntegerType` L = 0 and `Int32Type` L = 0 return null (0 bytes, line 180 not reached), `BytesType` L = 0 returns an empty buffer (48 bytes); for L = 1 .. 64 MiB line 180 runs for both types, `BytesType` allocates 48 bytes at every L (the codec returns a view) and `IntegerType` allocates L + 56; noise floor 0; control `BytesType.read` with a 2048 vint and max 1024 threw (AbstractType.java:594). All frozen predictions held.

Audit feedback for stage 3 (2026-10-29): (1) operand kind is 2 (an emptiness flag), as the drafts file said, not a data-size operand; (2) the filed sweep used `Int32Type` for large L, but an int32 value is 4 bytes; the type that is meaningless when empty and accepts any length is `IntegerType`; (3) the filed yaml variants (`max_value_size`, frame limit) do not reach `compose` and were dropped; (4) the filed ListType open question is unnecessary; (5) B3 is `n/a`. Citations held (UDFDataType.java:120, 175-181; AbstractType.java:458, 582, 594; the `isEmptyValueMeaningless` overrides listed in A1).
