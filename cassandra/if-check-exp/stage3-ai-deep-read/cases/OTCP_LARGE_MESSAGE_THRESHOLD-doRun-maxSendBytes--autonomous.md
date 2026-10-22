# OTCP_LARGE_MESSAGE_THRESHOLD — verification solution  <!-- file: cases/OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/net/OutboundConnection.java:767` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-opus-5-5, Claude Code 2.1.305, 2026-10-22 |
| Estimate | `negative`. The line-767 check (`maxSendBytes == 0`) only tests "nothing left to send". Its operand `maxSendBytes` comes from `OTCP_LARGE_MESSAGE_THRESHOLD`. That threshold caps the payload capacity of one transient frame buffer per small or urgent connection (at most about 128 KiB), not the node's outbound memory. Node-level outbound memory is set by the send-queue capacities and the fixed flush watermarks. |
| Ground | `maxSendBytes = min(pendingBytes() - flushingBytes, LARGE_MESSAGE_THRESHOLD)` (`OutboundConnection.java:766`) sizes only the buffer allocated at `:782`. The queued bytes behind it (`pendingBytes`, on heap as `Message` objects) are capped by `acquireCapacity` against `internode_application_send_queue_*` (`:383-440`). Frames waiting in Netty are capped by `flushHighWaterMark` = 64 KiB (`OutboundConnectionSettings.java:104`, `OutboundConnection.java:854`). So the threshold adds at most one frame of ≤ about 128 KiB per connection (the frame format caps payload below 128 KiB, `FrameEncoderCrc.java:71`). That is negligible next to the 4 MiB + 128 MiB + 512 MiB send-queue limits and the 128 MiB networking pool. |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `OTCP_LARGE_MESSAGE_THRESHOLD`.
- **Kind:** JVM system property `cassandra.otcp_large_message_threshold`.
- **Declared at:** `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java:388`, as `OTCP_LARGE_MESSAGE_THRESHOLD("cassandra.otcp_large_message_threshold", convertToString(1024 * 64))`.
- **Unit:** bytes. The default is 65536.
- **Derived value:** read once into the static final `OutboundConnections.LARGE_MESSAGE_THRESHOLD = OTCP_LARGE_MESSAGE_THRESHOLD.getInt() - max(max(HEADER_LENGTH, HEADER_AND_TRAILER_LENGTH), FrameEncoderLZ4.HEADER_AND_TRAILER_LENGTH)` (`src/java/org/apache/cassandra/net/OutboundConnections.java:69-70`).
  - The terms are `HEADER_LENGTH` = 8+1+4+4+4 = 21 (`:62-66`), `FrameEncoderCrc.HEADER_AND_TRAILER_LENGTH` = 10 (`FrameEncoderCrc.java:37`) and `FrameEncoderLZ4.HEADER_AND_TRAILER_LENGTH` = 12 (`FrameEncoderLZ4.java:50`).
  - So **LMT = property − 21**, and the default LMT is 65515.
- **How to set it:** only with `-Dcassandra.otcp_large_message_threshold=<bytes>` at JVM start (for example `JVM_EXTRA_OPTS` or `conf/jvm-server.options`). There is no yaml key and no JMX setter.
- **Restart:** a change needs a restart, because the field is `static final`.
- **Validation:** the value is not validated. A value whose LMT exceeds about 128 KiB produces frames the encoder rejects (A3, step 6).

**A2. What it caps.**
- **Resource:** off-heap memory, from the `networking` `BufferPool` (direct memory).
- **Quantity limited:** the payload capacity requested for **one outbound frame buffer** on a small or urgent connection (`EventLoopDelivery`).
- **Check at line 767:** it compares `maxSendBytes`, the bytes to try to pack into this frame, against `0` (nothing to do). The constraint enters through the `min(..., LARGE_MESSAGE_THRESHOLD)` at `:766`.
- **Second role, outside this check:** LMT is the size above which a message is routed to the `LARGE_MESSAGES` connection (`OutboundConnections.java:215-229`). The receive side also uses it as the large-message threshold (`InboundMessageHandlers.java:145`, `InboundMessageHandler.java:148`).

**A3. Mechanism.** All lines are in `src/java/org/apache/cassandra/net/OutboundConnection.java` unless noted.

1. Small and urgent connections use `EventLoopDelivery`. Large connections use `LargeMessageDelivery` (`:316-318`).
2. `doRun` returns early if a previous overflow left the connection not writable (`:759-760`).
3. `:766` computes `maxSendBytes = (int) min(pendingBytes() - flushingBytes, LARGE_MESSAGE_THRESHOLD)`.
   - `pendingBytes()` (`:1641-1644`) is the canonical size of every message accepted by `enqueue` and not yet released.
   - `flushingBytes` is the part already handed to Netty and not yet completed.
4. **`:767` (the target): `if (maxSendBytes == 0) return false;`.** No buffer is allocated if there is nothing unsent. This is an emptiness test, not a capacity test.
5. `:782` allocates `sending = established.payloadAllocator.allocate(true, maxSendBytes)`.
   - For CRC framing that is `new Payload(..., capacity, 6, 4)` (`FrameEncoderCrc.java:40-41`).
   - The constructor calls `bufferPool.getAtLeast(payloadCapacity + 10, OFF_HEAP)` on `BufferPools.forNetworking()` (`FrameEncoder.java:32,64`).
   - `getAtLeast` may return a larger buffer rounded up to the pool's allocation unit, `NORMAL_CHUNK_SIZE/64` = 2 KiB (`BufferPool.java:128-129,899-904,946`). `buffer.limit = capacity - trailer` (`FrameEncoder.java:67`).
   - So the usable payload is at most `roundUp(LMT+10, 2048) - 10`. That is a slight overshoot of LMT, by less than 2 KiB.
