# internode_max_message_size — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/net/OutboundConnection.java:331` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code agent, 2026-10-19 |
| Judgment | `qualifies` (weakly): the entry is a per-message size ceiling applied on the outbound and inbound paths, so it bounds the largest single object the internode layer will queue, serialize into a buffer, or accumulate on receive. It does not bound total usage (that is the queue and reserve capacities), and it does not bound the on-heap `Message` the caller already built. |

## A. Constraint trace

**A1. The constraint.** `internode_max_message_size`, a configuration entry (`Config.java:238-239`, `DataStorageSpec.IntBytesBound`, old name `internode_max_message_size_in_bytes`). It is not in `conf/cassandra.yaml`, so it is hidden by default. Unit: bytes (int). Default: if unset, `DatabaseDescriptor.java:992-996` sets it to `min(internode_application_receive_queue_reserve_endpoint_capacity, internode_application_send_queue_reserve_endpoint_capacity)`. Both default to 128MiB (`Config.java:252,259`), so the default is 128MiB. If set, `DatabaseDescriptor.java:974-989` rejects startup unless it is <= all four reserve capacities (receive/send, endpoint/global). It is set by a yaml key, with a restart. `DatabaseDescriptor.setInternodeMaxMessageSizeInBytes` (`:3091-3094`) is an unvalidated setter, used by tests. The getter is at `:3085-3088`.

**A2. What it caps.** Heap and direct (off-heap) memory held per internode message, and indirectly the size of the transfer unit. The operand is `canonicalSize = message.serializedSize(current_version)` (`OutboundConnection.java:330`, `canonicalSize()` at `:1045-1048`, `Message.serializedSize` at `Message.java:1105-1118`, cached per version). The limit is `DatabaseDescriptor.getInternodeMaxMessageSizeInBytes()` (`:331`).

**A3. Mechanism.**
1. `enqueue()` (`OutboundConnection.java:325`) throws `ClosedChannelException` if closing (`:327`).
2. At `:330-332`, if `canonicalSize > max`, it throws `Message.OversizedMessageException` (`Message.java:1143-1148`, a `RuntimeException`). It does so before `submittedUpdater` (`:334`), `acquireCapacity` (`:335`) and `queue.add` (`:348`). So an oversized message is never queued and never counted against `internode_application_send_queue_*`.
3. `MessagingService.doSend` (`MessagingService.java:465-485`) only catches `ClosedChannelException`, so the runtime exception goes back to the caller of `send`. Whether callers handle it is not traced here, and the cluster tier observes it.
4. Second send-side check, at `OutboundConnection.java:793-794` (small/urgent path, EventLoopDelivery). It uses `serializedSize(messagingVersion)` of the peer's version, which can differ from `current_version`. It is inside a try/catch, so the message is dropped and its capacity released (not read further).
5. Third send-side check, at `:979-980` (LargeMessageDelivery), after `AsyncMessageOutputPlus` is created at `:977`.
6. Receive side, `Message.java:817-818` (`serializer.inferMessageSize`): throws `OversizedMessageException` if the framed size exceeds the limit. It applies the same value to inbound messages, bounding large-message accumulation on the receiver.
7. Outcomes: `<= max` continues to capacity acquisition. `> max` is rejected as above, with the exception message "Message of size N bytes exceeds allowed maximum of M bytes" (`Message.java:1147`).
- Bypasses and overshoots: (a) the `Message` object (payload) already exists on the caller's heap when `enqueue` runs, so rejection only prevents queue retention and wire serialization buffers. (b) `canonicalSize` uses `current_version`, the later checks use the peer's version, so a message can pass step 2 and fail step 4 or 5. (c) Messages <= max can still be many, bounded by the queue and reserve capacities, not by this entry. (d) A node with different values from its peer (the entry is per node) rejects on receive what the sender accepted.

**A4. Other consumers.** Per-link send queue capacity `internode_application_send_queue_capacity` (4MiB) plus send reserves (128MiB endpoint, 512MiB global); the receive equivalents; `max_mutation_size` and client request limits (rejected before reaching the internode layer); `networking_cache_size` (frame buffer pool); `OTCP_LARGE_MESSAGE_THRESHOLD` (64KiB default, `CassandraRelevantProperties.java:388`, `OutboundConnections.java:69`), which routes messages to the LARGE connection; and all of memtables, caches and so on on the same heap.

**A5. Evidence beyond the source.** none (design reading only; no runs).

## B. Verification solution

