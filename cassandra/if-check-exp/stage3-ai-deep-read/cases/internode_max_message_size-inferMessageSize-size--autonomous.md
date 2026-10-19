# internode_max_message_size — verification solution  <!-- file: cases/internode_max_message_size-inferMessageSize-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/net/Message.java:817` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code agent, 2026-10-19 |
| Estimate | `positive`. `internode_max_message_size` is a hard per-message cap on the on-wire size of one internode message, checked on both the send and the receive side. A message that exceeds it is never buffered, deserialized or queued. This bounds the heap / direct memory one message can pin, but not the aggregate (aggregate is bounded by the separate reserve-capacity limits, A4). |

## A. Constraint trace

**A1. The constraint.** `internode_max_message_size` (configuration entry, `DataStorageSpec.IntBytesBound`, bytes, upper bound Integer.MAX_VALUE), declared at `src/java/org/apache/cassandra/config/Config.java:238-239` (legacy name `internode_max_message_size_in_bytes`, `@Replaces` at :238). It has no static default and does not appear in `conf/cassandra.yaml`. Default is derived in `DatabaseDescriptor.java:992-996`: `min(internode_application_receive_queue_reserve_endpoint_capacity, internode_application_send_queue_reserve_endpoint_capacity)`. Both default to 128MiB (`Config.java:252,259`), so the default is 128MiB. If set explicitly, `DatabaseDescriptor.java:974-989` rejects startup with `ConfigurationException` unless it is <= all four of the send/receive endpoint/global reserve capacities (128MiB/128MiB/512MiB/512MiB by default). Settable in `cassandra.yaml` only. It is read through `DatabaseDescriptor.getInternodeMaxMessageSizeInBytes()` (`DatabaseDescriptor.java:3085-3088`), so it is read at each check, and a test-only setter exists (`:3091-3094`, `setInternodeMaxMessageSizeInBytes`). No JMX setter was found, so a change in production needs a restart.

**A2. What it caps.** Heap / direct (off-heap) memory used for internode messages. The compared quantity is the on-wire size of one message: header (id, creation time, expiry, verb, flags, params) plus the vint-prefixed payload (`Message.java:777-819`; outbound analog `serializedSize`). The comparison is `size > limit` at `Message.java:817`. It is a per-message cap, not a sum over messages.

**A3. Mechanism.**
1. Inbound, `Message.java:817-818`: `inferMessageSize` computes `size = index - readerIndex` from the header bytes plus the payload-length vint (`:810-815`) and throws `OversizedMessageException(size)` if `size > limit`. It returns -1 if the header is not yet fully buffered (`:783,788,792,797,802,807,812`), so the check runs only once the payload length is known. The payload itself need not have arrived, because the size comes from the length prefix.
2. Callers: `InboundMessageHandler.java:128` (`processOneContainedMessage`) and `:214` (`processFirstFrameOfLargeMessage`). In both, `inferMessageSize` is called before `acquireCapacity(...)` (`:136`, `:217`) and before any `LargeMessage` or `ProcessSmallMessage` is created. An oversized message therefore reserves no endpoint/global capacity and gets no buffer. The exception is a RuntimeException in the frame-processing path. I did not trace the handler's `exceptionCaught` to the end. The expected outcome is that the inbound channel is closed and the sender reconnects, but this is unverified and is checked in B3 (the "Messaging" metrics and logs).
3. Outbound, `OutboundConnection.java:330-332` (`enqueue`, using `canonicalSize`, the size at the current/lowest messaging version), `:793-794` (re-check with the real `serializedSize(messagingVersion)` when filling the send buffer) and `:979-980` (large-message path, before `AsyncMessageOutputPlus` writes). Each throws the same `OversizedMessageException` (`Message.java:1143-1148`). At `enqueue`, the message is rejected before `acquireCapacity` (`:335`), so it takes no queue memory.
4. Sizes under the limit continue to normal admission: at or below `largeThreshold` (`OutboundConnections.LARGE_MESSAGE_THRESHOLD`) a small message is deserialized in place (`InboundMessageHandler.java:148-149`). Above it a `LargeMessage` is processed (`:151`, `:198-201`). Both are bounded by the per-link / endpoint / global receive reserve (`acquireCapacity`).
- Bypass / overshoot: (a) the check is on the declared payload length, so a lying length prefix is covered by the limit but a message whose payload expands during deserialization (for example into on-heap objects such as a Mutation) can use more heap than its wire size. The cap bounds wire bytes, not the deserialized footprint. (b) Messages below the limit but numerous are bounded only by the reserve capacities. (c) Streaming (`StreamingInboundHandler`) and the native protocol (`native_transport_max_message_size`) are separate paths and are not governed by this check (not traced in depth).