6. **Packing loop (`:785-834`).** Messages are serialized while they fit in `sending.remaining()` (`:795`), stopping at the first that does not fit (`:803-804`).
   - **Bypass:** if the *first* message does not fit, the buffer is released and replaced with one of `messageSize` bytes (`:806-812`). This can happen because the message's size at the negotiated version exceeds its canonical size, or because LMT is smaller than a message routed here.
   - Only `internode_max_message_size` bounds that replacement buffer (`:793`).
   - Messages larger than LMT normally never reach this path, because `connectionTypeFor` sends them to `LARGE_MESSAGES` (`OutboundConnections.java:215-229`). A connection type forced by the caller bypasses that routing (`:212-213`).
   - **Frame-format ceiling:** `FrameEncoderCrc.encode` throws `IllegalArgumentException("Maximum payload size is 128KiB")` when the payload is ≥ 1<<17 (`FrameEncoderCrc.java:71-72`). `FrameEncoderLZ4.java:73` and `FrameEncoderUnprotected.java:53` have the same check.
   - So a property above about 131 000 does not give bigger frames. It gives failed flushes and channel invalidation (`:887`, `:894-898`).
7. **Hand-off to Netty (`:838-840`).** `finish()` returns the unused tail to the pool through `putUnusedPortion` (`FrameEncoder.java:97-104`), and the frame is passed to `writeAndFlush`.
   - If the write completes synchronously, the buffer is freed at once (`:843-848`).
   - Otherwise `flushingBytes += canonicalSize` (`:851`). When `flushingBytes >= settings.flushHighWaterMark` (default `1 << 16`, `OutboundConnectionSettings.java:104`), `isWritable = false` and delivery stops (`:854-859`). It resumes at `flushLowWaterMark` = `1 << 15` (`:871-875`).
   - So off-heap held in unsent frames per connection is at most about `flushHighWaterMark - 1 + one frame`, that is at most about 64 KiB + LMT.
8. **What bounds the queued data:** `enqueue` → `acquireCapacity` (`:331-341`, `:383-440`), which compares `pendingBytes(next)` with `pendingCapacityInBytes` (`internode_application_send_queue_capacity`, default 4 MiB). It then draws on the endpoint and global reserves (`internode_application_send_queue_reserve_endpoint_capacity`, 128 MiB, and `..._global_capacity`, 512 MiB; `conf/cassandra.yaml:1386-1388`). LMT does not appear there.

**Outcomes of the 767 check:**
- *true* (nothing unsent): return, with nothing allocated.
- *false*: allocate one buffer of about `min(unsent, LMT)` bytes.

LMT never refuses or drops data. It only splits the backlog into frames of at most LMT bytes.

**A4. Other consumers.**
- **Heap:** the queued `Message` objects counted in `pendingBytes`, capped by the send-queue limits.
- **Off-heap, networking pool:**
  - in-flight frames, capped by the flush watermarks;
  - `LargeMessageDelivery` buffers (`AsyncMessageOutputPlus`, `:977`);
  - inbound frame decoders and their receive queues (`internode_application_receive_queue_*`);
  - native-transport framing, which shares `BufferPools.forNetworking()`, capped at `networking_cache_size`, default min(128 MiB, heap/16) (`DatabaseDescriptor.java:573-574`, `BufferPools.java:44-45`). Requests beyond the cap become overflow allocations (`BufferPool.java:233-239,923`).
- **Outside the JVM:** kernel socket send and receive buffers.
- **Disk:** hints, written once a peer is marked down. They are not related to this constraint.

**A5. Evidence beyond the source.**
- CASSANDRA-15066, the internode messaging rewrite that introduced `OutboundConnection` and `EventLoopDelivery`: https://issues.apache.org/jira/browse/CASSANDRA-15066.
- Metrics docs in the tree: `doc/modules/cassandra/pages/managing/operating/metrics.adoc:882-967` (BufferPool metrics).
- Tests that only use LMT for routing: `test/unit/org/apache/cassandra/net/ConnectionTest.java:300-350`, `test/unit/org/apache/cassandra/net/OutboundConnectionsTest.java:70,110`, `test/distributed/org/apache/cassandra/distributed/test/LargeMessageTest.java:39`.
- The local clone is shallow, so there is no git history beyond the release commit.

## B. Verification solution

**B1. Claim under test.** Varying `cassandra.otcp_large_message_threshold` (16384 / 65536 / 131072) changes the size of each small-connection frame buffer, roughly in proportion to LMT. It does **not** change how much outbound internode memory a node holds:
- peak queued bytes (`pendingBytes`, heap) stay at the send-queue capacity limits;
- peak networking-pool usage (off-heap) differs across those LMT values by less than about one LMT per backlogged connection.

Changing the send-queue capacity, under the same workload, does move both. The claim is wrong if either of the following holds:
- the peak `pendingBytes` follows LMT;
- networking-pool or direct-memory usage scales with LMT by much more than about 2 × ΔLMT.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11.0.32.1 and Ant 1.10.12.
- Clone the tag to local disk. Never build in `/proj/...`:
  ```
  mkdir -p /tmp/lmt && git clone --depth 1 --branch cassandra-5.0.9 /proj/misconfiguration-PG0/git-repos/cassandra-src /tmp/lmt/src
  ```
- Build: `cd /tmp/lmt/src && ant -Dno-checkstyle=true build-test`.
- New test file: `/tmp/lmt/src/test/unit/org/apache/cassandra/net/LargeMessageThresholdFrameTest.java`. It is in package `org.apache.cassandra.net` so that it can use the package-private `OutboundDebugCallbacks`, `withDebugCallbacks`, `pendingBytes()` and `settings()`.
- Copy the harness from `ConnectionTest.doTestManual` (`ConnectionTest.java:237-263`):
  - `DatabaseDescriptor.daemonInitialization(); CommitLog.instance.start();` in `@BeforeClass`;
  - one `SocketFactory`;
  - an `InboundSockets` on `FBUtilities.getBroadcastAddressAndPort()`;
  - `new OutboundConnection(SMALL_MESSAGES, template, reserve)`.