**B1. Claim under test.** No internode message larger than `internode_max_message_size` is ever queued or accumulated by the sender or receiver (rejected messages add 0 to outbound pending bytes), and the peak per-message memory the internode layer holds tracks the setting (more of it with a bigger limit, none above it). The claim is not that total usage is capped.

### B2. Unit tier

**B2a. Environment and build.** Local clone of the tag on local disk (not the shared tree): `git clone --branch cassandra-5.0.9 <shared> /local/c5`. JDK 11, Ant. `ant build-test` (or `ant jar` plus a compiled test). Add a JUnit test, `MaxMessageSizeProbeTest`, in package `org.apache.cassandra.net` under the local clone's `test/unit` (package-private access to `OutboundConnection`), modelled on `ConnectionTest`/`ConnectionTest.setup`. Run with `ant testsome -Dtest.name=org.apache.cassandra.net.MaxMessageSizeProbeTest`, default test JVM options, `-Xmx1g`.

**B2b. Knobs.** `DatabaseDescriptor.setInternodeMaxMessageSizeInBytes(L)` with L in {64KiB, 1MiB, 8MiB}. The payload size P is varied around L as described in B2c. Keep `send_queue_capacity` at its 4MiB default so L=8MiB also exceeds the per-link capacity and exercises the reserve.

**B2c. Workload.** One `OutboundConnection` of `ConnectionType.LARGE_MESSAGES` toward a loopback `InetAddressAndPort` that is not listening (as in `ConnectionTest`), or a started `InboundSockets`. Messages are built with a byte-array payload verb whose serializer is known, so S = `message.serializedSize(current_version)` is computed first and P adjusted to get S in {L-1, L, L+1, 2L}. Arithmetic: S is read from the object, so no estimate is needed.

**B2d. Observables and instruments.** Whether `enqueue` throws `OversizedMessageException`; `connection.pendingBytes()`, `pendingCount()`, `submittedCount()`, `overloadedCount()`; JVM `Runtime.totalMemory()-freeMemory()` before and after, only as a sanity check. Not observable: heap held by the caller's `Message`.

**B2e. Procedure.**
1. Set L, init `DatabaseDescriptor.daemonInitialization()` (or the test base class).
2. For each S in {L-1, L, L+1, 2L}: build the message, call `enqueue`, record the result, `pendingBytes()` and `submittedCount()`.
3. Repeat with L = 64KiB, 1MiB, 8MiB.
4. Control: same S values with `setInternodeMaxMessageSizeInBytes(Integer.MAX_VALUE)`.
5. Cleanup: close the connection, `MessagingService.instance().shutdown`.

**B2f. Predictions.** For each L: S = L-1 and S = L are accepted (pendingBytes rises by S, submittedCount +1). S = L+1 and 2L throw `OversizedMessageException`, with pendingBytes and submittedCount unchanged (the check is before `submittedUpdater`). With the control (no limit) all four are accepted, subject to capacity outcomes.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Exactly the S > L cases throw and add 0 to pendingBytes/submittedCount | Claim holds at the check |
| An S > L message is queued (pendingBytes rises) | Claim refuted |
| An S <= L message throws | Off-by-one or version-size mismatch; record the sizes |
| Control accepts everything | Rejections are caused by the knob |

**B2h. Controls.** Unlimited control (B2e step 4). Use the same payload type across runs so serializer differences are excluded. Check the size at both `current_version` and the peer's version (they should be equal for a same-version loopback).

### B3. Cluster tier

**B3a. Environment and build.** 2 nodes (127.0.0.1, 127.0.0.2) from a local clone built with `ant jar`; separate local-disk dirs for data, commitlog, hints, saved_caches (about 5GiB free each, known size). JDK 11. `MAX_HEAP_SIZE=1G`, `HEAP_NEWSIZE=256M`, `-XX:MaxDirectMemorySize=1g`; GC logging and `-Xlog:gc*`. Config: `num_tokens: 1`, `endpoint_snitch: SimpleSnitch`, `write_request_timeout: 30s`.

**B3b. Knobs.** `internode_max_message_size` in {1MiB, 8MiB} (yaml; restart each time), added to both nodes. The positive control is the 8MiB run (the limit does not bind, memory use is expected to move). Keep the reserves at their defaults (128MiB) so validation passes. Keep `max_mutation_size` at its default (16MiB) so the client write is not rejected earlier.

