# native_transport_max_frame_size (startup validation in applySimpleConfig) — verification solution  <!-- file: cases/native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:620`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L620) (`620#1` = `valueInBytes < 0`, `620#2` = `valueInBytes > Integer.MAX_VALUE-1`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code (CLI version not obtainable: `claude --version` failed inside the sandbox), 2026-10-24, band D triage |
| Estimate | `positive` (scoped): the entry becomes `Envelope.Decoder.MAX_TOTAL_LENGTH`, and the decoder discards any envelope whose header + body length exceeds it instead of accumulating it, which bounds the per-connection inbound decode buffer for protocol v3/v4 connections and for the initial (pre-negotiation) handler. Protocol v5 framing does not use it (`native_transport_max_message_size` governs there). Of the two checks, `620#1` is unreachable because `IntMebibytesBound.toBytes()` saturates to `[0, Integer.MAX_VALUE]`; `620#2` rejects values ≥ 2048 MiB. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `native_transport_max_frame_size`, configuration entry ([`Config.java:284-285`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L284-L285), `IntMebibytesBound`, default `16MiB`, legacy `native_transport_max_frame_size_in_mb`), commented at `conf/cassandra.yaml:1044`. `applySimpleConfig` reads `toBytes()` ([`DatabaseDescriptor.java:619`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L619)), which is `Ints.saturatedCast` ([`DataStorageSpec.java:442-445`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DataStorageSpec.java#L442-L445)), and throws if outside `[0, Integer.MAX_VALUE-1]` ([`DatabaseDescriptor.java:620-626`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L620-L626)). Getter `getNativeTransportMaxFrameSize` (`:3153-3156`). Read into a `static final` field at `Envelope.Decoder` class init ([`Envelope.java:197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Envelope.java#L197)), so it needs a restart. The setter `setNativeTransportMaxFrameSize(int bytes)` wraps the argument as MiB ([`DatabaseDescriptor.java:3158-3161`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3158-L3161)), used only in a test (`CQLConnectionTest.java:117`).


**Limit type (2026-10-29).** not-a-case: the entry-pointer `if` validates the value against a literal range, not usage against a capacity ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)). The verification solution and the stage-4 results are kept as filed.
**A2. What it caps.** Bytes buffered for one inbound legacy (pre-v5) envelope in the Netty `ByteToMessageDecoder` cumulation (pooled direct memory) before the envelope is sliced out and dispatched. Operand: `totalLength = bodyLength + Header.LENGTH` vs `MAX_TOTAL_LENGTH` (`Envelope.java:425-429`).