- The value is passed to the test JVM as `-Dtest.jvm.args="-Dcassandra.otcp_large_message_threshold=<V>"` (`build.xml:94,1192`).
- **Amendment S4-A1 (stage-4 audit, 2026-10-22; execution detail, B2f/B2g unchanged).** Paths for the run on `pc06`: the clone is `~/cassandra-otc` (cloned from `~/cassandra-run1`, tag `cassandra-5.0.9`, `ant build-test`), the test is copied in by the harness script `harness/OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous/unit-run.sh` and removed after, and logs go to `~/stage4-logs/otc/`. `/tmp/lmt` is not used.

**B2b. Knobs.**
- Primary: property V ∈ {16384, 65536 (default), 131072}, giving LMT ∈ {16363, 65515, 131051}.
  - 131072 is the largest value that still fits the frame format: 131051 + 10 ≤ 131072 = `NORMAL_CHUNK_SIZE`, and the payload stays below 1<<17.
  - 16384 is well below the default but still about 16 messages per frame.
- Fixed in the same test: send-queue capacity C, set through `template.withApplicationSendQueueCapacityInBytes(C)` and `withApplicationReserveSendQueueCapacityInBytes(R, new ResourceLimits.Concurrent(R))`, as in `ConnectionTest.java:357-359`.
  - The main runs use C = 4 MiB (4194304) and R = 65536.
- Positive control knob: C ∈ {1 MiB, 4 MiB} at V = 65536.
- Framing is set explicitly with `withFraming(OutboundConnectionSettings.Framing.CRC)`.

**B2c. Workload.**
- Register a serializer for `Verb._TEST_1` that writes exactly 1000 bytes (125 `writeLong`) and reports `serializedSize = 1000`. Use `unsafeSetSerializer` and a no-op handler, as in `ConnectionTest.java:386-405`. Set the expiry long with `Verb._TEST_1.unsafeSetExpiration(u -> u.convert(120, SECONDS))`, so nothing expires.
- Let S = `Message.out(_TEST_1, new Object()).serializedSize(current_version)`. Log it; it is about 1000 bytes plus a header of a few dozen bytes.
- **Phase 1 (fill):** do not open the inbound socket yet. Enqueue messages in a loop until `enqueue` reports overload, or until N_max = 2·C/S attempts. Count accepted messages through `outbound.submittedCount()` minus `overloadedCount()`.
  - With C = 4 MiB that is up to about 4100 accepted messages, so `pendingBytes` reaches about C.
- **Phase 2 (drain):** call `inbound.open().sync()`. The connection is established on the next retry, and `EventLoopDelivery` drains the backlog. Each frame should hold `floor(remaining/S)` messages, where remaining ≈ `roundUp(LMT+10, 2048) - 10`.
- **Arithmetic:** a backlog of C ≥ 1 MiB is much larger than LMT (at most 131 KiB). Every frame except the last is therefore limited by LMT (`min` picks LMT), so the limit is reached on every frame.

**B2d. Observables and instruments.**
1. **Per-frame payload size:** an `OutboundDebugCallbacks` passed through `template.withDebugCallbacks(...)` records `payloadSizeInBytes` from `onSendSmallFrame` (`OutboundConnection.java:839`). Record the max, the count of frames and a histogram.
2. **Networking-pool use:** `BufferPools.forNetworking().usedSizeInBytes()` and `.overflowMemoryInBytes()`, sampled every 1 ms by a daemon thread during phase 2. Record the peak minus the baseline taken just before `inbound.open()`.
3. **Queued bytes:** `outbound.pendingBytes()`, peak at the end of phase 1.
4. **Delivery check:** `outbound.sentCount()` and `sentBytes()` after the drain, and that `errorCount()` is 0.

**Not observable:** `flushingBytes` is private. Over loopback it is almost always 0 because writes complete synchronously. Pool samples also include the in-JVM inbound side; the baseline subtraction and identical runs control for that.

**Amendment S4-A2 (stage-4 audit, 2026-10-22; instrument, before any reading).** A 1 ms poller can miss a frame that lives for microseconds. So observable 2 also takes a pool sample **inside each `onSendSmallFrame` callback**: at that moment the frame's buffer is allocated and trimmed (`OutboundConnection.java:838-839`, after `finish()` at `:838`) and not yet written. poolPeakDelta is the maximum over both kinds of sample, minus the baseline. The RESULT line also prints `lmt=<OutboundConnections.LARGE_MESSAGE_THRESHOLD>`, `sent=<sentCount>` and `errors=<errorCount>`. The run stops if `lmt` ≠ V − 21, because that would mean the property did not reach the test JVM.

**B2e. Procedure.**
1. Write the test with three methods: `fillAndDrain_C4M`, `fillAndDrain_C1M` and `fillAndDrain_C4M_repeat`. Each prints one line of the form `RESULT V=<V> C=<C> S=<S> accepted=<n> pendingPeak=<b> frames=<f> maxFrame=<m> poolPeakDelta=<p> overflowDelta=<o>`.
2. For each V in 16384, 65536 and 131072, run:
   ```
   cd /tmp/lmt/src && ant testsome -Dtest.name=org.apache.cassandra.net.LargeMessageThresholdFrameTest -Dtest.jvm.args="-Dcassandra.otcp_large_message_threshold=$V" -Dno-build-test=false
   ```
3. Collect the lines with:
   ```
   grep RESULT build/test/output/TEST-org.apache.cassandra.net.LargeMessageThresholdFrameTest.xml
   ```
4. Repeat each V three times and keep all three readings.

**B2f. Predictions (stated before running).**
- **maxFrame:**
  - V = 16384: in [16363 − S, 16374], that is roughly 15.4–16.4 KB.
  - V = 65536: in [65515 − S, 65526].
  - V = 131072: in [131051 − S, 131062].
  - Formula: maxFrame ≤ `roundUp(LMT+10,2048) − 10` and > that minus S.
