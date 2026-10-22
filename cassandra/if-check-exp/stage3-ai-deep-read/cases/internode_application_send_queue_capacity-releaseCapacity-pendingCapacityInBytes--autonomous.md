# internode_application_send_queue_capacity — verification solution  <!-- file: cases/internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/net/OutboundConnection.java:449` |
| Pinned source | `cassandra-5.0.9` (HEAD `b5f2a54`) |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code via Agent SDK (CLI version not exposed to the agent), 2026-10-21 |
| Estimate | `positive`. The per-link value bounds the bytes queued on one outbound link before shared reserve permits are needed. Once the reserves are also exhausted, further messages are dropped (`onOverloaded`), so a link's queued bytes never exceed `C + min(endpoint reserve, global reserve)`. The queued `Message` objects are heap-resident (plus off-heap frames in flight), so heap held by the backlog follows `C` additively. The limit counts serialized size, not heap size, so heap follows it by a roughly constant factor rather than byte for byte. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- Name: `internode_application_send_queue_capacity` (configuration entry; legacy name `internode_application_send_queue_capacity_in_bytes`, accepted via `@Replaces`).
- First declared: `src/java/org/apache/cassandra/config/Config.java:249-250`: `public DataStorageSpec.IntBytesBound internode_application_send_queue_capacity = new DataStorageSpec.IntBytesBound("4MiB");`
- Unit: bytes (yaml takes a data-storage string, min unit B; `cassandra.yaml:1385-1386`). It is an `int`, so the maximum is about 2 GiB.
- Default: hard-coded `4MiB` (Config.java:250), not derived from anything. In the shipped `conf/cassandra.yaml:1386` the key is commented out with the same value.
- Path to the check:
  `DatabaseDescriptor.getInternodeApplicationSendQueueCapacityInBytes()` (`DatabaseDescriptor.java:3025-3028`)
  → `OutboundConnectionSettings.applicationSendQueueCapacityInBytes()`, which falls back to it when the template field is null (`OutboundConnectionSettings.java:380-384`)
  → `withDefaults(MESSAGING)` resolves it into the template (`OutboundConnectionSettings.java:467-480`)
  → `OutboundConnection` constructor: `this.pendingCapacityInBytes = template.applicationSendQueueCapacityInBytes;` (`OutboundConnection.java:306-311`; field `OutboundConnection.java:118-119`, doc "the number of bytes we permit to queue to the network without acquiring any shared resource permits").
- Validation: `OutboundConnectionSettings.java:129` requires a value ≥ 1 KiB, checked when a connection's settings are built, not at startup.
- How to set it: `cassandra.yaml` only. There is no `-D` property and no JMX or nodetool setter: only getters exist (`DatabaseDescriptor.java:3025-3038`). The value is captured into a `final` field when each `OutboundConnection` is built (`OutboundConnections.java:80-88`, built lazily per peer). `OutboundConnection.java:1312` rejects a template change on reconnect. A change therefore needs a restart.
- Related sources that share the bound:
  - `internode_application_send_queue_reserve_endpoint_capacity`: default 128MiB, `Config.java:251-252`. One `Concurrent` limit is shared by the urgent, small and large links to one peer (`OutboundConnections.java:84-88`).
  - `internode_application_send_queue_reserve_global_capacity`: default 512MiB, `Config.java:253-254`. One node-wide `Concurrent` limit (`MessagingService.java:320-321`).
  - `internode_max_message_size`: defaults to `min(receive endpoint reserve, send endpoint reserve)`, and when set explicitly it must not exceed either reserve (`DatabaseDescriptor.java:974-997`).

**A2. What it caps.** It caps the per-link pending byte count, `pendingBytes(pendingCountAndBytes)`. That count packs the bytes of messages accepted for this link and not yet released, in the low 42 bits of `pendingCountAndBytes` (`OutboundConnection.java:120-123, 152-171`).
- Each message contributes `canonicalSize(message) = message.serializedSize(current_version)` (`OutboundConnection.java:1045-1048`), its on-wire size and not its heap size.
- A message stays in the count while it waits in `OutboundMessageQueue` (heap: the `Message` and its payload object graph). It also stays in while it is being serialized and flushed (an off-heap frame from the payload allocator), until the Netty flush future completes (`OutboundConnection.java:851-866`).
- The resource this governs is therefore mainly **heap**: queued `Message`/`Mutation` objects, and for mutations also the cached serialized `byte[]`, `Mutation.java:439-466`, prepared at `StorageProxy.java:1501`. A smaller **off-heap** share is the frames in flight.
- `pendingCapacityInBytes` is not a hard per-link cap. It is the part of the per-link queue that is "free". Bytes above it must be covered by permits from the shared endpoint and global reserves.

**A3. Mechanism.**
1. Enqueue (`OutboundConnection.java:325-358`):
   - A message larger than `internode_max_message_size` is rejected with `OversizedMessageException` (`:330-332`).
   - Otherwise `acquireCapacity(canonicalSize)` runs (`:335`).
   - On `INSUFFICIENT_ENDPOINT` it tries once to prune expired messages and retries (`:337-342`). Then, or directly on `INSUFFICIENT_GLOBAL`, `onOverloaded(message)` drops the message (`:343-345`, `:456-468`).
   - A dropped message is counted in `overloadedCount/Bytes` and logged ("overloaded; dropping …"). `RequestCallbacks.onOverloaded` removes and expires its callback (`RequestCallbacks.java:269-299`), so it is not retained.
2. Acquire (`OutboundConnection.java:385-440`), a CAS loop:
   - If the 22-bit pending count is saturated → `INSUFFICIENT_ENDPOINT` (`:391-395`).
   - **If `pendingBytes(next) <= pendingCapacityInBytes` → CAS and SUCCESS with no reserve (`:397-406`).** This is the primary use of the constraint.
   - If the link is reconnecting after a failure (`isFailingToConnect`) → `INSUFFICIENT_ENDPOINT` with no reserve allowed (`:408-413`; doc `architecture/messaging.adoc:283`). In this state the link is hard-capped at exactly `C`.
   - Otherwise the excess `requiredReserve = min(bytes, pendingBytes(next) - pendingCapacityInBytes)` (`:415`) is taken from `EndpointAndGlobal.tryAllocate` (global first, then endpoint; `ResourceLimits.java:263-273`). If that fails, the loop breaks with that outcome (`:416-427`).
   - Reserve claimed but unused after CAS races is returned (`:436-437`).
