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

### B3. Cluster tier

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

`none yet`