- **frames:** about accepted·S / maxFrame, that is about 256 / 64 / 32 frames for C = 4 MiB.
- **pendingPeak:** the same for all three V, in [C − S, C + R]; for C = 4 MiB, about 4.13–4.26 MB. It does not depend on V.
- **poolPeakDelta:** at most about 2 × (LMT + 2 KiB) above baseline, from one sending frame plus at most one decoding frame on the inbound side. Across V the spread is less than about 300 KiB. It never comes near C.
- **overflowDelta:** 0 for every V. Every request is ≤ 128 KiB and the pool is far from its 128 MiB cap.
- **Positive control:** with C = 1 MiB and V = 65536, pendingPeak is about 1.05–1.11 MB, a quarter of the C = 4 MiB value. maxFrame is unchanged.

**Amendment S4-A3 (stage-4 audit, 2026-10-22; from the source, before any reading).**
- **poolPeakDelta per reading, corrected bound.** The filed "≤ 2 × (LMT + 2 KiB)" leaves out two terms:
  - the outbound flushing allowance of up to `flushHighWaterMark` = 64 KiB (A3, step 7);
  - the inbound side's Netty read buffer, which comes from the same networking pool (`InboundConnectionInitiator.java:108`, `GlobalBufferPoolAllocator`; Netty's adaptive receive allocator grows to 64 KiB).

  The bound is therefore about 128 KiB + 2·(LMT + 2 KiB): about 164 / 263 / 391 KiB at V = 16384 / 65536 / 131072. The spread prediction is unchanged: less than about 300 KiB across V. The expected spread is about ΔLMT (≈ 112 KiB, the sending frame) to 2·ΔLMT (≈ 225 KiB).
- **poolPeakDelta ≥ maxFrame** in every reading, because the frame is held when the S4-A2 callback samples (`roundUp(payload + 10, 2048)` bytes).
- **Delivery:** `errors` = 0 and `sent` = accepted at every V and C. At V = 131072 the request is 131061 bytes, which rounds to 131072 = `NORMAL_CHUNK_SIZE`, so the payload is at most 131062 < 1<<17 and `FrameEncoderCrc.java:71` does not throw.
- **pendingPeak band.** In phase 1 the link is failing to connect, so `acquireCapacity` refuses at C with no reserve (`OutboundConnection.java:409-413`). pendingPeak ∈ (C − S, C] is expected, inside the filed band [C − S, C + R]. For C = 1 MiB the filed "about 1.05–1.11 MB" is read as the band [1,048,576 − S, 1,114,112] B.
- **Aggregation.** For each V, the C = 4 MiB readings are the six lines from `fillAndDrain_C4M` and `fillAndDrain_C4M_repeat` in the three `ant` runs. A per-V value is the median of those six. The positive control compares the three `fillAndDrain_C1M` readings at V = 65536 with that V's C = 4 MiB readings.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| maxFrame follows LMT as predicted; pendingPeak is the same across V; pendingPeak moves with C | **Claim confirmed:** LMT sizes frames only, and queued usage is governed by C. |
| pendingPeak changes with V by more than S | **Claim refuted:** queued usage follows LMT. |
| poolPeakDelta scales with V by much more than 2·ΔLMT (for example several MB) | **Claim refuted:** off-heap usage follows LMT. |
| pendingPeak does not change between C = 1 MiB and 4 MiB | Positive control failed; **not confirmed**. Check the setters and the fill loop. |
| maxFrame far below LMT (backlog not formed, or frames sent before phase 2) | Limit not reached; **not confirmed**. Make sure inbound was closed during phase 1. |
| maxFrame > `roundUp(LMT+10,2048) − 10` | The mechanism differs from the trace, through the oversized-first-message path. Investigate S at the negotiated version. |
| errorCount > 0 at V = 131072 | The frame ceiling was hit (A3, step 6). Record it; this is a correctness limit of the property, not a memory cap. |

**Amendment S4-A4 (stage-4 audit, 2026-10-22; before any reading).** The table above did not include B1's pool clause in its Confirmed row. It also left some outcomes with no row or no verdict. **The table below replaces it for the verdict.** Rows are applied in order: validity (U5, U7, U8), then Refuted (U2, U3), then U4, U6, U9, then U1. The first row that holds is the verdict. Values are aggregated as in S4-A3.

| Row | Observation | Meaning |
|---|---|---|
| U1 | All of the following hold: every C = 4 MiB maxFrame is in its B2f band; the per-V pendingPeak medians differ by ≤ S; every C = 1 MiB pendingPeak at V = 65536 is more than 2 MiB below that V's C = 4 MiB median; the per-V poolPeakDelta medians span < 300 KiB; every poolPeakDelta is < 1 MiB | **Confirmed:** LMT sizes frames only (about one frame of pool per side), and queued usage is governed by C |
| U2 | The per-V pendingPeak medians differ by more than S | **Refuted:** queued usage follows LMT |
| U3 | The per-V poolPeakDelta medians increase with V, and median(131072) − median(16384) > 1 MiB | **Refuted:** off-heap usage follows LMT beyond one frame |
| U4 | Some C = 1 MiB pendingPeak is not more than 2 MiB below the C = 4 MiB median | Positive control failed: **Not confirmed** |
| U5 | Some maxFrame is below its B2f band (backlog not formed), or `sent` < accepted (drain incomplete) | Limit not reached: **Not confirmed** |
| U6 | Some maxFrame is above `roundUp(LMT+10,2048) − 10` | The mechanism differs from the trace: **Not confirmed** |
| U7 | `errors` > 0 at any V | Frame ceiling or delivery failure. Record it; **Not confirmed** |
| U8 | Some poolPeakDelta < maxFrame | The instrument missed the frame: **Not confirmed** |
| U9 | The poolPeakDelta medians span ≥ 300 KiB, or some poolPeakDelta is ≥ 1 MiB, without U3's condition | Pool band missed, so flatness is not shown: **Not confirmed** |