3. Release, the **target check** (`OutboundConnection.java:445-454`):
   - `prev = getAndAdd(-decrement)`. **`if (pendingBytes(prev) > pendingCapacityInBytes)` (`:449`)** releases `min(pendingBytes(prev) - pendingCapacityInBytes, bytes)` back to the endpoint and global reserves (`:451-452`).
   - It is the mirror of `:415`: it returns exactly the bytes that sat above `C`.
   - If `:449` released too little, the reserves would leak and the effective cap of every link to that peer (and node-wide) would shrink. If it released too much, the reserve counters would go below what is really in use (over-commit).
   - Callers:
     - delivery success, async flush completion: `:860-866`
     - sync completion: `:902-903`
     - large-message delivery: `:991`
     - expiry: `onExpired`, `:474-481`
     - serialization failure: `onFailedSerialize`, `:488-496`
     - discard on close: `onClosed`, `:503-508`
     - race with closing: `:354-357`
4. Resulting bound:
   - One link: `pendingBytes ≤ C + min(R_endpoint, R_global)`.
   - One peer (urgent, small and large links): `≤ 3·C + R_endpoint` (and ≤ `3·C + R_global`).
   - Node-wide: `≤ 3·N·C + R_global` for N peers. This matches `cassandra.yaml:1372-1383` and `messaging.adoc:86-99`.
5. Bypasses and overshoot:
   - The per-link `C` is **outside** the global reserve, so node-wide usage grows with peer count (3·N·C).
   - The accounting uses `serializedSize(current_version)` (`:1045-1048`), not the peer's version or the heap footprint. Delivery re-measures for the peer's version (`:789`).
   - Bytes already handed to the kernel socket buffer are released once the flush completes and are not counted.
   - A single message bigger than `C` is allowed if the reserve covers it (`requiredReserve` is capped at `bytes`).
   - The count saturates at 2^22−1 messages (`:152-156`), which is another cap.

**A4. Other consumers.** Other things use the same heap and off-heap memory outside this constraint:
- inbound/receive queues (`internode_application_receive_queue_*`, `InboundMessageHandlers`, `MessagingService.java:309-310`)
- the `RequestCallbacks` map, which for hinted writes retains the mutation until timeout
- hints buffers (off-heap)
- memtables (`memtable_heap_space`/`memtable_offheap_space`)
- the Netty/`BufferPool` networking chunk cache
- kernel socket send and receive buffers, which are outside the JVM
- the coordinator's local write path (the same `Mutation` instance is applied locally, `StorageProxy.java:1563-1567`)

**A5. Evidence beyond the source.**
- `doc/modules/cassandra/pages/architecture/messaging.adoc:72-108, 260-283` (in tree): per-link limit consumed in isolation, reserve semantics, "While failing to connect, no reserve queue limits are acquired."
- `conf/cassandra.yaml:1368-1391`.
- CASSANDRA-15066 (internode messaging rewrite that introduced these limits): https://issues.apache.org/jira/browse/CASSANDRA-15066
- Existing tests: `test/unit/org/apache/cassandra/net/ConnectionTest.java:354-424` (`testInsufficientSpace`: overload outcome with small `C` and reserves) and `:744-810` (`testAcquireReleaseOutbound`: asserts `max capacity = C + min(R_endpoint, R_global)` under contention).
- Git history is not available (shallow clone at `b5f2a54`).

## B. Verification solution

**B1. Claim under test.** For one outbound link, the bytes held in its send queue plateau at `internode_application_send_queue_capacity + min(endpoint reserve, global reserve)`, and messages beyond that are dropped as overloaded. The release-side check at `OutboundConnection.java:449` returns exactly the bytes above `C` to the reserves, with no leak. As a result, the heap held by an outbound backlog to an unreachable or non-reading peer rises with `C` (by a roughly constant heap/serialized ratio k ≥ 1) and stops rising once that plateau is reached. The claim is wrong if:
- the plateau does not move with `C`, or
- pending bytes or the backlog's heap exceed the bound by more than one message, or
- reserve usage stays > 0 after all pending bytes are released.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11.0.32.1, Ant 1.10.12.
- Clone the tag to local disk and build tests:
  ```
  mkdir -p /local/$USER/s3 && cd /local/$USER/s3   # any local (non-shared) dir on /, ≥ 10 GB free
  git clone --no-hardlinks /proj/misconfiguration-PG0/git-repos/cassandra-src c509 && cd c509 && git checkout -q cassandra-5.0.9
  ant build-test   # first run downloads deps into ~/.m2 and build/
  ```
- Test source: `c509/test/unit/org/apache/cassandra/net/SendQueueCapacityProbeTest.java`. It must be in package `org.apache.cassandra.net` to reach the package-private constructor `OutboundConnection(ConnectionType, OutboundConnectionSettings, EndpointAndGlobal)` and the `@VisibleForTesting` hooks `unsafeAcquireCapacity`, `unsafeReleaseCapacity`, `unsafeGetEndpointReserveLimits` (`OutboundConnection.java:1750-1778`) and `queue`.
- JVM: the `testsome` macro's defaults (`build.xml:1153`: `maxmemory=1024m`; CMS from `build.xml:233-240`; `-Dstorage-config=test/conf`). `System.gc()` is a full STW collection under CMS (no `ExplicitGCInvokesConcurrent`).

**B2b. Knobs.** The knob is set programmatically in the test with `OutboundConnectionSettings.withApplicationSendQueueCapacityInBytes(C)`, the same field the yaml value fills via `withDefaults`. The reserves are set with `withApplicationReserveSendQueueCapacityInBytes(R_e, new ResourceLimits.Concurrent(R_g))`.
- U1 (accounting): `C ∈ {65536, 1048576, 4194304}` (64 KiB, 1 MiB, 4 MiB = default), `R_e = 262144`, `R_g = 1048576`. These span 64× and include the default. `R_e < R_g`, so the endpoint reserve binds first.
- U2 (heap, connected peer that does not drain): `C ∈ {8 MiB, 32 MiB, 128 MiB}`, `R_e = R_g = 1 MiB`. They are large enough that the heap delta (≥ 9 MiB) is above GC-measurement noise, and small enough that 128 MiB × k fits in 1 GiB.
- U3 (failing-to-connect link): `C ∈ {8 MiB, 32 MiB}`, `R_e = R_g = 1 MiB`.