**A4. Other consumers.** The same memory is shared with: `internode_application_{send,receive}_queue_{capacity,reserve_endpoint_capacity,reserve_global_capacity}` (aggregate caps, 4MiB/128MiB/512MiB), with the config validation in `DatabaseDescriptor.java:974-989` forcing the per-message cap to be <= each reserve; the Netty buffer pool / BufferPool used for frames; native-transport buffers; memtables, caches and compaction buffers on heap and off heap. These are outside this constraint.

**A5. Evidence beyond the source.** none (no web access used; tests: `test/unit/org/apache/cassandra/net/OutboundConnectionsTest.java:103` `getConnection_Gossip_Oversized`, `ProxyHandlerConnectionsTest.java:181` sets the limit via `setInternodeMaxMessageSizeInBytes`).

## B. Verification solution

**B1. Claim under test.** A message whose on-wire size exceeds `internode_max_message_size` is rejected (`OversizedMessageException`) at the receive-side `inferMessageSize` check before any capacity is acquired or any message buffer is retained, so peak memory that one such message can pin on the receiver is bounded by the limit rather than by the sender's message size. Falsified if the receiver holds the oversized message's bytes (direct-buffer / heap growth proportional to the message size) or processes it despite size > limit.

### B2. Unit tier

**B2a. Environment and build.** Local clone of the tag on local disk (`git clone` of `/proj/misconfiguration-PG0/git-repos/cassandra-src` into `$WORK/cassandra`, JDK 11, Ant). Add a new test class `test/unit/org/apache/cassandra/net/InferMessageSizeLimitTest.java` in the package `org.apache.cassandra.net` (needed because `inferMessageSize` is package-private, `Message.java:777`), modelled on `MessageTest.java`. Build with `ant jar` in the clone, then run `ant testsome -Dtest.name=org.apache.cassandra.net.InferMessageSizeLimitTest`. JVM: default test options (`-Xmx1g`), `DatabaseDescriptor.daemonInitialization()` in `@BeforeClass`.

**B2b. Knobs.** `DatabaseDescriptor.setInternodeMaxMessageSizeInBytes(L)` with L in {64 KiB, 1 MiB, 16 MiB}. The payload size P is varied relative to L: P = {L-1KiB, L+1KiB-overhead boundary, 2L, 8L}. Boundaries are tested exactly by computing the serialized size first and setting L = serializedSize and L = serializedSize-1.

**B2c. Workload.** Build `Message.out(Verb.ECHO_REQ, payload)` style messages. Use a verb whose payload is a simple byte holder if available (otherwise a `Mutation` with one blob cell, as in `MessageTest`). Serialize with `Message.serializer.serialize(msg, DataOutputBuffer, version)`, so `size = msg.serializedSize(version)` is known. Feed the bytes to `Message.serializer.inferMessageSize(buf, 0, buf.limit())`. Also feed only the header + length-prefix bytes (truncate the payload) to show the check fires before payload arrival. Arithmetic: with L=1MiB and P=2MiB, size ~ 2MiB+~30 B > L.

**B2d. Observables and instruments.** Return value or thrown `OversizedMessageException` (message text contains size and limit, `Message.java:1147`); `size` returned equals `serializedSize`. Heap not directly measured at this tier (the usage-side value is `size`). Cannot be observed: receiver buffer retention (cluster tier).

**B2e. Procedure.** 1) Clone and build. 2) Write the test: for each (L, P) set limit, serialize, call `inferMessageSize`, record result/exception. 3) Truncated-payload case: pass only the first `headerLen+vintLen` bytes. 4) Run `ant testsome`. 5) Delete the clone.