**A3. Mechanism.**
1. `Envelope.Decoder` is installed for the initial handler ([`PipelineConfigurator.java:265`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L265)) and for the legacy pipeline ([`PipelineConfigurator.java:391`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L391), `configureLegacyPipeline`).
2. `decode(ByteBuf)` reads the header; if `totalLength > MAX_TOTAL_LENGTH`, it enters discard mode, skips the bytes received so far and keeps skipping on later reads ([`Envelope.java:345-352`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Envelope.java#L345-L352), `429-438`, `490-495`), then throws `InvalidRequestException` "Request is too big…" to the stream (`:478-486`). Otherwise it waits until `totalLength` bytes are buffered (`:441-442`) and slices the body (`:448-452`).
- Bypass: protocol v5 connections decode frames in `CQLMessageHandler` using `extractHeader` ([`Envelope.java:221-252`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Envelope.java#L221-L252)), which has no `MAX_TOTAL_LENGTH` check. Inbound bytes for in-flight legacy requests are separately limited by `native_transport_max_request_data_in_flight[_per_ip]` ([`DatabaseDescriptor.java:649-657`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L649-L657)).

**A4. Other consumers.** Netty/`BufferPool` direct memory for all connections, v5 frame buffers, outbound response buffers (not checked by this entry), `native_transport_receive_queue_capacity`.

**A5. Evidence beyond the source.** `NEWS.txt:1976` (frame size limits protocol frames), `NEWS.txt:1220` (relation to commit log segment size in older releases).

## B. Verification solution

**B1. Claim under test.** For protocol v4, an envelope with `bodyLength + 9 > native_transport_max_frame_size` is rejected with "Request is too big" without buffering it, so the largest inbound request size observed (`ClientMessageSizeMetrics` bytesReceivedPerRequest max) never exceeds the entry; envelopes at or below it are accepted. Values ≥ 2048 MiB fail startup.

### B2. Unit tier

**B2a. Environment and build.** Local clone `/local/c509`, JDK 11, `ant jar build-test`. Test classes in package `org.apache.cassandra.transport` (to reach package-private `Decoder.decode(ByteBuf)`, `Envelope.java:343`): `FrameCap1MiBTest`, `FrameCap4MiBTest`, one class per knob because `MAX_TOTAL_LENGTH` is fixed at class load and `ant testsome` forks a JVM per class. Each `@BeforeClass` calls `DatabaseDescriptor.daemonInitialization(() -> { Config c = DatabaseDescriptor.loadConfig(); c.native_transport_max_frame_size = new DataStorageSpec.IntMebibytesBound("<N>MiB"); return c; })` before touching `Envelope`.

**Amendment 2026-10-24 (step-0 audit) — B2a, this host and the classes.** Clone `$W/cassandra-run5` (`W=~/Library/Caches/stage4`, tag `cassandra-5.0.9`, `ant -Dlocal.repository=$W/m2 build-test`), JDK 11. Four test classes in `test/unit/org/apache/cassandra/transport/`: `FrameCap1MiBTest`, `FrameCap4MiBTest`, `FrameCapDefaultTest` (calls `DatabaseDescriptor.daemonInitialization()` with no override, so the knob is the `Config.java:285` default) and `FrameCap2048MiBTest`, sharing a non-test helper `FrameCapBase.java`; each runs in its own `ant testsome -Dtest.name=org.apache.cassandra.transport.<class>` (one forked JVM per class, since `daemonInitialization()` returns early once it has run, `DatabaseDescriptor.java:259-261`, and `MAX_TOTAL_LENGTH` is fixed at class load, `Envelope.java:197`). Each class writes `STAGE4 …` lines to the file named by `-Dstage4.out`. Reason: the clone path and the default class were not given.

**B2b. Knobs.** N ∈ {1, 4} MiB; plus a third class with `2048MiB` expecting `ConfigurationException` from `daemonInitialization`.

**Amendment 2026-10-24 (step-0 audit) — B2b, the default added and a read-back.** N ∈ {1, 4, 16 (default, unset)} MiB, plus `2048MiB`. After `daemonInitialization` each class reads back `DatabaseDescriptor.getNativeTransportMaxFrameSize()`; it must equal N·2^20 (16,777,216 for the default). Reason: audit group A needs at least three values including the default, and a set without a read-back cannot show the knob took.

**B2c. Workload.** Hand-built v4 envelopes: 9-byte header (version 0x04, flags 0, stream 1, opcode QUERY 0x07, body length L) followed by L bytes, with L = N·2^20 − 9 (exactly at the limit), L = N·2^20 − 8 (one byte over), L = 2·N·2^20. Fed into `new Envelope.Decoder().decode(buf)` in 64 KiB chunks via a single `CompositeByteBuf`/re-used cumulation, mimicking Netty reads.

**Amendment 2026-10-24 (step-0 audit) — B2c, exact bytes and feeding.** Envelope = 9-byte header `04 00 00 01 07` followed by L as a big-endian unsigned 32-bit integer, then L zero bytes; Ls per N: L1 = N·2^20 − 9 (total exactly N·2^20), L2 = N·2^20 − 8 (total N·2^20 + 1), L3 = 2·N·2^20 (total 2·N·2^20 + 9). The whole envelope is cut into consecutive 65,536-byte chunks (the last one shorter). One new `Envelope.Decoder` per envelope; the cumulation is one heap `ByteBuf` (`Unpooled.buffer()`): for each chunk, `writeBytes(chunk)`, read `before = readableBytes()`, call `decoder.decode(cum)`, read `after = readableBytes()`, then `cum.discardReadBytes()` (as Netty's cumulator keeps only unread bytes). Feeding stops at the first returned `Envelope` or thrown exception. Reason: the header bytes, chunk boundaries and what "retained" means were not exact.

**B2d. Observables and instruments.** Returned `Envelope` or thrown `ErrorMessage.WrappedException`; `buf.readerIndex()` / `readableBytes()` after each chunk (whether bytes are skipped or retained); maximum `readableBytes()` retained across chunks.

**Amendment 2026-10-24 (step-0 audit) — B2d, observables.** Per envelope: outcome (an `Envelope`, with `header.bodySizeInBytes` and `body.readableBytes()`; or the exception class, its cause class and message), the index of the chunk at which the outcome occurred, and the maxima of `before` and `after` over the chunks. B2h control: `decoder.extractHeader(ByteBuffer)` on the first 9 bytes of the same three envelopes with the version byte `05`: `isSuccess()` and `bodyLength()`. Reason: the observables were listed but not defined.

**B2e. Procedure.** For each L: allocate, feed chunks, record result and max retained bytes. Run each class with `ant testsome -Dtest.name=org.apache.cassandra.transport.FrameCap<N>MiBTest`.

**Amendment 2026-10-24 (step-0 audit) — B2e, order and stop conditions.** Per class: read-back, then L1, L2, L3, then the B2h control. Order of the runs: `FrameCap1MiBTest`, `FrameCap4MiBTest`, `FrameCapDefaultTest`, `FrameCap2048MiBTest`, each bounded by the default JUnit timeout of `build.xml`. A class that fails stops nothing; its outcome is a reading. Reason: the order and the control's place were open.

**B2f. Predictions.** At-limit envelope decoded, max retained ≈ N MiB. One byte over and 2N MiB: retained bytes after each chunk ≤ 64 KiB (skipped), exception "Request is too big: length X exceeds maximum allowed length N·2^20" after the final chunk. 2048 MiB → `ConfigurationException` "native_transport_max_frame_size must be positive value < 2147483647B".

**Amendment 2026-10-24 (step-0 audit) — B2f, exact form.** For N = 1, 4, 16: read-back N·2^20. L1: an `Envelope` with body length L1, returned at the last chunk (index N·16 − 1), no exception, max(`before`) = N·2^20. L2 and L3: no `Envelope`; exactly one exception, at the last chunk and not before, `ErrorMessage.WrappedException` with cause `InvalidRequestException` and message `Request is too big: length T exceeds maximum allowed length N·2^20.` with T = L + 9 (`Envelope.java:478-486`); max(`before`) = 65,536 and max(`after`) = 0 (every chunk is skipped as it arrives). Control: `isSuccess()` true and `bodyLength()` = L for all three Ls at every N. `2048MiB`: `daemonInitialization` throws `ConfigurationException` with the message `native_transport_max_frame_size must be positive value < 2147483647B, but was 2147483647B` (`toBytes()` saturates 2^31 to 2^31 − 1, `DataStorageSpec.java:442-445`, which is > `Integer.MAX_VALUE - 1`, `DatabaseDescriptor.java:619-626`). Reason: "≈ N MiB" and "≤ 64 KiB" were not exact, and the default and the control had no values.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| over-limit bodies skipped, error raised | cap works as traced |
| over-limit body fully retained before error | cap does not bound buffering (claim wrong) |
| over-limit envelope decoded | check not applied (claim wrong) |
| 2048 MiB accepted | `620#2` ineffective |

**Amendment 2026-10-24 (step-0 audit) — B2g, rows added; the four rows above are unchanged.** Row 1 ("cap works as traced") needs every amended B2f item at N = 1, 4 and 16 and the `2048MiB` rejection. Added rows:

| Observation | Meaning |
|---|---|
| L1 (total = the knob) rejected | the cap is tighter than the knob (claim wrong: envelopes at the limit must be accepted) |
| read-back ≠ N·2^20, or the message names a maximum ≠ N·2^20 | knob not taken; invalid run |
| rejection raised before the last chunk, a different exception or message, or max(`before`) > 65,536 for L2/L3 | trace differs from A3; not confirmed |
| v5 control: `extractHeader` fails for any L | control invalid; the bypass is not shown (row 1 still possible for the cap) |
| a test class does not run (compile error, timeout) | not run for that value; the tier is not confirmed |

**B2h. Controls.** Same at-limit and over-limit envelopes with version byte 0x05 through `extractHeader` (`Envelope.java:221`): no size error, demonstrating the v5 bypass and that the result depends on the cap, not on the bytes.

**Amendment 2026-10-24 (step-0 audit) — B2h, the control's scope.** The control shows that the v5 header path (`extractHeader`, `Envelope.java:221-252`) carries no length check; it does not show anything about the bytes. Reason: wording; the outcome is in the amended B2f.

### B3. Cluster tier

**B3a. Environment and build.** One node from `/local/c509`, `MAX_HEAP_SIZE=2G`, dirs under `/local/c509-node`, `-XX:NativeMemoryTracking=summary`. `native_transport_allow_older_protocols: true` (yaml default, `conf/cassandra.yaml:1056`). Keep `commitlog_segment_size: 32MiB` so `max_mutation_size` = 16 MiB is above the payloads.

**Amendment 2026-10-24 (step-0 audit) — B3a, this host.** One node, `127.0.0.1`, from `$W/cassandra-run5` (the unit tier's clone; no `ant` runs there while the node is up), `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`; configuration copied to `$W/node-ntmfs/conf` (`CASSANDRA_CONF`), data, commit log, hints, saved caches and CDC under `$W/node-ntmfs/`, wiped before and after each start; `-XX:NativeMemoryTracking=summary` appended to the node's copy of `jvm-server.options`. Everything else as shipped (`commitlog_segment_size: 32MiB`, so `max_mutation_size` = 16 MiB and the v5 `native_transport_max_message_size` = min(16 MiB, in-flight limits of 204.8 / 51.2 MiB at a 2 GiB heap) = 16 MiB, `DatabaseDescriptor.java:3237-3245`). Started with `bin/cassandra -f` in the background; up when `nodetool status` shows `UN` and `statusbinary` prints `running`, bound 360 s. Reason: CloudLab paths; the node's other limits must be known to read B3f.

**B3b. Knobs.** `native_transport_max_frame_size` ∈ {`2MiB`, `8MiB`} (restart for each); startup with `2048MiB`.

**Amendment 2026-10-24 (step-0 audit) — B3b, the default added; read-backs.** Knob K ∈ {default (unset → 16 MiB), `2MiB`, `8MiB`}, one node start each, in that order; then a start with `2048MiB`. Read-back after each start: `SELECT value FROM system_views.settings WHERE name = 'native_transport_max_frame_size'` (expected `16MiB`, `2MiB`, `8MiB`); the decoder's own value is the "maximum allowed length" in every rejection message. Reason: audit group A needs three values including the default; knob-taken evidence.

**B3c. Workload.** Python script using the driver bundled with cqlsh (`PYTHONPATH=/local/c509/lib/cassandra-driver-internal-only-*.zip`), `Cluster(protocol_version=4)`, table `ks.t (k int PRIMARY KEY, v blob)` RF 1, inserting blobs of size 0.5×, 0.9×, 1.1×, 3× the knob, 20 times each, plus 8 concurrent connections sending 3× blobs in a loop for 60 s. Repeat the 1.1× case with `protocol_version=5` as bypass check.

**Amendment 2026-10-24 (step-0 audit) — B3c, exact client and order.** Harness client `frame-client.py`: bundled driver `lib/cassandra-driver-internal-only-3.29.0.zip` (loaded as `bin/cqlsh.py` loads it), `Cluster(['127.0.0.1'], protocol_version=4` (or 5 for the bypass phase)`, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False)`, request timeout 60 s, `FallthroughRetryPolicy`, consistency ONE. Schema `CREATE KEYSPACE ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}` and `ks.t (k int PRIMARY KEY, v blob)`; prepared `INSERT INTO ks.t (k, v) VALUES (?, ?)`; blob = ⌊f·K⌋ zero bytes. Per start, in order: (1) v4 single inserts, 20 sequential per f ∈ {0.5, 0.9, 1.1, 3}, distinct k; (2) rejected flood: 8 worker processes, each with its own `Cluster` (one connection), synchronous inserts of 3K blobs in a loop for 60 s, k = worker id; (3) 20 s settle; (4) accepted flood (B3h control), the same with 0.9K blobs; (5) v5 phase: 20 inserts of 1.1K with `protocol_version=5`. The rejected flood runs before the accepted one because Netty's pooled arenas keep the memory an accepted flood allocates (`conf/jvm11-server.options:144-145`, chunk 16 MiB). Each insert's outcome is printed (OK, or the exception class and message). Reason: the client, concurrency and order were open; the order matters for the NMT comparison.

**B3d. Observables and instruments.** Client-side result/exception per insert; `nodetool sjk mx -b "org.apache.cassandra.metrics:type=ClientMessageSize,name=BytesReceivedPerRequest" -mg -f Max` (histogram defined at `ClientMessageSizeMetrics.java:31,34`, updated at `Envelope.java:445`); `jcmd <pid> VM.native_memory summary` every 5 s during the 60 s flood; `logs/system.log`.

**Amendment 2026-10-24 (step-0 audit) — B3d, exact observables.** (i) Per insert: OK or the exception class and message. (ii) `nodetool sjk mx -b "org.apache.cassandra.metrics:type=ClientMessageSize,name=BytesReceivedPerRequest" -mg -f Max` and `-f Count`, and the exact counter `…name=BytesReceived -mg -f Count` (incremented by the accepted envelope's total length only, `Envelope.java:444`), read after the schema and after each phase of B3c, so each phase has its own delta; the v4 readings come before the v5 phase because the v5 path updates the same histogram (`CQLMessageHandler.java:369`). The histogram's `Max` is the upper offset of the highest non-empty bucket, not the value (`DecayingEstimatedHistogramReservoir.java:537-549`; offsets grow by ×1.2, `EstimatedHistogram.java:91-109`); the bucket bound B(K) of each knob is 2,346,799 (2 MiB), 8,409,007 (8 MiB), 17,436,917 (16 MiB). (iii) `jcmd <pid> VM.native_memory summary` every 1 s from 10 s before each flood until 10 s after it (5 s was too coarse for cumulations that live less than a second); D = committed KB of the `Other` category (direct memory: `Unsafe.allocateMemory`, used by Netty and `ByteBuffer.allocateDirect`); ΔD = max over the flood's samples − the last sample before the flood. (iv) `system.log` read only past the start's byte offset. Reason: "max ≤ knob" cannot hold literally for a bucketed histogram (B(K) > K), the sampling window and the NMT figure were undefined.

**B3e. Procedure.** Start node, create schema, run script per knob, collect metrics, drain, stop, wipe; start with 2048 MiB and record failure.

**Amendment 2026-10-24 (step-0 audit) — B3e, sequence and bounds.** Per knob: wipe, write the yaml, start (360 s), schema, read-back, B3c phases (1)–(5) with metric reads between them (each insert bounded by its 60 s timeout; each flood 60 s, its workers killed at 90 s), `nodetool drain` (bound 120 s), stop, check `ps -eo command | grep '[C]assandraDaemon'` is empty, wipe. `2048MiB`: start bounded to 120 s; "fails" = the process exits, `node.out` or `system.log` holds the B2f message, and no `Startup complete` line; "starts" = `UN` and `running`. Reason: no bounds, and no test for "fails".

**B3f. Predictions.** v4: 0.5× and 0.9× succeed; 1.1× and 3× fail with `InvalidRequest` "Request is too big"; `BytesReceivedPerRequest` max ≤ knob. During the flood, NMT native growth stays well below 8 connections × 3 × knob (rejected bodies are discarded, not cumulated). v5 1.1× succeeds (governed by `native_transport_max_message_size`, default derived in `DatabaseDescriptor.java:903-918`). 2048 MiB: startup fails.

**Amendment 2026-10-24 (step-0 audit) — B3f, exact form; "≤ knob" restated for the histogram.** At each K: 0.5× and 0.9×: 20/20 OK. 1.1× and 3×: 20/20 `InvalidRequest` whose message contains `Request is too big: length T exceeds maximum allowed length K.` with K in bytes and T > K. ΔBytesReceived over each of the 1.1× and 3× phases < K (no over-limit envelope counted; one would add more than K), and ≥ 20 × 0.9K over the 0.9× phase. `Max` after phases (1)–(4) ≤ B(K) and equal to the bucket bound of the 0.9× message. Rejected flood: every completed insert rejected; ΔD < 6K (a quarter of 8 × 3 × K: at most 12 / 48 / 96 MiB at 2 / 8 / 16 MiB) and ΔD(rejected) < ΔD(accepted). v5 phase: at 2 and 8 MiB 20/20 OK (the bypass); at 16 MiB 20/20 rejected by `native_transport_max_message_size` (1.1 × 16 MiB > 16 MiB) with `… bytes exceeds allowed maximum of 16777216 bytes` (`CQLMessageHandler.java:848-851`), i.e. B3g row 4 by design at the default. `2048MiB`: fails as defined in B3e. Reason: "max ≤ knob" was unreachable for a bucketed histogram; "well below" had no number; the default's v5 outcome follows from the node's other limits, not from any reading.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| v4 over-limit rejected, max ≤ knob | claim confirmed |
| v4 over-limit accepted | cap not applied (claim wrong) |
| NMT grows ≈ 8 × 3 × knob during flood | rejected frames still buffered (claim wrong for memory) |
| v5 over-limit rejected too | another limit binds; not a refutation, note which |

**Amendment 2026-10-24 (step-0 audit) — B3g, definitions and rows added; the four rows above are unchanged.** "max ≤ knob" in row 1 means `Max` ≤ B(K) and ΔBytesReceived < K over the over-limit phases; "NMT grows ≈ 8 × 3 × knob" (row 3) means ΔD(rejected) ≥ 12K (half of 8 × 3 × K). Row 1 ("claim confirmed") needs every amended B3f item at all three knobs, the `2048MiB` failure, and the B3h control (ΔD(accepted) > ΔD(rejected)). Added rows:

| Observation | Meaning |
|---|---|
| 0.5× or 0.9× rejected at any K | the cap is tighter than the knob (claim wrong) |
| read-back ≠ K, or a rejection message names a maximum ≠ K | knob not taken; invalid run |
| client saw a rejection but `Max` > B(K) or ΔBytesReceived ≥ K over an over-limit phase | over-limit envelope decoded and counted (claim wrong) |
| 6K ≤ ΔD(rejected) < 12K, or ΔD(accepted) ≤ ΔD(rejected) | the memory part is not shown; rejection rows as observed, memory **not confirmed** |
| an over-limit insert fails otherwise (connection closed, timeout) | not the traced rejection; not confirmed |
| `2048MiB` starts | `620#2` ineffective (claim wrong for startup) |
| v5 1.1× rejected at 2 or 8 MiB | row 4 (another limit binds); name it |

**B3h. Controls.** 0.9× insert shows the path works and the metric moves; v5 run shows dependence on protocol; compare NMT against a flood of 0.9× (accepted) blobs, which must show higher buffered bytes than the rejected flood.

**Amendment 2026-10-24 (step-0 audit) — B3h, the comparison is ΔD.** "Higher buffered bytes" = ΔD(accepted) > ΔD(rejected), ΔD as in the amended B3d. Reason: the comparison had no observable.

**B4. Risks and cleanup.** Small disk use (≤ 1 GB). Stop the node and script, `pgrep -f CassandraDaemon` empty, `rm -rf /local/c509-node`.

**Amendment 2026-10-24 (step-0 audit) — B4, disk.** The accepted flood writes blobs of up to 14.4 MiB on 8 connections for 60 s: the commit log is bounded by `commitlog_total_space` (default ≤ 8 GiB) and each flush holds at most 8 + 80 rows, so ≤ 10 GiB on `$W/node-ntmfs` against 157 GiB free; wiped after each start. The check is `ps -eo command | grep '[C]assandraDaemon'`. Reason: "≤ 1 GB" did not count the control flood.

## C. Sources read

src/java/org/apache/cassandra/config/DatabaseDescriptor.java (619-626, 649-657, 903-918, 3153-3161)
src/java/org/apache/cassandra/config/Config.java (284-285)
src/java/org/apache/cassandra/config/DataStorageSpec.java (400-470)
src/java/org/apache/cassandra/transport/Envelope.java (195-340, 340-500)
src/java/org/apache/cassandra/transport/PipelineConfigurator.java (265, 294, 388-398)
src/java/org/apache/cassandra/metrics/ClientMessageSizeMetrics.java (31-35)
test/unit/org/apache/cassandra/transport/CQLConnectionTest.java (110-118)
conf/cassandra.yaml (1044-1056)
NEWS.txt (1220, 1976)

## D. Stage-4 feedback

**Stage 4 closed 2026-10-24** ([results](../../stage4-runtime-verification/results/native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous.md)); Claude Opus 5.5 (claude-opus-5-5), advisor's machine; estimate `positive` (scoped) held. **Unit tier: Confirmed — caps only on some paths (bypass)** (at 1, 4, 16 MiB the envelope of total = knob is decoded with knob bytes retained; total = knob + 1 and 2× knob are skipped chunk by chunk, at most 65,536 B retained, and rejected at the last byte with "Request is too big: length T exceeds maximum allowed length <knob>."; `2048MiB` → `ConfigurationException` "native_transport_max_frame_size must be positive value < 2147483647B, but was 2147483647B"; v5 `extractHeader` accepts every size). **Cluster tier: Confirmed — caps only on some paths (bypass)** (one node at 2, 8, 16 (default) MiB, protocol v4: 0.5× and 0.9× blobs accepted, 1.1× and 3× rejected naming the knob; `BytesReceived` rose by ≤ 10,584 B over each over-limit phase and rejected flood; `BytesReceivedPerRequest` `Max` ≤ the knob's bucket bound; NMT `Other` rose ≤ 41 KiB during 60 s floods of 3× envelopes on 8 connections against 35–427 MiB for accepted 0.9× floods; `2048MiB` stops startup; protocol v5 1.1× accepted at 2 and 8 MiB, rejected at 16 MiB by `native_transport_max_message_size`). No runbook defect. Notes for stage 3, not applied: B1's "max ≤ entry" cannot hold literally for the bucketed histogram (`DecayingEstimatedHistogramReservoir.java:537-549`; the exact `BytesReceived` counter answers it); v5 large messages left both metrics unchanged at 8 MiB (not on `CQLMessageHandler.java:369`'s path); every rejection is logged as a WARN with the exception. The seventeen amendments of 2026-10-24 (B2a–B2h, B3a–B3h, B4) were made at the step-0 audit; the frozen hash is in `_INDEX.md` §4, and this section was added after it.