**B2c. Workload.**
- U1: acquire in fixed steps `S = 1000` bytes until the first failure, then release in steps of `S`. For `C=65536`: `(C+R_e)/S = 327.68` → 327 successes, pending 327000. For `C=1 MiB`: 1310 successes, pending 1310000. For `C=4 MiB`: 4456 successes, pending 4456000.
- U1-stress: 16 threads × 200 cycles. Each thread acquires random sizes `U[1, 4096]` until its first failure, recording what it got. Barrier, then each thread releases everything it holds. Total per cycle ≥ `C+R_e`, so the limit is hit in every cycle.
- U2: payload `byte[P]`, `P = 16384`, sent with verb `_TEST_1` and a custom serializer (4-byte length + bytes). The on-wire size is `s = message.serializedSize(current_version)`, about 16.4 KiB; it is logged. Enqueue `M = 2·(C+1 MiB)/P + 100` messages while the test holds the queue lock, so delivery cannot drain. For `C=128 MiB`, M ≈ 16612, of which about 8253 are accepted and the rest dropped as overloaded.
> **Amendment 2026-10-21 (stage-4 run 1, runbook defect 2; B2f/B2g unchanged; the unit tier restarted):** U2's blocking method is changed. Holding the queue lock in the test thread does block delivery, but `EventLoopDelivery.doRun` (`OutboundConnection.java:777-780`) registers a `this::execute` callback on every failed `lockOrCallback`, and while the test held the lock (about 2 s with the GC sleeps) the event loop registered 8.7–9.9 million `OutboundMessageQueue$Locked` nodes and their lambdas (≈ 350–400 MB; class histograms of the test JVM), so `heapDelta` measured the method, not the queue. Delivery is now blocked by **parking the link's event-loop thread** (a task that waits on a latch, submitted to the connection's `eventLoop` before the bulk enqueue and released after the reading); B2h's "retained heap comes only from the queue" holds again. Everything else in U2 (C, M, P, the readings, B2f, B2g) is unchanged. A class histogram of the test JVM is now also written at each U2/U3 heap reading (`-Dstage4.histo`).
- U3: same messages, but no inbound listener is open, so connection attempts are refused and the link enters `isFailingToConnect`. Enqueue `M = 2·C/P + 100`.
> **Amendment 2026-10-21 (stage-4 audit, A3, before any harness or reading):** U3's peer is a free loopback port that nothing listens on (taken from `new ServerSocket(0)` and closed), not the broadcast address that U2 opens and closes. Before the bulk enqueue the test checks `connectionAttempts() ≥ 2`: `isFailingToConnect` is set only once a retry has been scheduled after a failed attempt (`OutboundConnection.java:277`, `:1104`); if the check fails, U3 is invalid, not a reading.
- All bulk messages are built with `Message.builder(Verb._TEST_1, payload).withExpiresAt(nanoTime() + MINUTES.toNanos(10)).build()`. They must not expire during the test (`_TEST_1` otherwise uses `writeTimeout`, `Verb.java:214`).

**B2d. Observables and instruments.**
- `o.pendingBytes()` and `o.pendingCount()`: the check's own operand.
- `o.unsafeGetEndpointReserveLimits().using()`: endpoint reserve in use.
- `g.using()`: global reserve, the `Concurrent` object the test passed in.
- `o.overloadedCount()` and `o.overloadedBytes()`.
- Heap: `ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed()` after `System.gc()` three times with 200 ms sleeps (`usedAfterGc()`).
- All values are logged as one line per step: `PROBE <phase> C=… pending=… count=… endpointUsing=… globalUsing=… overloaded=… heapDelta=…`.
- Cannot observe directly: the exact heap per message (only the aggregate delta), and the off-heap frames in flight (none here, because delivery is blocked).

**B2e. Procedure.**
1. Create `SendQueueCapacityProbeTest.java` in the local clone. Skeleton (setup copied from `ConnectionTest.java:93-103, 230-253`):
   ```java
   package org.apache.cassandra.net;
   // imports: java.lang.management.*, java.util.*, java.util.concurrent.*, org.junit.*, org.apache.cassandra.config.DatabaseDescriptor,
   // org.apache.cassandra.db.commitlog.CommitLog, org.apache.cassandra.io.IVersionedSerializer, org.apache.cassandra.io.util.*,
   // org.apache.cassandra.locator.InetAddressAndPort, org.apache.cassandra.utils.FBUtilities;
   // static: Clock.Global.nanoTime, TimeUnit.*, MessagingService.current_version
   public class SendQueueCapacityProbeTest {
     static final SocketFactory factory = new SocketFactory();
     @BeforeClass public static void up() { DatabaseDescriptor.daemonInitialization(); CommitLog.instance.start(); }
     @AfterClass public static void down() throws Exception { factory.shutdownNow(); }

     static OutboundConnection newOut(InetAddressAndPort to, int C, int Re, ResourceLimits.Concurrent g) {
       OutboundConnectionSettings t = new OutboundConnectionSettings(to)
           .withApplicationSendQueueCapacityInBytes(C)
           .withApplicationReserveSendQueueCapacityInBytes(Re, g)
           .withSocketFactory(factory).withDefaults(ConnectionCategory.MESSAGING);
       return new OutboundConnection(ConnectionType.SMALL_MESSAGES, t,
           new ResourceLimits.EndpointAndGlobal(new ResourceLimits.Concurrent(Re), g));
     }
     static long usedAfterGc() throws InterruptedException {
       for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(200); }
       return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
     }
     static final IVersionedSerializer<byte[]> BYTES = new IVersionedSerializer<byte[]>() {
       public void serialize(byte[] b, DataOutputPlus out, int v) throws java.io.IOException { out.writeInt(b.length); out.write(b); }
       public byte[] deserialize(DataInputPlus in, int v) throws java.io.IOException { byte[] b = new byte[in.readInt()]; in.readFully(b); return b; }
       public long serializedSize(byte[] b, int v) { return 4 + b.length; } };
     // @Before: Verb._TEST_1.unsafeSetSerializer(() -> BYTES); Verb._TEST_1.unsafeSetHandler(() -> m -> {});
     // @After: restore the previous suppliers returned by those calls.

     @Test public void u1Accounting() { /* per C: loop unsafeAcquireCapacity(1000) until false; log;
        then n times unsafeReleaseCapacity(1000), after each: assert endpointUsing == max(0, pending - C) && globalUsing == endpointUsing;
        finally assert pending==0, endpointUsing==0, globalUsing==0. Then U1-stress (16 threads x 200 cycles,
        CyclicBarrier between acquire and release phases; at the barrier log/assert pending <= C+Re and
        endpointUsing == max(0, pending - C); after release assert all three == 0). o.close(false). */ }

     @Test public void u2HeapConnected() throws Throwable { /* per C: ep = FBUtilities.getBroadcastAddressAndPort();
        InboundSockets in = new InboundSockets(Collections.singletonList(new InboundConnectionSettings().withBindAddress(ep).withSocketFactory(factory)));
        in.open().sync(); o = newOut(ep, C, 1<<20, g = new Concurrent(1<<20));
        o.enqueue(Message.out(Verb._TEST_1, new byte[16])); wait ≤10 s until o.isConnected() && o.pendingCount()==0;
        long before = usedAfterGc();
        loop { try (OutboundMessageQueue.WithLock l = o.queue.lockOrCallback(nanoTime(), null)) { if (l == null) continue;
                 for (i < M) o.enqueue(builder(... new byte[P]) ...);   // do NOT keep references to the messages
                 long after = usedAfterGc(); log PROBE U2 C pending count endpointUsing globalUsing overloadedCount (after-before); break; } }
        o.close(false).get(30, SECONDS); log PROBE U2-closed pending endpointUsing globalUsing; in.close().get(30, SECONDS); */ }

     @Test public void u3FailingToConnect() throws Throwable { /* per C: no inbound opened; o = newOut(ep, C, 1<<20, g);
        o.enqueue(one 16-byte message); sleep 3 s (connection refused -> retry scheduled -> isFailingToConnect);
        before = usedAfterGc(); enqueue M messages (no lock needed); after = usedAfterGc(); log; o.close(false).get(30, SECONDS); log. */ }
   }
   ```
   `MessagingService.instance()` is initialised implicitly by `withDefaults` (callbacks, versions), as in `ConnectionTest`.
2. Run the baseline: `ant testsome -Dtest.name=org.apache.cassandra.net.ConnectionTest -Dtest.methods=testAcquireReleaseOutbound,testInsufficientSpace`. Both must pass.
3. Run the probe: `ant testsome -Dtest.name=org.apache.cassandra.net.SendQueueCapacityProbeTest`. Collect `grep PROBE build/test/output/TEST-org.apache.cassandra.net.SendQueueCapacityProbeTest.*` (or `build/test/logs/`).
4. Repeat step 3 three times to check heap-delta stability.

**B2f. Predictions.**
- U1:
  - Successes `n = floor((C+R_e)/1000)`: 327, 1310, 4456 for C = 64 KiB, 1 MiB, 4 MiB.
  - Pending at the first failure: `n·1000` (327000, 1310000, 4456000).
  - `endpointUsing = n·1000 − C`: 261464, 261424, 261696.
  - `globalUsing = endpointUsing`.
  - During release: `endpointUsing == max(0, pending − C)` after every step. It reaches 0 exactly when pending first drops to ≤ C, and stays 0 while pending falls from about C to 0. Final pending, endpoint and global values are all 0.
- U1-stress: every barrier shows `pending ≤ C + R_e` and `endpointUsing == max(0, pending − C)`. After each cycle all three counters are 0. The number of bytes acquired per cycle does not drift downward across 200 cycles (no leak).
> **Amendment 2026-10-21 (stage-4 audit, A1, before any reading):** "does not drift downward" is made exact: a thread stops only when `tryAllocate` fails, i.e. when `pending + b − C > R_e` with `b ≤ 4096`, and pending only grows during the acquire phase, so **every cycle's total is in `[C + R_e − 4095, C + R_e]`**, checked at every cycle of every C (16 threads × 200 cycles at each of the three U1 values). A total below that band in any cycle is the leak row of B2g; the global reserve equals the endpoint reserve at every barrier (`R_g > R_e`, so `INSUFFICIENT_GLOBAL` cannot occur).
- U2:
  - `pending ∈ (C + 1 MiB − s, C + 1 MiB]`.
  - `endpointUsing = globalUsing = pending − C`, about 1 MiB.
  - `overloadedCount = M − accepted`, where `accepted = pendingCount − 0`.
  - `heapDelta / pending` between 1.0 and 1.15 for all three C (a `byte[16384]` plus `Message`/header objects of about 100–300 B each).
  - So `heapDelta` is about 9.2, 33.2 and 129.2 MiB (± 5 %).
  - After close: pending, endpoint and global are all 0.
- U3:
  - `pending ∈ (C − s, C]`, `endpointUsing = globalUsing = 0`.
  - `heapDelta ≈ C × (1.0–1.15)`, and `overloadedCount ≈ M − C/s`.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| U1/U2 pending plateaus at C+R (±1 message) and moves with C. U3 plateaus at C with zero reserve. Invariant holds and all counters return to 0 | Claim confirmed at the mechanism level |
| `endpointUsing` > 0 after all pending released, or acquired bytes per cycle shrink over U1-stress cycles | `:449` under-releases (leak). Claim wrong for the release path |
| `endpointUsing` < `pending − C` at any quiescent point, or a counter goes negative | `:449` over-releases (over-commit). Claim wrong |
| pending > C + R + s | Acquire-side bound bypassed. Claim wrong |
| Pending plateau independent of C | The constraint does not govern the queue. Claim wrong |
| `heapDelta` does not scale with C (ratio across C outside 0.8–1.25× of `pending` scaling) | Heap is not governed by the counted bytes (for example the payload is retained elsewhere). Heap part of the claim wrong |
| `overloadedCount == 0` | Limit never reached. Run not confirming; increase M |
| U1 passes unchanged with mutant M1 or M2 (A2 below) | The instrument cannot see `:449`. Not confirmed (the unit verdict cannot rest on it) |

> **Amendment 2026-10-21 (stage-4 audit, A2, before any harness or reading):** a sensitivity control is added, because nothing in B2h shows that U1's invariant would fail if `:449`–`:452` were wrong. In a separate clone at the same tag, U1 (accounting and stress) is run twice against mutated source: **M1** releases `bytes` instead of `excess` at `:451-452`; **M2** removes the guard (`if (pendingBytes(prev) > pendingCapacityInBytes)` → `if (true)`, so a release at or below C hands back `min(prev − C, bytes) ≤ 0`). Each mutant must produce at least one U1 mismatch or an exception; the row above is the outcome if one does not. The mutants run only U1; U2/U3 and the cluster tier use the unmodified build.

**B2h. Controls.**
- Existing `ConnectionTest#testAcquireReleaseOutbound` passing confirms the harness and the build.
- U2 includes a `before` heap reading. A no-enqueue run of the same method (M=0) should give a `heapDelta` of about 0 (±2 MiB), which bounds GC noise.
- The messages are not referenced from the test, so retained heap comes only from the queue.
- U3 (no reserve) against U2 (reserve) isolates `C` from the reserve contribution.
- The post-close counters exercise `:449` via `onClosed`.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux host with two nodes on loopback: A = 127.0.0.1, B = 127.0.0.2. Two physical nodes also work, with the IPs replaced.
- Build in the local clone: `ant jar stress-build` (gives `bin/cassandra`, `tools/bin/cassandra-stress`, `bin/nodetool`).
- Make two config copies `confA` and `confB` from `conf/`.
- Data, commitlog, hints, saved caches and logs go under `/local/$USER/s3/nodeA|nodeB` on local disk. Set `CASSANDRA_LOG_DIR` per node.
- Both nodes:
  ```yaml
  cluster_name: s3probe
  num_tokens: 16
  seed_provider: [{class_name: org.apache.cassandra.locator.SimpleSeedProvider, parameters: [{seeds: "127.0.0.1:7000"}]}]
  listen_address: 127.0.0.X        # X=1 for A, 2 for B
  rpc_address: 127.0.0.X
  data_file_directories: [/local/$USER/s3/nodeX/data]
  commitlog_directory: /local/$USER/s3/nodeX/commitlog
  hints_directory: /local/$USER/s3/nodeX/hints
  saved_caches_directory: /local/$USER/s3/nodeX/saved_caches
  hinted_handoff_enabled: false        # no hints buffers, and write callbacks do not retain mutations (StorageProxy.java:2442-2446)
  write_request_timeout: 60000ms       # queued mutations do not expire during the window
  phi_convict_threshold: 16            # B convicted ≈ 16/0.434 ≈ 37 s after its last heartbeat (FailureDetector.java:99,360)
  internode_tcp_user_timeout: 0ms      # no kernel-level drop of the stalled connection (cassandra.yaml:1357-1363)
  memtable_allocation_type: offheap_objects
  memtable_heap_space: 64MiB           # bounds the memtable's heap share (A4 confounder)
  memtable_offheap_space: 512MiB
  ```
> **Amendment 2026-10-21 (stage-4 audit, A4, before any harness or reading):** both nodes also set **`native_transport_timeout: 60000ms`**. The coordinator stamps a `MUTATION_REQ`'s expiry with the nearer of the verb deadline and the client deadline (`Dispatcher.java:238-244`, default 12 s; the same defect was found in the receive-side twin's run, its results §3 row 1). Without it, messages queued to B expire after 12 s and `onExpired` releases capacity during the plateau window, which B3h's "expiry does not mimic a cap" excludes.
- Node A only, the knobs under test:
  ```yaml
  internode_application_send_queue_capacity: <C>
  internode_application_send_queue_reserve_endpoint_capacity: 1MiB
  internode_application_send_queue_reserve_global_capacity: 1MiB
  internode_max_message_size: 1MiB     # must be ≤ both reserves (DatabaseDescriptor.java:984-988)
  ```