**B3c. Workload.** Keyspace RF=2, so every write is sent to the other node. Table `(k int primary key, v blob)`. Writes with `CONSISTENCY ALL` at the coordinator on node1, 16 parallel client threads, each writing a 2MiB blob per request (payload 2,097,152 bytes, so S is about 2.0MiB), 200 writes per thread (about 6.4GiB offered, 3.2GiB on the wire per node if accepted). 2MiB > 1MiB (rejected at L=1MiB) and < 8MiB (accepted at L=8MiB). Control workload: 256KiB blobs under L=1MiB (always allowed). Duration to completion, about a few minutes.

**B3d. Observables and instruments.** JMX `org.apache.cassandra.metrics:type=Messaging` / `InternodeOutbound` per-peer metrics `LargeMessagePendingBytes`, `PendingBytes`, `ExpiredCount`, `OverloadedCount` (sampled every 1s); `nodetool tpstats` dropped counts; `jcmd <pid> GC.heap_info`, direct buffer memory via MBean `java.nio:type=BufferPool,name=direct` (`MemoryUsed`, 1s sampling) and RSS from `/proc/<pid>/status`; node1 `system.log` for "exceeds allowed maximum"; client-side error counts. Not observable: transient heap held by serialization inside a single GC cycle.

**B3e. Procedure.**
1. Clone, build, create the two configs with L=1MiB, start both nodes, wait for `UN`.
2. Create keyspace and table; run the 2MiB workload; sample metrics throughout.
3. Record client successes and errors, log hits, peak `LargeMessagePendingBytes`, peak direct `MemoryUsed`, peak heap used.
4. Run the 256KiB control workload on the same setup.
5. Stop both nodes, wipe data dirs, change L to 8MiB, restart and repeat step 2.
6. Stop all processes, `pgrep -f CassandraDaemon` must be empty, delete the local dirs.

**B3f. Predictions.** L=1MiB with 2MiB blobs: node1 log shows "Message of size ~2.1e6 bytes exceeds allowed maximum of 1048576 bytes"; client writes at CL=ALL fail (error or timeout; the exact failure mode is not known from the source and is recorded); peak `LargeMessagePendingBytes` about 0 on node1 to node2; no direct-memory growth from large payloads. L=1MiB with 256KiB blobs: all succeed. L=8MiB with 2MiB blobs: writes succeed; peak `LargeMessagePendingBytes` > 0 and up to about 16 x 2MiB (limited by the 4MiB per-link capacity plus reserves); peak direct `MemoryUsed` higher than in the L=1MiB run by about the same order (MiB to tens of MiB).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| L=1MiB rejects 2MiB writes, pending bytes about 0; L=8MiB accepts them with pending bytes and direct memory up | Claim holds; the limit governs the largest per-message memory |
| L=1MiB 2MiB writes succeed, or pending bytes rise to a 2MiB-scale | Claim refuted (another path carries it, or the version size differs) |
| Both runs show similar memory despite accepted/rejected differing | The entry caps message count of work, not memory significant here (suggests `does not cap` at node scale) |
| 8MiB run shows no increase in pending bytes | Workload did not reach the boundary or the control did not move; not confirmed |
| 256KiB control fails at L=1MiB | Setup problem |

**B3h. Controls.** The 256KiB workload (always under the limit); the 8MiB run as positive control (same workload, limit not binding); identical heap/GC settings; same coordinator; start from empty data dirs; check node2 is not a coordinator.

**B4. Risks and cleanup.** Disk: up to about 6.4GiB offered, written only on accepted runs, to a local dir of known size (>= 20GiB free); commit log and hints on local disk, hints disabled (`hinted_handoff_enabled: false`) so rejected writes do not fill disk. Never build in the shared tree. Unit tier leaves no files outside the local clone. After runs, kill both JVMs and verify `pgrep -f CassandraDaemon`, `ss -ltnp` for ports 7000/9042 on both loopbacks, and remove the clone and data dirs.

## C. Sources read

- `src/java/org/apache/cassandra/net/OutboundConnection.java` (lines 290-370, 440-480, 770-800, 960-995, 1040-1050)
- `src/java/org/apache/cassandra/net/Message.java` (800-825, 1100-1150)
- `src/java/org/apache/cassandra/net/MessagingService.java` (465-490)
- `src/java/org/apache/cassandra/net/OutboundConnections.java` (60-100)
- `src/java/org/apache/cassandra/config/Config.java` (230-262)
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (965-1000, 3085-3094)
- `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java` (388)
- `conf/cassandra.yaml` (1370-1392)
- `cases/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided.md` (format reference only)

## D. Stage-4 feedback

`none yet`