**B2h. Controls.**
- Identical message size and backlog across V.
- The baseline sample is taken just before the drain.
- The C knob is the positive control: the same workload with a binding cap.
- Three repeats per V.
- Fixed CRC framing, so LZ4 compression does not change frame sizes.
- No `LARGE_MESSAGES` routing is involved, because the connection type is fixed to `SMALL_MESSAGES`.

### B3. Cluster tier

**B3a. Environment and build.**
- **Nodes:** two Cassandra nodes on one host, on loopback addresses 127.0.0.1 and 127.0.0.2. Everything lives on local disk under `/tmp/lmt`.
- **Build:** `cd /tmp/lmt/src && ant -Dno-checkstyle=true jar`. Then make a copy per node:
  ```
  cp -r /tmp/lmt/src /tmp/lmt/n1
  cp -r /tmp/lmt/src /tmp/lmt/n2
  ```
  `bin/` and `conf/` are used in place; data goes to `/tmp/lmt/nX/data`.
- **Per-node `conf/cassandra.yaml` changes:**
  - `cluster_name: lmt`;
  - `listen_address` and `rpc_address`: 127.0.0.X;
  - `seeds: "127.0.0.1:7000"`;
  - `data_file_directories: [/tmp/lmt/nX/data/data]`, with `commitlog_directory`, `hints_directory`, `saved_caches_directory` and `cdc_raw_directory` under `/tmp/lmt/nX/data`;
  - `write_request_timeout: 10000ms`, so queued messages do not expire before the cap binds;
  - `phi_convict_threshold: 16`;
  - `internode_compression: none`, which gives CRC framing;
  - `hinted_handoff_enabled: false`, so no hint files are written;
  - send-queue limits as in B3b.