> **Amendment 2026-10-21 (stage-4 audit, A5, before any harness or reading; from the closed acquire-side case, not from a reading of this file):** `internode_application_send_queue_reserve_endpoint_capacity` is **inert** in 5.0.9: the per-peer reserve an `OutboundConnections` builds is read from `internode_application_receive_queue_reserve_endpoint_capacity` (default 128 MiB; measured in `results/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided.md`, units U10/U11 and arms c1/c2). The key is still set as written (it is also checked against `internode_max_message_size`, `DatabaseDescriptor.java:984-988`). On A the effective reserves are therefore endpoint 128 MiB and global 1 MiB, so `min(R_e, R_g)` = 1 MiB and every B3f number stands; the first refusal is `INSUFFICIENT_GLOBAL`. In the positive control the global key (128 MiB) is what moves the plateau; the effective endpoint reserve is 128 MiB from the receive key's default, so the predicted 132 MiB stands.
- JVM: in `confA/jvm-server.options`/`cassandra-env.sh`, `MAX_HEAP_SIZE=4G`, `HEAP_NEWSIZE=800M` for both nodes. Keep the default G1 settings from `jvm11-server.options`.
- JMX: `JMX_PORT=7199` for A and `7299` for B (edit `cassandra-env.sh:235` in each conf copy), local JMX only.