**B2f. Predictions.** For serializedSize <= L: returns exactly serializedSize. For serializedSize = L+1 and larger: throws `OversizedMessageException` with the message text "Message of size N bytes exceeds allowed maximum of L bytes", N = serializedSize. Truncated payload: still throws when header + length prefix are present (decision is made without the payload), returns -1 if the length vint itself is incomplete. The result depends only on L, not on JVM heap.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Throws iff size > L, at exact boundary L = size-1 | Mechanism works as traced (claim holds at unit level) |
| Returns size although size > L | Claim wrong (check not enforced here) |
| Throws for size <= L | Off-by-one or different quantity compared than traced |
| Truncated payload returns -1 although the length vint is present and size > L | Check needs the payload to arrive first, so the receiver would buffer it first: claim wrong |
| Result changes with JVM -Xmx | Unexpected dependence, investigate |

**B2h. Controls.** Same message with L set to Integer.MAX_VALUE (or 128MiB) passes; two different L values on the same bytes flip the result, which isolates the knob; serializedSize computed independently by `Message.serializer.serializedSize`.

### B3. Cluster tier

**B3a. Environment and build.** Two nodes on one Linux host (or two hosts), local-disk clone built with `ant jar`, JDK 11. Node data, commitlog, hints and saved caches under `$WORK/nodeN/` on local disk with at least 5 GiB free each. Each node `-Xms1G -Xmx1G`, `-XX:MaxDirectMemorySize=1G` (set in `conf/jvm11-server.options` of the clone, not the shared tree), distinct loopback IPs (127.0.0.1, 127.0.0.2), `endpoint_snitch: SimpleSnitch`, `num_tokens: 4`, 127.0.0.1 as seed, `commitlog_segment_size: 32MiB` (so max mutation = 16MiB is above the test sizes), `native_transport_max_message_size` left at the default or raised to 32MiB so the client frame is accepted. Keyspace `ks` with RF=2 so every write is sent internode. Per-node `internode_max_message_size` settings are in B3b. JMX enabled on 7199/7299 for sampling.

**B3b. Knobs.** `internode_max_message_size` in `cassandra.yaml` (restart required). Runs:
- R1: A=16MiB, B=16MiB (control, both permit).
- R2: A=16MiB, B=1MiB (receiver stricter than sender: exercises the inbound check at `Message.java:817`; sender passes its own outbound checks).
- R3: A=1MiB, B=1MiB (sender-side rejection at `OutboundConnection.java:331`).
All values satisfy `DatabaseDescriptor.java:974-989` because the reserves are 128MiB or more. Write sizes (blob in one row) S in {512KiB, 4MiB, 12MiB}; 12MiB stays under the 16MiB max mutation.

**B3c. Workload.** `cqlsh`/driver script (or `cassandra-stress`-free python/Java driver) connected only to node A (127.0.0.1, `LOCAL_ONE` / `ALL` so that the replica write to B must complete) doing 20 INSERTs of S bytes of a random blob into `ks.t(k int primary key, v blob)` with consistency ALL. Choose partitions such that B is a replica (RF=2 on 2 nodes guarantees it). Total traffic per size: 20 x 12MiB = 240MiB of internode data, which is larger than the 4MiB per-link limit, so reserve and per-message limits are both in play. Duration under 2 minutes each.

**B3d. Observables and instruments.** On B: (1) `java.nio:type=BufferPool,name=direct` MemoryUsed / Count via JMX and `jcmd <pidB> GC.heap_info` before, during (1 s sampling) and after the workload; (2) process RSS from `/proc/<pidB>/status` VmRSS at 1 s; (3) Cassandra metrics `org.apache.cassandra.metrics:type=InternodeInbound,scope=127.0.0.1,name=*` (received/processed bytes, corrupt frames, pending counts, `ReceivedBytes`, `ProcessedBytes`); (4) `system.log` on both nodes for "Message of size N bytes exceeds allowed maximum" and for channel close / reconnect messages; (5) client-side outcome (write success or timeout/exception); (6) `nodetool tpstats` on B for dropped MUTATION and `select count(*)` on the table at consistency ONE on each node. Cannot be observed directly: per-message Netty ByteBuf retention (inferred from direct pool and RSS deltas).