- **Per-node `conf/cassandra-env.sh`:** `JMX_PORT="7199"` on n1 and `"7299"` on n2.
- **Environment for each launch:** `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M JVM_EXTRA_OPTS="-Dcassandra.otcp_large_message_threshold=$V -XX:NativeMemoryTracking=summary"`.
- **Stress client:** `tools/bin/cassandra-stress` from n1's copy.
- **Amendment S4-A5 (stage-4 audit, 2026-10-22; execution detail, B3f/B3g unchanged).** The tier runs on `pc06` from the one clone `~/cassandra-otc` (`ant build-test` covers `jar` and stress), not from two copies under `/tmp/lmt`:
  - each node has its own `CASSANDRA_CONF` (`~/stage4-otc/nX/conf`, a copy of the clone's `conf/` with the B3a lines and `JMX_PORT`) and `CASSANDRA_LOG_DIR` (`~/stage4-otc/nX/logs`);
  - data is in `~/stage4-otc/nX/data` on local disk (`/dev/sda3`);
  - `ulimit -n 100000` before each start;
  - a node is matched by `java` + `CassandraDaemon` + its working directory or conf path, since the command line shows only `bin/../`;
  - `JVM_EXTRA_OPTS` is set on the `bin/cassandra` command only.

**B3b. Knobs.**
- Primary: V ∈ {16384, 65536, 131072} on **both** nodes, with a restart for each value.
- Held fixed:
  - `internode_application_send_queue_capacity: 1MiB`;
  - `internode_application_send_queue_reserve_endpoint_capacity: 2MiB`;
  - `internode_application_send_queue_reserve_global_capacity: 4MiB`;
  - `internode_max_message_size: 1MiB`, required to be ≤ the reserves (`DatabaseDescriptor.java:974-989`).
  - A low cap makes the binding limit visible and reachable.
- Positive control, at V = 65536: send-queue capacity 16MiB, reserve endpoint 16MiB, reserve global 32MiB, and `internode_max_message_size: 1MiB`.
  - The predicted pending cap moves from 3 MiB to 32 MiB (capacity + endpoint reserve).
- **Amendment S4-A6 (stage-4 audit, 2026-10-22; from the source and a closed case, before any reading; B3f unchanged).** On the production path, the per-peer send reserve is read from **`internode_application_receive_queue_reserve_endpoint_capacity`** (default 128 MiB), not from the send-side key.
  - The code path: `OutboundConnectionSettings.withDefaults()` fills the field from the receive key (`:392-396`) before `withDefaultReserveLimits()` (`:329-330`) could read the send key, and `OutboundConnections.java:83-84` builds the reserve from it.
  - This was tested and confirmed in `results/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided.md` (U10, cluster arms c1/c2).
  - As filed, the plateau would therefore be C + min(128 MiB, global) = 5 MiB in the main runs and 48 MiB in the control, not 3 / 32 MiB.
  - **Fix:** both nodes also set `internode_application_receive_queue_reserve_endpoint_capacity` to the send-side endpoint value: `2MiB` in the main runs and `16MiB` in the control. That gives the intended endpoint reserve, so B3f's 3 MiB and 32 MiB stand. `internode_max_message_size: 1MiB` is still ≤ every reserve (`DatabaseDescriptor.java:974-989`).
  - The control is run twice, like each V (B3h, "two repeats per value").

**B3c. Workload.**
1. Create the schema:
   ```
   tools/bin/cassandra-stress write duration=90s cl=ONE -schema "replication(factor=2)" -col "size=FIXED(1000)" "n=FIXED(1)" -rate threads=200 -node 127.0.0.1 -mode native cql3
   ```
2. At t = 30 s, run `kill -STOP <n2 pid>`. At t = 50 s, run `kill -CONT <n2 pid>`.
3. While n2 is stopped, n1 (the coordinator and replica) keeps enqueuing 1 KB mutations to n2 on the small connection. n2 is not yet convicted, with phi 16 and only 20 s stopped.
4. **Arithmetic:** at 10 k ops/s or more, that is at least 10 MB/s into a socket that stops draining once kernel buffers (a few MB) fill. A 1+2 = 3 MiB cap is reached within about 1 s. The positive-control 32 MiB cap is reached within about 3–5 s, which is well under the 10 s timeout and the 20 s stall.
5. Total duration per run: about 2 min.

**Amendment S4-A7 (stage-4 audit, 2026-10-22; workload validity, before any reading; B3f unchanged).** The stress command becomes:

```
tools/bin/cassandra-stress write duration=90s cl=ONE no-warmup -schema "replication(factor=2)" -col "size=FIXED(1000)" "n=FIXED(1)" -rate threads=200 fixed=30000/s -node whitelist 127.0.0.1 -mode native cql3 -log interval=1s
```

- **Why `whitelist`:** with `-node 127.0.0.1` alone, the driver discovers n2 and routes about half of the requests to it as coordinator. While n2 is stopped, those requests, and the client threads waiting on them, hang, so n1's write rate and backlog would depend on routing rather than on the knobs. With `whitelist`, every request goes to n1, and n1 forwards each mutation to n2 on the small link.
- **Why `fixed=30000/s`:** it holds the offered load identical across V (B3h). 30,000/s × about 1.06 KB ≈ 32 MB/s fills the 3 MiB cap in under 1 s and the 32 MiB cap in about 1–2 s once the kernel buffers are full. The closed send-queue release case drove 30,000/s through one node on the same kind of host.

Stress runs with `CASSANDRA_CONF` and `JVM_EXTRA_OPTS` unset.

**B3d. Observables and instruments.** Sample every 1 s on n1 with `bin/nodetool -p 7199 sjk mx -mg -f Value -b <mbean>`:
- `org.apache.cassandra.metrics:type=Connection,scope=127.0.0.2_7000,name=SmallMessagePendingBytes` (queued bytes, heap). Confirm the scope first with `sjk mx -q 'org.apache.cassandra.metrics:type=Connection,*'`.
- `org.apache.cassandra.metrics:type=Connection,scope=127.0.0.2_7000,name=SmallMessageDroppedBytesDueToOverload`, which confirms the cap bound.
- `org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize` and `...name=OverflowSize` (off-heap).
- `java.nio:type=BufferPool,name=direct` attribute `MemoryUsed`, read with `-f MemoryUsed`.
- Heap used, from `bin/nodetool -p 7199 info | grep Heap`.
- At the peak (t ≈ 45 s), take a native-memory snapshot with `jcmd <n1 pid> VM.native_memory summary`.

**Not directly observable:** per-frame sizes and `flushingBytes`. The unit tier covers those.

**Amendment S4-A8 (stage-4 audit, 2026-10-22; instruments, before any reading).**
- **One JMX client.** `sjk mx` starts one JVM per attribute, too slow for six attributes a second. The harness's `Jmx.java` reads, over one JMX connection to n1 every 1 s:
  - the same beans: `SmallMessagePendingBytes`, `SmallMessageDroppedBytesDueToOverload`, networking `UsedSize` and `OverflowSize`, and `java.nio:type=BufferPool,name=direct` `MemoryUsed`;
  - also `SmallMessageDroppedTasksDueToTimeout`, Urgent/Large `PendingBytes`, and heap used (`MemoryMXBean`).

  Each row carries epoch milliseconds.
- **Heap for the control sub-prediction.** Instantaneous heap used is a G1 sawtooth of hundreds of MB, so it cannot show a 29 MB step. The B3f heap sub-prediction is read from the total of `jcmd <n1> GC.class_histogram` (live objects) taken at SIGSTOP + 12 s in every run. The control's total is compared with the mean of the V = 65536 runs.
- **NMT** summary at SIGSTOP + 15 s.
- **`nodetool info`** is not sampled.

**B3e. Procedure.**
1. Build and configure as in B3a, with send-queue settings as in B3b.
2. For each V, then the control:
   1. Start n1, wait for `nodetool -p 7199 status`, then start n2. Wait for both nodes to show `UN`. `bin/cassandra -p /tmp/lmt/nX/pid` with `CASSANDRA_CONF=/tmp/lmt/nX/conf` runs in the background.
   2. Start the sampler loop, which writes CSV to `/tmp/lmt/out/V$V.csv`.
   3. Start stress, then SIGSTOP and SIGCONT n2 at the given times.
   4. After stress ends, stop the sampler and run `nodetool -p 7199 drain` and `-p 7299 drain`.
   5. Run `kill $(cat /tmp/lmt/n*/pid)` and `rm -rf /tmp/lmt/n*/data`.
3. Repeat each V twice.
4. Report, per run, the peak of each metric over the stall window minus its median over t = 10–25 s (the unstalled baseline).

**B3f. Predictions (stated before running).**
- **Peak SmallMessagePendingBytes** during the stall is about 3 MiB (≤ 3145728 + one message) for all V, and `SmallMessageDroppedBytesDueToOverload` grows. The spread across V is under 5 %.
- **Positive control:** peak SmallMessagePendingBytes is about 32 MiB, an increase of roughly 29 MiB. Heap used rises correspondingly, by at least about 29 MB above the cap-3-MiB run.
- **Networking UsedSize peak-minus-baseline** differs across V by less than 0.5 MiB. Only about one frame per connection plus the 64 KiB watermark depends on LMT.
- **Direct `MemoryUsed`** across V: same as UsedSize, a difference of less than 1 MiB. It moves only in 1 MiB macro-chunk steps, if at all.
- **OverflowSize** is about 0 for all V.

**Amendment S4-A10 (stage-4 audit, 2026-10-22; factual correction from the source, bands unchanged).** The pool takes direct memory in **8 MiB** macro chunks, not 1 MiB: `MACRO_CHUNK_SIZE = 64 * NORMAL_CHUNK_SIZE` = 64 × 128 KiB (`BufferPool.java:385`; the comment on `:384` says 1 MiB). Direct `MemoryUsed` therefore moves in steps of 0 or ≥ 8 MiB from the pool, plus overflow and other direct users. The < 1 MiB band means that no step happened at any V.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Pending, UsedSize and direct peaks are flat across V within the stated bands, while the control moves pending by about 29 MiB | **Claim confirmed:** usage does not follow LMT, and the send-queue cap binds. |
| Peak pending or UsedSize grows monotonically with V by much more than 2·ΔLMT (more than about 1 MiB between 16384 and 131072) | **Claim refuted:** usage follows LMT. |
| Control pending does not rise above about 3 MiB, or pending never reaches about 3 MiB in the main runs | Cap not reached or workload too weak; **not confirmed**. Raise threads, or lengthen the stall. |
| n2 marked down during the stall (check `nodetool status` and `system.log` on n1) | The backlog was cut short; **not confirmed** for that run. Shorten the stall to 12 s. |
| Errors such as "Maximum payload size is 128KiB" in n1's `system.log` at V = 131072 | The frame ceiling was hit. Record it; this is not a memory effect. |

**Amendment S4-A9 (stage-4 audit, 2026-10-22; before any reading).** The table above had no row for direct memory in its Refuted row, for a band missed without a refutation, for usage above the send cap, or for a verdict on frame errors. It also did not define "peak". **The table below replaces it for the verdict.**

**Definitions:**
- **Stall window:** SIGSTOP to SIGCONT.
- **Pending peak:** the maximum `SmallMessagePendingBytes` sample in the stall window (absolute).
- **UsedSize and direct:** the maximum in the stall window minus the median over t = 10–25 s.
- **Per-V value:** the mean of that V's two runs.
- **One message:** 2 KiB is allowed for one message.

Rows are applied in order: run validity (C4, C5), then C2, then C3 and C6, then C7, then C1. The first row that holds is the verdict.

| Row | Observation | Meaning |
|---|---|---|
| C1 | All of the following hold: every main-run pending peak is in [0.9 × 3 MiB, 3 MiB + 2 KiB]; the per-V pending peaks span < 5 % of their mean; the per-V UsedSize values span < 0.5 MiB; the per-V direct values span < 1 MiB; each control run's pending peak is in [0.9 × 32 MiB, 32 MiB + 2 KiB] | **Confirmed:** usage does not follow LMT, and the send-queue cap binds |
| C2 | The per-V value of pending peak, UsedSize or direct increases with V (16384 < 65536 < 131072), and value(131072) − value(16384) > 1 MiB | **Refuted:** usage follows LMT |
| C3 | Some main-run pending peak < 0.9 × 3 MiB, or some control-run pending peak < 0.9 × 32 MiB | Cap not reached or workload too weak: **Not confirmed** |
| C4 | n2 is marked down during a run's stall (`is now DOWN` in n1's `system.log`) | That run does not count. Shorten the stall to 12 s and restart the tier; **Not confirmed** if it recurs |
| C5 | "Maximum payload size is 128KiB" or another frame error in n1's `system.log` | Recorded. That run does not count; a V with no counting run gives **Not confirmed** |
| C6 | Some main-run pending peak > 3 MiB + 2 KiB, or some control-run peak > 32 MiB + 2 KiB | The send-queue cap does not bind as B3b states, so the control premise fails: **Not confirmed** |
| C7 | A band of C1 is missed without C2's condition | Flatness not shown: **Not confirmed** |