**B3b. Knobs.**
- `internode_application_send_queue_capacity` on A ∈ {`4MiB` (default), `64MiB`, `256MiB`}. These span 64× and the largest still fits 4 GiB of heap at k ≤ 4. Set it in `confA/cassandra.yaml` and restart both nodes (wipe data) between values.
- Reserves are fixed at 1 MiB so that `C` dominates the plateau.
- Positive-control knob (C fixed at 4 MiB): `internode_application_send_queue_reserve_endpoint_capacity` and `_global_capacity` = `128MiB` (with `internode_max_message_size: 1MiB`). This is a documented cap of the same queue, so the plateau should move by +127 MiB.

**B3c. Workload.**
- `cassandra-stress` writes through A only, at RF=2 and CL=ONE. A stores each write locally and sends a ~1 KiB `MUTATION_REQ` to B on the **small** link (size < 64 KiB, `CassandraRelevantProperties.java:388`, `OutboundConnections.java:72-73`):
  ```
  tools/bin/cassandra-stress write duration=90s cl=ONE no-warmup \
    -schema "replication(strategy=SimpleStrategy,factor=2)" \
    -col "n=FIXED(1)" "size=FIXED(1000)" \
    -rate threads=64 fixed=30000/s -node whitelist 127.0.0.1 -port native=9042 -log interval=1
  ```