**B3e. Procedure.** 1) `git clone` the source into `$WORK/cassandra`, `ant jar`. 2) Create node dirs, write both yaml files and set the per-run limits. 3) Start B and then A (seed first if needed), wait for `UN` in `nodetool status`; create keyspace/table with RF=2. 4) Record baseline (direct pool, RSS, heap) on B. 5) Run the workload for S=512KiB, 4MiB, 12MiB, 20 writes each, sampling every second to a CSV. 6) Collect logs and metrics. 7) Stop both nodes, change limits per run, wipe node dirs, repeat for R1-R3. 8) At the end, `pkill`-free cleanup: stop by PID, check `pgrep -f CassandraDaemon` is empty, delete `$WORK`.

**B3f. Predictions.** R1: all writes succeed for all S; B's direct pool peaks during 4MiB/12MiB (at least S above baseline, bounded by the reserve limits <= 128MiB). R2: S=512KiB succeeds; S=4MiB and 12MiB writes at ALL fail or time out on the coordinator, and B logs "Message of size ~S bytes exceeds allowed maximum of 1048576 bytes" (or the channel is closed); B's peak direct memory during these runs stays below baseline + a small constant (order of the per-link 4MiB capacity and frame buffers, not tens of MiB x number of writes), and does not scale with S; no oversized row is present on B. R3: the same failure with the exception raised at A (`OversizedMessageException` in A's log / write failure) and B's direct memory flat; B receives nothing of S>=4MiB. Relation: B's peak memory increment in R2 for S=12MiB is much smaller than in R1 for S=12MiB (<= 1/3 of it).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| R2 large S fails, B logs exceeds-max, B peak memory increment much lower than R1 and flat in S | Claim supported: the limit caps what the receiver holds |
| R2 large S succeeds and the row is present on B | Claim wrong: inbound check not effective (or the limit not applied) |
| R2 fails but B's direct pool/RSS grows with S like R1 | Claim wrong in memory terms: bytes are buffered before the check despite the rejection |
| R3 write fails with exception on A and nothing arrives at B | Outbound check works as traced (A3 item 3) |
| R1 shows no memory growth at B for large S | Workload did not reach the limit or instrument is blind; result not confirmed, repeat with bigger S or finer sampling |
| B restarts the channel repeatedly and memory climbs across retries | Retry amplification overshoot: note as bypass, claim partly wrong |

**B3h. Controls.** R1 is the control (limit not binding, same workload, same S). Also: same S and same node but limit varied (R1 vs R2) isolates the knob; run S=512KiB (below all limits) in every run to show the instrument and path work; repeat each run twice; fixed heap and direct memory so GC does not mask changes (force `jcmd GC.run` before the baseline); check `nodetool tpstats` and logs to exclude other drop causes (timeouts from the write timeout setting rather than the size check).

**B4. Risks and cleanup.** Disk: each node writes at most ~240MiB x runs to commitlog/memtables; keep all under `$WORK` on local disk with >= 5 GiB free, check `df` before each run; do not use shared storage. Memory: 1G heap + 1G direct per node, two nodes; check host free memory first. Processes: stop A and B by PID, verify with `pgrep -f CassandraDaemon` and `ss -ltnp | grep -E '7000|9042|7199'` that nothing remains. Unit tier: delete the clone; nothing is written to the shared source tree.

## C. Sources read

- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/playbook-autonomous.md
- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/net/Message.java (770-860)
- src/java/org/apache/cassandra/config/Config.java (230-262)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (965-1000, 3085-3094)
- src/java/org/apache/cassandra/net/OutboundConnection.java (320-335, 785-796, 972-982)
- src/java/org/apache/cassandra/net/InboundMessageHandler.java (115-260 and grep)
- src/java/org/apache/cassandra/net/AbstractMessageHandler.java (grep only)
- conf/cassandra.yaml (1360-1392, grep)
- test/unit/org/apache/cassandra/net (directory listing and grep)

## D. Stage-4 feedback

`none yet`