**B3h. Controls.**
- The same stress profile, stall timing and fixed send-queue caps across V.
- The positive control changes only the send-queue caps.
- An unstalled baseline window in each run.
- Two repeats per value.
- Compression is off, so frame sizes are not altered.
- Hints are disabled, so there is no disk or heap churn from hint writing.
- Mutation size (about 1 KB) is far below every LMT tested, so routing to the large connection does not change between values.

**B4. Risks and cleanup.**
- **Locations:** all builds, data, commit logs and hints are under `/tmp/lmt` on local `/`. Expected use is under 5 GB (90 s of 1 KB writes, RF = 2). Nothing is written to `/proj`, and the shared clone is only read with `git clone`.
- **Cleanup after each run:**
  - `kill $(cat /tmp/lmt/n*/pid)`; if needed, `kill -CONT` first, because a SIGSTOPped JVM ignores SIGTERM until continued;
  - make sure the sampler loop and stress are gone;
  - `pgrep -f 'cassandra|CassandraDaemon|cassandra-stress'` must be empty;
  - `pgrep -f junit` must be empty after the unit tier.
- **Final:** `rm -rf /tmp/lmt` once the results are copied.
- **Amendment S4-A11 (stage-4 audit, 2026-10-22; execution detail).** The paths are those of S4-A1 and S4-A5 on `pc06`, not `/tmp/lmt`.
  - Leftover processes are checked with `ps -eo pid,args` for `java` processes whose working directory is `~/cassandra-otc` (not `pgrep -f` inside an ssh string).
  - Any SIGSTOPped node is sent SIGCONT before it is killed.
  - Node data is removed after the tier. The clone and logs stay.
- **Risks:**
  - V = 131072 may log frame errors and invalidate connections. This is expected (A3, step 6) and is not a failure of the run.
  - A JMX port clash on 7199/7299 with other users' processes: check `ss -ltn` first.

## C. Sources read

All paths below are in the source tree at `/proj/misconfiguration-PG0/git-repos/cassandra-src`.