- Rate: 30000 × ~1.1 KB ≈ 33 MB/s toward B.
- Once B is stopped (`kill -STOP`), the socket buffers (a few MB) fill within 1 s. After that the link's pending bytes grow at about 33 MB/s.
- Time to plateau: C+1MiB = 5 MiB takes < 1 s; 65 MiB takes ~2 s; 257 MiB takes ~8 s. All of these are well inside the ~37 s before B is convicted. After conviction A interrupts the connection (`StorageService.java:3884-3890`) and stops sending writes to B (`StorageProxy.java:1507`).
- Each run: 20 s with B running (warm-up, connections established), then SIGSTOP B for 30 s, then SIGCONT.

**B3d. Observables and instruments.**
- On A, sampled every 1 s with a timestamp, with the JMX bean scope `127.0.0.2_7000` (`InetAddressAndPort.java:127-130`):
  - `org.apache.cassandra.metrics:type=Connection,scope=127.0.0.2_7000,name=SmallMessagePendingBytes`
  - `…name=SmallMessagePendingTasks`
  - `…name=SmallMessageDroppedBytesDueToOverload`
  - `…name=SmallMessageDroppedTasksDueToOverload`
  - Also the Urgent* and Large* equivalents, which should be small.
- Read with `bin/nodetool -p 7199 sjk mx -mg -b '<bean>' -f Value`. List names first with `bin/nodetool -p 7199 sjk mxdump -q 'org.apache.cassandra.metrics:type=Connection,*'`.
- Heap on A at the plateau (pause + 12 s):
  - `jcmd <pidA> GC.class_histogram > histo_C.txt`. This forces a full GC. Record the instance counts and bytes of `org.apache.cassandra.net.Message`, `org.apache.cassandra.db.Mutation`, `org.apache.cassandra.db.Mutation$CachedSerialization` and the total.
  - `jcmd <pidA> GC.heap_info` immediately after.
- Log line: `grep "overloaded; dropping" logs/system.log` (NoSpamLogger, every 30 s).
- Cannot observe directly: per-link heap (only the whole-JVM heap and class counts), and bytes sitting in kernel socket buffers (outside the JVM and not counted).
> **Amendment 2026-10-21 (stage-4 audit, A6, before any harness or reading):** the sampler is a persistent JMX client (harness `Jmx.java poll`, one connection, every 1 s) reading the same beans plus `java.lang:type=Memory HeapMemoryUsage`; `nodetool sjk mx` starts a JVM per attribute (about 1 s each), so it cannot read eight attributes per second. Added observable: `system_views.internode_outbound` on A every 1 s (`pending_bytes`, `using_reserve_bytes`, `overload_count`, `expired_count`), read with the in-tree Python driver. `using_reserve_bytes` is the reserve the link holds, the only cluster-tier view of the release at `:449` (B1's third falsifier).

> **Amendment 2026-10-21 (stage-4 audit, A7, before any harness or reading):** heap noise rule. Every lifetime also takes a class histogram at t = 18 s (B running, before the SIGSTOP); the negative control takes t = 18 s and t = 32 s. **Noise N = the range of the t = 18 s histogram totals over all lifetimes.** ΔH(C) = total(pause + 12 s) − negative control total(t = 32 s), as B3f says; **k = ΔH / `SmallMessagePendingBytes` at the histogram's sample** (the bytes actually queued when the heap was read). The heap clause of B3f/B3g is judged only on runs 1–3 whose ΔH > 3N; if fewer than two clear it, the heap clause is *not adjudicable* (row added to B3g). The `Mutation` instance count against `SmallMessagePendingTasks` is read in every run regardless.

**B3e. Procedure.**
For each value of C, plus the positive control and the negative control:
1. `rm -rf /local/$USER/s3/nodeA /local/$USER/s3/nodeB`; recreate the directories. Run `df -h /` and check ≥ 10 GB free.
2. Start the nodes:
   ```
   CASSANDRA_CONF=$PWD/confA CASSANDRA_LOG_DIR=/local/$USER/s3/nodeA/logs bin/cassandra -p /local/$USER/s3/A.pid
   ```
   Wait for `nodetool -p 7199 status` to show A UN, then start B the same way with `confB` and `B.pid`. Wait until both show UN.
3. Start the sampler: a bash loop of `sjk mx` reads, appending `epoch,metric,value` to `samples_C.csv` every 1 s.
4. Start `cassandra-stress` (B3c) in the background. At t=20 s run `kill -STOP $(cat /local/$USER/s3/B.pid)`.
5. At pause+12 s: `jcmd $(cat .../A.pid) GC.class_histogram > histo_C.txt; jcmd … GC.heap_info >> histo_C.txt`.
6. At pause+30 s: `kill -CONT` B. Let the stress run finish. Stop the sampler.
7. `nodetool -p 7199 stopdaemon` and `-p 7299 stopdaemon`; `kill` any leftover PIDs from the pid files. `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` must return nothing.
8. Negative control: same C=64MiB run without step 4's SIGSTOP. Take the histogram at the same wall time (t=32 s).
9. Positive control: C=4MiB with both reserves at 128 MiB.

**B3f. Predictions.**
- Plateau of `SmallMessagePendingBytes` (median over pause+5 s … pause+25 s):

  | Run | C | Reserves | Predicted plateau | Overload drops |
  |---|---|---|---|---|
  | 1 | 4 MiB | 1 MiB | 5 MiB − ≤1 msg (≈ 5.24 MB) | grow ~30 k/s once plateaued |
  | 2 | 64 MiB | 1 MiB | 65 MiB (≈ 68.2 MB) | grow after ~2 s |
  | 3 | 256 MiB | 1 MiB | 257 MiB (≈ 269.5 MB) | grow after ~8 s |
  | Positive control | 4 MiB | 128 MiB | 132 MiB (≈ 138.4 MB) | grow after ~4 s |
  | Negative control | 64 MiB | 1 MiB, B running | < 1 MiB throughout | 0 |
- `SmallMessagePendingBytes / SmallMessagePendingTasks` gives a constant per-message size `s` of about 1.05–1.2 KB. `PendingTasks` plateaus at about plateau/s.
- Heap after full GC, as excess over the negative control at the same time point: `ΔH(C) = k · plateau(C)` with a single k ∈ [1.5, 4], equal across runs 1–3 within ±25 %. k > 1 because each queued `Mutation` holds its object graph plus a cached serialized `byte[]` of about s. So ΔH ≈ 8–20 MiB (run 1), 100–260 MiB (run 2), 390–1030 MiB (run 3).
- `Mutation` instance count in the histogram is ≈ `PendingTasks` (± a few thousand in flight). In the negative control it is ≪ that.
- The plateau stays flat while stress continues: pending does not track elapsed time once reached.
- After SIGCONT (or after conviction), pending drops to about 0.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Plateau ≈ C + 1 MiB for each C, overload drops rising after it, ΔH ∝ plateau with stable k | Claim confirmed: `C` governs the node's outbound backlog heap |
| Plateau rises without bound (tracks elapsed time × rate) for any C | The cap does not bind. Claim wrong |
| Plateau ≈ constant across C (for example always ≈ 5 MiB) | `C` not applied (for example config not read, or the link is in failing-to-connect so only C counts…). Check the log; if it is genuinely flat, the claim is wrong |
| Plateau scales with C but ΔH does not (k varies > 2× across C) | The counted bytes do not govern heap. Heap part of the claim wrong |
| Positive control plateau ≈ 132 MiB while run 1 ≈ 5 MiB | Workload and instrument can move usage where a known cap binds. Validates the runs |
| Positive control does not move, or pending never exceeds ~0 with B stopped | Backlog not created (for example B convicted early, writes not routed to B). Not confirming; fix the setup |
| B convicted before the plateau (log `is now DOWN` within the window) | Run invalid; raise the rate or lower C |
| `using_reserve_bytes` on A stays > 0 once pending has returned to ≈ 0 after SIGCONT, or a reserve goes negative (`UnrecoverableIllegalStateException`) | `:449` under- or over-releases on the node. Claim wrong for the release path (added by A8) |
| ΔH ≤ 3N for at least two of runs 1–3 (A7) | Heap clause not adjudicable: heap part Not confirmed; the accounting rows above still decide (added by A8) |
| `SmallMessageDroppedTasksDueToTimeout` > 0 before pause + 25 s | Expiry, not the cap, shaped the backlog. That value's run invalid (added by A8) |

> **Amendment 2026-10-21 (stage-4 audit, A8, before any harness or reading):** the three rows above are added so that every plausible outcome has a row (README group B): the release-side leak at the cluster tier, the heap clause below noise, and expiry inside the window.

**B3h. Controls.**
- The negative control (B running) separates the queue's heap from memtable/stress heap growth at the same time and rate.
- The positive control (reserve 128 MiB) shows the plateau is a configured cap.
- The fixed client rate (`fixed=30000/s`) makes the workload identical across runs.
- Hints are disabled, so callbacks and hint buffers do not retain the dropped mutations.
- `write_request_timeout` is 60 s, so expiry does not mimic a cap.
- Check that the Urgent/Large pending bytes stay < 1 MiB, so only the small link is involved.
- Check A's log for `is now DOWN` timing against the plateau window.

**B4. Risks and cleanup.**
- Unit tier: builds only in the local clone. Uses localhost port 7012 (test conf storage port) for U2; nothing persistent. `ant` writes to `c509/build` (~2 GB) and `~/.m2`.
- Cluster tier: about 3 GB of data per run on local `/` (90 s × 33 MB/s, written on A and on B after resume). Wipe it between runs. Never place data, commitlog or hints on `/proj`.
- Leftover processes: always `kill -CONT` B before stopping (a stopped JVM ignores `stopdaemon`). Then `stopdaemon` both nodes, kill the pid-file PIDs, and check `pgrep -f CassandraDaemon`, `pgrep -f cassandra-stress` and `pgrep -f sampler` are empty.
- Free ports 7000/9042/7199/7299 on 127.0.0.1-2 before starting (`ss -ltnp`).
- At the end: `rm -rf /local/$USER/s3`.

> **Amendment 2026-10-21 (stage-4 audit, A9, before any harness or reading; execution detail):** on `pc13` there is no `/local`; node data, commit logs, hints and caches go on a tmpfs `~/stage4-sq2/nodes` (40 GiB, RAM, local, never `/proj`), wiped per lifetime and unmounted at the end; logs under `~/stage4-sq2/{A,B}/logs`. A process is matched by `java` + the clone path (`~/cassandra-sq2`), never by `pgrep -f CassandraDaemon` (a shared host's shells match it). The shell that starts a node runs `ulimit -n 100000` (peer default 1024).

## C. Sources read

- `src/java/org/apache/cassandra/net/OutboundConnection.java` (lines 60-171, 300-520, 700-910, 980-995, 1040-1060, 1300-1315, 1550, 1630-1778)
- `src/java/org/apache/cassandra/net/OutboundConnectionSettings.java` (83-142, 223-260, 310-400, 467-480)
- `src/java/org/apache/cassandra/net/OutboundConnections.java` (60-110)
- `src/java/org/apache/cassandra/net/ResourceLimits.java` (237-290, grep)
- `src/java/org/apache/cassandra/net/MessagingService.java` (300-330)
- `src/java/org/apache/cassandra/net/RequestCallbacks.java` (110-160, 265-300)
- `src/java/org/apache/cassandra/net/Verb.java` (214, 345-358)
- `src/java/org/apache/cassandra/metrics/InternodeOutboundMetrics.java` (33-150)
- `src/java/org/apache/cassandra/locator/InetAddressAndPort.java` (118-130)
- `src/java/org/apache/cassandra/config/Config.java` (249-261)
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (554-556, 970-997, 2391-2396, 3020-3053)
- `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java` (388)
- `src/java/org/apache/cassandra/service/StorageProxy.java` (796-811, 1475-1580, 2423-2452)
- `src/java/org/apache/cassandra/service/StorageService.java` (3884-3896)
- `src/java/org/apache/cassandra/gms/FailureDetector.java` (99, 229-233, 360-372, 541-544)
- `src/java/org/apache/cassandra/db/Mutation.java` (78-81, 423-466)
- `test/unit/org/apache/cassandra/net/ConnectionTest.java` (60-264, 354-424, 550-620, 744-860)
- `conf/cassandra.yaml` (68, 825, 1330, 1340-1391, 1471)
- `conf/cassandra-env.sh` (235)
- `build.xml` (targets list, 225-240, 508-512, 1120-1182, 1382-1390)
- `doc/modules/cassandra/pages/architecture/messaging.adoc` (72-108, 260-283, 348)
- `CHANGES.txt` (grep for CASSANDRA-15066)
- https://issues.apache.org/jira/browse/CASSANDRA-15066 (cited from the in-tree doc; not fetched)

## D. Stage-4 feedback

**2026-10-21. Stage 4, run 1 on `pc13`, closed.** Results: [`../../stage4-runtime-verification/results/internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous.md`](../../stage4-runtime-verification/results/internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous.md); harness in `stage4-runtime-verification/harness/<stem>/`. Nothing committed.

- **Audit (step 0): Ready after amendments.** A1–A9 are dated next to the text they change (B2c, B2f, B2g, B3a, B3d, B3g, B4); no B1 claim was changed. sha256 as filed `49e904a2…`, after the audit `658ca786…`, after defect 2 `b48dd16e…` (the version run).
- **Unit (B2): Confirmed, B2g row 1. Effect: caps.**
  - U1 is exact at C = 64 KiB / 1 MiB / 4 MiB: 327 / 1310 / 4456 successes; reserve 261,464 / 261,424 / 261,696.
  - `reserve == max(0, pending − C) == global` holds after every release step.
  - In 1,800 U1-stress cycles there are 0 barrier violations and every cycle ends at (0, 0, 0).
  - U2 sits at C + 1 MiB − < 1 message, with endpoint = pending − C and heap/pending 0.995–1.008 at 8 / 32 / 128 MiB.
  - U3 holds at C with no reserve.
  - Everything is 0 after `close(false)`.
  - Mutant M1 (`:452` releases `bytes`) fails with `UnrecoverableIllegalStateException (using=-536)`; mutant M2 (guard removed) fails with an `AssertionError`.
- **Cluster (B3): B3g row 4 by its trigger — partial, refines the claim. Effect: caps.**
  - Plateaus are 5,242,328 / 68,156,648 / 269,483,536 B at C = 4 / 64 / 256 MiB and 138,411,504 B in the positive control: C + reserve minus 496–792 B (s = 1,064 B).
  - The link's `using_reserve_bytes` equals pending − C to the byte at every plateau sample, and is 0 after SIGCONT and in the final read: the release at `:449` on a real node.
  - Overload drops start at the plateau. There was no expiry and no conviction, and the negative control stays below 51 KB.
  - **The heap clause as worded (ΔH = k·plateau, one k ± 25 %) is refuted:** k = 11.6 / 3.9 / 3.4.
  - **Heap does follow C, linearly:** 3.265 and 3.276 heap bytes per counted byte over the two segments, plus a C-independent ≈ 42 MiB. The positive control lies on the same line (−1.8 %).
  - The constant term matches the 7.2–8.7 k live `Mutation`s beyond `PendingTasks` at every C. These are inferred to be mutations already flushed into the socket and unanswered: the write handler keeps `mutation.hintOnFailure()`, which is the `Mutation` itself (`Mutation.java:158`, `AbstractWriteResponseHandler.java:81`), until a response or the timeout.
- **Runbook defects:**
  1. A2's mutant M1 was not recompiled (Ant's 1 s mtime granularity). Harness fix; unit tier restarted.
  2. U2's blocking by holding the queue lock made `EventLoopDelivery.doRun` (`:777-780`) register about 9 M `Locked` callbacks (≈ 0.4 GB), so heapDelta measured the method. Dated amendment at B2c (park the link's event loop instead); B2f/B2g unchanged; unit tier restarted.
  3. Cluster shakedown: the daemon matcher missed a node whose command line names the clone only as `bin/../`. Harness only.