- `src/java/org/apache/cassandra/net/OutboundConnection.java`
- `src/java/org/apache/cassandra/net/OutboundConnections.java`
- `src/java/org/apache/cassandra/net/OutboundConnectionSettings.java`
- `src/java/org/apache/cassandra/net/OutboundDebugCallbacks.java`
- `src/java/org/apache/cassandra/net/FrameEncoder.java`
- `src/java/org/apache/cassandra/net/FrameEncoderCrc.java`
- `src/java/org/apache/cassandra/net/FrameEncoderLZ4.java` (grep)
- `src/java/org/apache/cassandra/net/FrameEncoderUnprotected.java` (grep)
- `src/java/org/apache/cassandra/net/InboundMessageHandlers.java`
- `src/java/org/apache/cassandra/net/InboundMessageHandler.java` (grep)
- `src/java/org/apache/cassandra/net/Verb.java` (grep)
- `src/java/org/apache/cassandra/utils/memory/BufferPool.java`
- `src/java/org/apache/cassandra/utils/memory/BufferPools.java` (grep)
- `src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java`
- `src/java/org/apache/cassandra/metrics/InternodeOutboundMetrics.java`
- `src/java/org/apache/cassandra/locator/InetAddressAndPort.java` (grep)
- `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java`
- `src/java/org/apache/cassandra/config/Config.java` (grep)
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java`
- `conf/cassandra.yaml`
- `conf/cassandra-env.sh` (grep)
- `build.xml` (grep)
- `test/unit/org/apache/cassandra/net/ConnectionTest.java`
- `test/unit/org/apache/cassandra/net/OutboundConnectionsTest.java` (grep)
- `test/unit/org/apache/cassandra/net/proxy/InboundProxyHandler.java` (grep)
- `test/unit/org/apache/cassandra/net/ProxyHandlerConnectionsTest.java` (grep)
- `test/distributed/org/apache/cassandra/distributed/test/LargeMessageTest.java` (grep)
- `doc/modules/cassandra/pages/managing/operating/metrics.adoc` (grep)
- https://issues.apache.org/jira/browse/CASSANDRA-15066 (cited by reference)

## D. Stage-4 feedback

**2026-10-22, run 1 on `pc06` (stage-4 agent).** Results: [`results/OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous.md`](../../stage4-runtime-verification/results/OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous.md). Nothing committed.

- **Audit:** Ready after amendments.
  - S4-A1 to S4-A11 were made before any reading. They are dated next to the text they change (B2a, B2d, B2f, B2g, B3a, B3b, B3c, B3d, B3f, B3g, B4).
  - sha256 as filed `d33cf16717796b29514e1a5231c07e58d59a493396b49a28acafa982ec0d426f`; frozen after the audit `6b3a899e9628ea09f183789915bd073767d8cc00ce0da890dd29df7862a105a3`. Both tiers ran against the frozen version. No row or prediction was changed after a reading.
  - The two load-bearing fixes:
    - **S4-A6.** The send-side endpoint reserve key is inert on the production path; the receive-side key supplies it. That finding is confirmed by the closed acquire case. Without the fix, B3's plateaus would have been 5 / 48 MiB, not 3 / 32 MiB.
    - **S4-A7.** The stress client is whitelisted to n1. Otherwise the driver routes to the stopped n2.
- **Unit tier: Not confirmed. B2g row U9 (S4-A4), pool band missed. Effect: undetermined.**
  - The mechanism holds exactly. maxFrame = 16,224 / 64,896 / 130,806 B at V = 16384 / 65536 / 131072, the largest multiple of S that fits `roundUp(LMT+10,2048) − 10`, in every reading.
  - Queued bytes do not depend on V: the per-V pendingPeak medians are identical. The C positive control moved pendingPeak by 3.18 MB.
  - The in-JVM networking-pool peak rose with LMT: medians 106 / 262 / 459 KiB, a span of 344 KiB, against the frozen "< 300 KiB" band. That is about 3 frames of LMT for one link whose two ends share the pool, and every reading was < 0.5 MiB. Under the frozen table this is U9, not Confirmed.
  - Missed sub-predictions:
    - S4-A3's per-reading bound at V = 131072 (458,752 > 397,270 B);
    - S4-A3's expectation pendingPeak ≤ C in the first method of each JVM (its first connect had not yet failed, so the reserve was used).
- **Cluster tier: Confirmed. B3g row C1 (S4-A9). Effect: does not cap.**
  - Two repeats per value and per control.
  - The stalled link's pending peaked at 3,145,417 B at every V (span 0).
  - The networking pool's UsedSize peak − baseline spanned 5,152 B across V; direct `MemoryUsed` spanned 13,946.5 B; OverflowSize was 0.
  - The control (C 16, E 16, G 32 MiB) reached 33,553,595 B, and the live heap rose by +272.7 MB.
  - No conviction or frame error occurred during any stall.
  - Gap: 1 s samples of a pool shared with native transport cannot resolve a one-frame (16–128 KiB) effect. The tier shows "no effect > 0.5 MiB", which is what B3g asks.
- **Runbook defects:** one, harness only, found in a shakedown before the counted chain. The orderly stop of n2 logs "is now DOWN" on n1, so row C4 counts only DOWN lines inside the stall window.
- **For stage 3, left as recommendations:**
  - **R12.** The unit pendingPeak is read before any delivery runs, so it cannot depend on LMT by construction. A unit test of "queued usage is independent of LMT" would have to read pending while delivery runs.
  - **R13**, found from readings, so not applied. B1's pool clause ("< about one LMT per backlogged connection") and B2f's 300 KiB spread should count every frame of LMT that the pool holds at once for one link: the sending frame, frames in flight up to the 64 KiB watermark, the receiving side's frame stash, and Netty read buffers. In the unit tier that was about 3.5 frames at V = 131072. The claim's substance (LMT sizes frames, not the node's outbound memory) is supported by both tiers.
- **Overlap.**
  - The positive-control knob and the receive-key wiring come from `internode_application_send_queue_capacity-acquireCapacity-…--guided` (Confirmed).
  - The SIGSTOP pattern, `Jmx.java` and the daemon matcher come from `…-releaseCapacity-…--autonomous`.
  - The send-queue plateau C + endpoint reserve is observed again here (3 MiB − 311 B; 32 MiB − 837 B). It is not a new finding of this file.