- **Missed sub-predictions (B2f/B3f/B2h/A1), recorded and not tuned:**
  - A1's band, in 1 of 1,800 cycles, 1,524 B below. A1 ignored the reserve held for a moment by a CAS-retrying acquirer (`:415-437`).
  - U2/U3 heap ratio ≥ 1.0: 0.993–0.997 in four readings, within noise.
  - M = 0 within ±2 MiB: −2.66 MiB once.
  - ΔH(4 MiB) 8–20 MiB: 58.1 MiB.
  - k ∈ [1.5, 4] at 4 MiB: 11.6.
  - `Mutation` ≈ `PendingTasks` ± a few thousand: +7.2 to +8.7 k.
- **For stage 3 (not applied):**
  - (R10) B3f's heap relation needs an intercept: the backlog's heap is ≈ k·(C + R) + H₀, where H₀ (the sent-but-unanswered messages that write handlers retain) depends on socket buffers and timeouts, not on C. A proportional k is only meaningful when C ≫ H₀/k.
  - A1-style bands for concurrent acquirers must allow for transient claimed reserve.
  - A queue-lock hold is not a neutral way to block delivery: `EventLoopDelivery` registers a callback on every failed attempt.
- **Overlap with the closed acquire-side case** (`internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided`, Confirmed at both tiers): the plateau `C + F` and the inert send endpoint key (A5) were already established there and are only re-observed here. What is new here is listed under "What this file tests beyond the closed acquire-side case" in results §1.1: the release-side invariant at every step, the stress and mutant controls, U2/U3 heap, the small-link SIGSTOP stall with the reserve read through the release, and the heap line with its intercept.
