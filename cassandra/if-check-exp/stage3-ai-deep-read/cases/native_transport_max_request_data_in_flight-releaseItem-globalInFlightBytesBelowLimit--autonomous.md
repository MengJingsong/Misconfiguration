# native_transport_max_request_data_in_flight — verification solution  <!-- file: cases/native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/transport/PreV5Handlers.java:127` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.305, 2026-10-22 |
| Estimate | `positive` (with a bounded, soft overshoot). On protocol V4 and earlier connections, the request-body bytes a node retains (pooled direct `ByteBuf`s, plus heap copies of bound values) are admitted against the global limit (and the per-IP one). Once the limit is crossed the connection stops reading. Retained request memory should therefore scale with the limit. The cap is soft: each connection force-admits at least the request that crosses the limit, plus frames already decoded in its read batch. Line 127 also lets a connection resume reading as soon as its own in-flight bytes reach 0, even while the global count is still above the limit. So the overshoot grows with the number of connections times the frame size. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- Name: `native_transport_max_request_data_in_flight`. It is a configuration entry (yaml), declared at `src/java/org/apache/cassandra/config/Config.java:298` as `public volatile DataStorageSpec.LongBytesBound native_transport_max_request_data_in_flight = null;`. It carries `@Replaces(oldName = "native_transport_max_concurrent_requests_in_bytes")` (`Config.java:297`).
- Unit: bytes. It accepts a data-storage string such as `64MiB`.
- Default: `null`, which `DatabaseDescriptor.applySimpleConfig` replaces with `Runtime.getRuntime().maxMemory() / 10`, i.e. heap/10 (`DatabaseDescriptor.java:649-652`).
- Read at runtime by `DatabaseDescriptor.getNativeTransportMaxRequestDataInFlightInBytes()` (`DatabaseDescriptor.java:3379-3382`). `ClientResourceLimits.getGlobalLimit()` (`ClientResourceLimits.java:60-63`) feeds it into the static `GLOBAL_LIMIT = new ResourceLimits.Concurrent(getGlobalLimit())` (`ClientResourceLimits.java:42`).
- How it can be set:
  - yaml key, applied at startup. The key is not listed in the shipped `conf/cassandra.yaml`, so it has to be added.
  - JMX `org.apache.cassandra.db:type=StorageService` attribute `NativeTransportMaxConcurrentRequestsInBytes` (`StorageService.java:7044-7054`). This calls `ClientResourceLimits.setGlobalLimit`, which updates `GLOBAL_LIMIT` live (`ClientResourceLimits.java:65-70`). No restart is needed.
  - Setting `-1` resets it to heap/10 (`DatabaseDescriptor.java:3384-3388`).
- Companion limit, also checked at the target line: `native_transport_max_request_data_in_flight_per_ip` (`Config.java:296`). Its default is heap/40 (`DatabaseDescriptor.java:654-657`). It is used per remote address by `ClientResourceLimits.Allocator` (`ClientResourceLimits.java:158-164`), and is settable by yaml or JMX `NativeTransportMaxConcurrentRequestsInBytesPerIp`, which is applied live to existing allocators (`ClientResourceLimits.java:78-85`).
- Why the stem names the global limit: the target's operand is `globalInFlightBytesBelowLimit`, which is `BELOW_LIMIT` only if both limits are below. The global limit is the one a user would size against heap; the per-IP limit is noted here and pinned equal to the global limit in the procedures.
- Related settings:
  - Pre-V5 maximum request size: `native_transport_max_frame_size`, default 16 MiB (`Config.java:285`, enforced at `Envelope.java:197,429`). It is not `native_transport_max_message_size`, which is V5-only (`CQLMessageHandler.java:551`).
  - If set explicitly, `native_transport_max_message_size` must be no larger than both in-flight limits (`DatabaseDescriptor.java:907-916`). That restriction does not bind V4 frames.

**A2. What it caps.**
- Resource: the memory held by native-protocol (V4/V3) requests that the node has accepted but whose response has not yet been flushed. That means two things:
  - the request `Envelope` body, a retained slice of the connection's Netty cumulation buffer, allocated from `CBUtil.allocator = new PooledByteBufAllocator(true)`, i.e. pooled **direct (off-heap)** memory (`CBUtil.java:60`, `PipelineConfigurator.java:138`, `Envelope.java:448-449`);
  - heap copies of bound values, made by `CBUtil.readValue` (`CBUtil.java:443-450`).
- Compared quantity: the sum of `header.bodySizeInBytes` (the frame's declared body length, without the 9-byte header) over in-flight requests.
- That sum is tracked in two `ResourceLimits.Concurrent` counters:
  - `GLOBAL_LIMIT.using`, the global count, exported as metric `org.apache.cassandra.metrics:type=Client,name=RequestsSize` (`ClientMetrics.java:129`);
  - the per-IP `endpoint.using`.
- Each channel also keeps `channelPayloadBytesInFlight` (`PreV5Handlers.java:70`).

**A3. Mechanism.** These are V4-and-earlier connections only. V5 uses `CQLMessageHandler` and is a different path. The pipeline is set up in `PipelineConfigurator.configureLegacyPipeline` (`PipelineConfigurator.java:388-397`), called from `InitialConnectionHandler.java:111,148` with the allocator for the remote address.

1. `Envelope.Decoder.decode` cuts a complete frame out of the cumulation buffer. A frame larger than `native_transport_max_frame_size` is discarded (`Envelope.java:429-438`). The body is `buffer.slice(...).retain()` (`Envelope.java:448-449`), so the whole frame is already in memory **before** any limit is consulted.
2. `LegacyDispatchHandler.channelRead0` → `checkLimits` (`PreV5Handlers.java:82-88,151-209`).
   - **Throw-on-overload connection** (STARTUP option `THROW_ON_OVERLOAD=1`, `StartupMessage.java:111`):
     - `endpointPayloadTracker.tryAllocate(size)` (`PreV5Handlers.java:157`) → `EndpointAndGlobal.tryAllocate`. That tries the global limit, then the endpoint limit, rolling back the global allocation if the endpoint one fails (`ResourceLimits.java:263-273`). `Concurrent.tryAllocate` fails if `using + amount > limit` (`ResourceLimits.java:130-144`).
     - On failure the request is discarded with `OverloadedException` (`PreV5Handlers.java:159,239-252`). This is a hard cap.
   - **Default connection** (drivers do not send `THROW_ON_OVERLOAD`):
     - `channelPayloadBytesInFlight += size` (`:176`).
     - If `tryAllocate` fails, the size is **force-allocated** with `allocate(size)` (`:181`, `ResourceLimits.java:146-154,275-279`), and `pauseConnection` sets `autoRead=false` (`:182,211-218`).
     - The request is still dispatched (`:87`). So the request that crosses the limit always overshoots.
     - *Stage-4 audit amendment (2026-10-22), citation fix only:* at `cassandra-5.0.9` the three lines above are `:179` (`channelPayloadBytesInFlight += requestSize`), `:184` (`allocate`) and `:185` (`pauseConnection`), not `:176`, `:181`, `:182`. The target `:127`, `:106` and `:110` are as cited. No prediction depends on the shift.
     - *Stage-4 audit note (2026-10-22), from the source, not from a run:* on the throw-on-overload path the rejected request's envelope is never released. `discardAndThrow` (`:239-252`) throws without `request.getSource().release()`, and `SimpleChannelInboundHandler` cannot release a `Message.Request` (not reference-counted), so the retained body slice, and the pooled buffer it pins, are not returned to the pool. This bears on the THROW=1 control's direct memory (B3f, B3g amendments), not on B1.
   - Rate-limiter and queue-age backpressure (`:186-207`) are disabled by default: `native_transport_rate_limiting_enabled=false` (`Config.java:299`), and `native_transport_queue_max_item_age_threshold=Double.MAX_VALUE` (`Config.java:1394`, `Dispatcher.java:342-349`).
3. Netty stops issuing socket reads once `autoRead=false`. Frames already in the cumulation buffer from the current read are still decoded and fire `channelRead0`. Each of them hits the failed `tryAllocate` → force-allocate path. This is the in-batch overshoot.
4. The request runs on the `Native-Transport-Requests` executor (`Dispatcher.java:103-126`). After the response is flushed, `Flusher` calls `item.release()` (`Flusher.java:249-250`) → `LegacyDispatchHandler.releaseItem` (`PreV5Handlers.java:100-129`). That does the following:
   - releases the request envelope, freeing the `ByteBuf` slice (`:106`);
   - decrements `channelPayloadBytesInFlight` (`:109`);
   - computes `globalInFlightBytesBelowLimit = endpointPayloadTracker.release(itemSize) == BELOW_LIMIT` (`:110`). `release` returns `ABOVE_LIMIT` if either reserve still has `using >= limit` (`ResourceLimits.java:156-172,281-287`).
5. **Target check, `PreV5Handlers.java:127`:** `if (backpressure == Overload.BYTES_IN_FLIGHT && (channelPayloadBytesInFlight == 0 || globalInFlightBytesBelowLimit)) unpauseConnection(config);`
   - The connection resumes reading when **both** reserves are strictly below their limits after this release.
   - It also resumes **as soon as this channel's own in-flight bytes reach zero, regardless of global or endpoint usage**.
   - Once it resumes, the next frame again fails `tryAllocate`, is force-allocated, and pauses the channel again. So every connection can always keep at least one request (plus its in-batch frames) in flight, even when the global count is above the limit.
6. Bound implied by the code, for C pre-V5 connections whose frames are at most F bytes: global accounted usage ≤ L + Σ over connections of (frames decoded after that connection's failing `tryAllocate`). That is roughly ≤ L + C·(F + one socket read, ≤64 KiB by Netty's adaptive receive allocator default) + one partially read frame per connection.
   - Netty's `ByteToMessageDecoder` keeps reading (`ctx.read()`) when a read produced no complete frame while `autoRead` is off, to finish a partial frame.
   - Nothing caps C: `native_transport_max_concurrent_connections=-1` (`Config.java:289`). F can be up to 16 MiB.
7. Bypasses and overshoots:
   - The force-allocated crossing request and in-batch frames (above).
   - The `channelPayloadBytesInFlight == 0` early unpause (above).
   - The whole frame is buffered before the check, and frames over `native_transport_max_frame_size` are buffered or discarded independently of this limit.
   - Only `bodySizeInBytes` is counted. The retained slice pins the entire cumulation buffer it was cut from, which can be larger. The 9-byte header, the heap copies of values, the decoded `Message` objects and the response buffers are not counted.
   - `channelInactive` (`PreV5Handlers.java:256-264`) only drops the allocator reference. The bytes are released when the flush items are released.

**A4. Other consumers.** These use the same memory outside this constraint:
- response bodies, encoded into Netty outbound buffers and released by Netty itself (comment at `PreV5Handlers.java:102-105`, `Flusher.java:245-248`);
- the V5 path, which charges the same `GLOBAL_LIMIT` but through `CQLMessageHandler` and its wait queues;
- Cassandra's own `BufferPool` (chunk cache, V5 frames, internode messaging) and internode buffers;
- memtables, both on and off heap;
- heap copies of values and the mutation objects built from them;
- TCP socket buffers, which are kernel memory, not JVM memory.

**A5. Evidence beyond the source.**
- `CHANGES.txt` entries:
  - "Make native_transport_max_concurrent_requests_in_bytes updatable (CASSANDRA-15519)" (line 1591);
  - "Allow pre-V5 global limit on bytes in flight to revert to zero asynchronously in RateLimitingTest (CASSANDRA-17927)" (line 793);
  - "Reduce native transport max frame size to 16MB (CASSANDRA-16886)" (line 1023).
- Existing test `test/unit/org/apache/cassandra/transport/ClientResourceLimitsTest.java`. Note that it uses V5 by default (`NativeProtocolLimitsTestBase.java:39`), so it does not cover `PreV5Handlers`. Its `backPressureTest` shows the "second query triggers backpressure but is allowed to complete" semantics.
- Issues: https://issues.apache.org/jira/browse/CASSANDRA-15519 , https://issues.apache.org/jira/browse/CASSANDRA-16886 .
- Netty 4.1 `ByteToMessageDecoder` and `DefaultMaxMessagesRecvByteBufAllocator.continueReading` (autoRead check): https://netty.io/4.1/api/io/netty/handler/codec/ByteToMessageDecoder.html . The Netty version is `4.1.130.Final` (`.build/parent-pom-template.xml:749`).

## B. Verification solution

**B1. Claim under test.** On protocol V4 connections, request memory retained by a node rises and falls with `native_transport_max_request_data_in_flight` (L). The accounted global in-flight bytes (`Client.RequestsSize`) are held at or below L + C·2F for C connections sending frames of at most F bytes; they never grow with the offered load beyond that. Pooled direct memory growth follows the same relation within a small factor (≤2× from cumulation-buffer rounding, plus 16 MiB pool-chunk granularity). The limit is soft: with many connections, accounted usage measurably exceeds L by about one frame per connection. The claim is wrong if:
- usage at a low L reaches the offered load; or
- usage does not change with L; or
- the overshoot does not grow with C.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11.0.32.1 and Ant 1.10.12.
- Clone the tag to local disk. Never build inside the shared tree.
  ```
  W=/tmp/s3-inflight; df -h /tmp   # must be local disk with >= 15 GB free
  git clone --branch cassandra-5.0.9 /proj/misconfiguration-PG0/git-repos/cassandra-src $W/cassandra
  cd $W/cassandra && ant jar build-test
  ```
- Test source: `$W/cassandra/test/unit/org/apache/cassandra/transport/PreV5InflightCapTest.java`. It is in that package because `LegacyDispatchHandler`'s constructor, `Envelope.Decoder.decode(ByteBuf)` and `Flusher.FlushItem.release()` are package-private.
- Run with `ant testsome -Dtest.name=org.apache.cassandra.transport.PreV5InflightCapTest`. This uses the default test JVM options and `test/conf/cassandra.yaml`.
- *Stage-4 audit amendment (2026-10-22), environment:* the run node is `pc12` (`node1.jason92-320876`, loopback only). `$W/cassandra` is the fresh clone `~/cassandra-pv5` at `cassandra-5.0.9` (`b5f2a54210`), built with `ant build-test </dev/null`; the test file is a copy of `harness/<this stem>/PreV5InflightCapTest.java`. Logs go to `~/stage4-logs/pv5/`, run copies of the harness to `~/stage4-harness-run/pv5/`. `/tmp/s3-inflight` is not used.

**B2b. Knobs.**
- L, varied by `ClientResourceLimits.setGlobalLimit(L)`, with `setEndpointLimit(L)` set to the same value so that either reserve trips at the same point.
- Values for L: 1,000,000, 4,000,000 and 16,000,000 bytes. These are exact multiples of S = 100,000 bytes, so the arithmetic is exact.
- Connection count C: 1, 8 and 64 EmbeddedChannels.
- Overload mode: default, versus `connection.setThrowOnOverload(true)` as the positive control.
- Control value L = 10^12, effectively unlimited.

**B2c. Workload.**
- Synthetic V4 QUERY requests whose source envelope declares a body of S = 100,000 bytes. They are decoded from a raw frame by `new Envelope.Decoder().decode(buf)`.
- They are written into an `EmbeddedChannel` holding a real `PreV5Handlers.LegacyDispatchHandler`.
- A `HoldingDispatcher` (a subclass of `Dispatcher`) records each dispatched request instead of executing it, so nothing is released until the test "completes" it. Completing calls the handler's own `FlushItemConverter` and then `FlushItem.release()`, which reaches `releaseItem` and the target line exactly as `Flusher` would.
- To reach the limit, send floor(L/S) = 10, 40 or 160 requests; the next one crosses.
- To go past it:
  - (a) respect `autoRead` (stop sending once it is false), modelling Netty;
  - (b) ignore it for 50 requests, modelling frames already in a read batch;
  - (c) add more channels.

**B2d. Observables and instruments.** Values are read synchronously after each `writeInbound` or completion (the EmbeddedChannel runs on the test thread):
- `ClientResourceLimits.getCurrentGlobalUsage()` (the check's operand);
- `allocator.endpointUsing()` / `allocator.globallyUsing()`;
- `ch.config().isAutoRead()` (pause state);
- the `channelPayloadBytesInFlight` field, read by reflection;
- the count of `OverloadedException`s.

Output is CSV lines prefixed `U,` on stdout, which lands in `build/test/output/TEST-...xml` / console. Actual memory is not measured in this tier; that is the cluster tier's job.

**B2e. Procedure.**
1. Create the test file below, then run `ant testsome -Dtest.name=org.apache.cassandra.transport.PreV5InflightCapTest`.
2. Collect the `U,` lines with `grep '^U,' build/test/output/TEST-org.apache.cassandra.transport.PreV5InflightCapTest.xml`. If the XML has CDATA wrappers, grep the console log instead.
   - *Stage-4 audit amendment (2026-10-22):* use `grep -o 'U,[A-E],.*'` on both the XML and the console log (a CDATA wrapper can prefix the first line); the console log is the evidence. The test must report 5 tests, 0 failures, 0 errors.

```java
package org.apache.cassandra.transport;

import java.lang.reflect.Field;
import java.net.InetAddress;
import java.util.*;

import org.junit.BeforeClass;
import org.junit.Test;

import io.netty.buffer.ByteBuf;
import io.netty.buffer.Unpooled;
import io.netty.channel.Channel;
import io.netty.channel.embedded.EmbeddedChannel;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.metrics.ClientMetrics;
import org.apache.cassandra.transport.messages.QueryMessage;
import org.apache.cassandra.transport.messages.ResultMessage;
import org.apache.cassandra.utils.FBUtilities;

public class PreV5InflightCapTest
{
    static final long S = 100_000;
    static InetAddress EP;

    static final class Held { Channel ch; Message.Request req; Dispatcher.FlushItemConverter<Object> conv; Object param; }

    static final class HoldingDispatcher extends Dispatcher
    {
        final Deque<Held> held = new ArrayDeque<>();
        HoldingDispatcher() { super(false); }
        @Override @SuppressWarnings("unchecked")
        public <P> void dispatch(Channel channel, Message.Request request, FlushItemConverter<P> f, P param, ClientResourceLimits.Overload bp)
        { Held h = new Held(); h.ch = channel; h.req = request; h.conv = (FlushItemConverter<Object>) f; h.param = param; held.add(h); }
        @Override public boolean hasQueueCapacity() { return true; }
        void complete(Held h) { h.conv.toFlushItem(h.param, h.ch, h.req, new ResultMessage.Void()).release(); }
    }

    static final class Conn { EmbeddedChannel ch; Connection c; HoldingDispatcher d = new HoldingDispatcher(); LegacyHandlerRef h; }
    static final class LegacyHandlerRef { PreV5Handlers.LegacyDispatchHandler h; }

    @BeforeClass
    public static void init() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        ClientMetrics.instance.init(Collections.emptyList());
        EP = FBUtilities.getJustLocalAddress();
    }

    static Conn open(boolean throwOnOverload)
    {
        Conn k = new Conn();
        k.h = new LegacyHandlerRef();
        k.h.h = new PreV5Handlers.LegacyDispatchHandler(k.d, QueueBackpressure.NO_OP, ClientResourceLimits.getAllocatorForEndpoint(EP));
        k.ch = new EmbeddedChannel(k.h.h);
        k.c = new Connection(k.ch, ProtocolVersion.V4, new Connection.Tracker() {
            public void addConnection(Channel ch, Connection c) {}
            public boolean isRunning() { return true; } });
        k.c.setThrowOnOverload(throwOnOverload);
        return k;
    }

    static int stream = 1;
    /** returns true if admitted, false if rejected with OverloadedException */
    static boolean send(Conn k)
    {
        ByteBuf frame = Unpooled.buffer((int) (9 + S));
        frame.writeByte(0x04).writeByte(0).writeShort(stream++ & 0x7fff).writeByte(0x07).writeInt((int) S);
        frame.writeZero((int) S);
        Envelope env = new Envelope.Decoder().decode(frame);
        frame.release();                       // env.body (retained slice) keeps it alive
        QueryMessage q = new QueryMessage("SELECT 1", QueryOptions.DEFAULT);
        q.setSource(env); q.attach(k.c);
        try { k.ch.writeInbound(q); return true; }
        catch (ErrorMessage.WrappedException e) { return false; }
    }

    static long chanInFlight(Conn k) throws Exception
    { Field f = PreV5Handlers.LegacyDispatchHandler.class.getDeclaredField("channelPayloadBytesInFlight"); f.setAccessible(true); return f.getLong(k.h.h); }

    static void limits(long L) { ClientResourceLimits.setGlobalLimit(L); ClientResourceLimits.setEndpointLimit(L); }
    static long g() { return ClientResourceLimits.getCurrentGlobalUsage(); }
    static void drain(Conn k) { while (!k.d.held.isEmpty()) k.d.complete(k.d.held.poll()); }

    @Test public void uA_sweep() throws Exception
    {
        for (long L : new long[]{ 1_000_000, 4_000_000, 16_000_000 })
        {
            limits(L); Conn k = open(false); int n = 0;
            while (k.ch.config().isAutoRead() && n < 10_000) { send(k); n++; }
            long peak = g();
            int completedAtUnpause = -1, i = 0;
            while (!k.d.held.isEmpty()) { k.d.complete(k.d.held.poll()); i++; if (completedAtUnpause < 0 && k.ch.config().isAutoRead()) completedAtUnpause = i; }
            System.out.println("U,A,L=" + L + ",admitted=" + n + ",peak=" + peak + ",unpausedAfterCompletions=" + completedAtUnpause + ",final=" + g());
            k.ch.close();
        }
    }

    @Test public void uB_connections() throws Exception
    {
        long L = 1_000_000;
        for (int C : new int[]{ 1, 8, 64 })
        {
            limits(L);
            Conn a = open(false); while (a.ch.config().isAutoRead()) send(a);     // saturate: usage = L + S
            List<Conn> bs = new ArrayList<>();
            for (int j = 0; j < C; j++) { Conn b = open(false); send(b); bs.add(b); }
            long peak = g(); int paused = 0; for (Conn b : bs) if (!b.ch.config().isAutoRead()) paused++;
            // cycle: each B completes its only request -> line 127 unpauses it although global >= L -> it sends again
            long maxDuringCycles = peak; boolean unpausedAboveLimit = false;
            for (int r = 0; r < 100; r++) for (Conn b : bs)
            {
                b.d.complete(b.d.held.poll());
                if (b.ch.config().isAutoRead() && g() >= L) unpausedAboveLimit = true;
                send(b); maxDuringCycles = Math.max(maxDuringCycles, g());
            }
            System.out.println("U,B,L=" + L + ",C=" + C + ",peak=" + peak + ",pausedB=" + paused + ",maxDuring100Cycles=" + maxDuringCycles + ",unpausedWhileGlobalAboveLimit=" + unpausedAboveLimit);
            drain(a); for (Conn b : bs) { drain(b); b.ch.close(); } a.ch.close();
            System.out.println("U,B,afterDrain=" + g());
        }
    }

    @Test public void uC_ignorePause() throws Exception
    {
        limits(1_000_000); Conn k = open(false);
        for (int n = 0; n < 50; n++) send(k);          // frames already decoded in one read batch
        System.out.println("U,C,L=1000000,sent=50,usage=" + g() + ",chan=" + chanInFlight(k) + ",autoRead=" + k.ch.config().isAutoRead());
        drain(k); k.ch.close();
    }

    @Test public void uD_throwOnOverload_control() throws Exception
    {
        limits(1_000_000); Conn k = open(true); int ok = 0, rej = 0; long max = 0;
        for (int n = 0; n < 20; n++) { if (send(k)) ok++; else rej++; max = Math.max(max, g()); }
        System.out.println("U,D,L=1000000,admitted=" + ok + ",rejected=" + rej + ",maxUsage=" + max);
        drain(k); k.ch.close();
    }

    @Test public void uE_unlimited_control() throws Exception
    {
        limits(1_000_000_000_000L); Conn k = open(false);
        for (int n = 0; n < 200; n++) send(k);
        System.out.println("U,E,L=1e12,sent=200,usage=" + g() + ",autoRead=" + k.ch.config().isAutoRead());
        drain(k); k.ch.close();
    }
}
```

If a test-harness detail differs (for example the `ResultMessage.Void` encode path needs a connection attribute), fix only the harness. Do not change any production class.

**B2f. Predictions.** Stated before any run; S = 100,000 bytes.

| Run | Prediction |
|---|---|
| U-A, L = 1e6 / 4e6 / 16e6 | `admitted` = L/S + 1 = 11 / 41 / 161. `peak` = (L/S + 1)·S = 1,100,000 / 4,100,000 / 16,100,000, so peak − L = S exactly, and peak is linear in L. `unpausedAfterCompletions` = 2: after one completion usage = L, so `release` returns ABOVE_LIMIT and the channel stays paused; after two, usage = L − S < L, so it returns BELOW and the channel resumes. `final` = 0. |
| U-B, L = 1e6, C = 1 / 8 / 64 | `peak` = L + S + C·S = 1.2e6 / 1.9e6 / 7.5e6. `pausedB` = C. `maxDuring100Cycles` = peak: it does not grow with cycles, but it does grow linearly with C. `unpausedWhileGlobalAboveLimit` = true, from the line-127 `channelPayloadBytesInFlight == 0` disjunct. `afterDrain` = 0. |
| U-C | `usage` = 50·S = 5,000,000 = 5·L. `autoRead` = false. The handler itself admits everything it is given; only the transport's honouring of `autoRead` stops ingress. |
| U-D (control) | `admitted` = 10, `rejected` = 10, `maxUsage` = 1,000,000 ≤ L. This is a hard cap. |
| U-E (control) | `usage` = 200·S = 20,000,000. `autoRead` = true. |

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| U-A peak = L + S for all three L, and U-D maxUsage ≤ L | Mechanism works as traced: the soft cap overshoots by exactly one request per pausing channel. Supports the claim. |
| U-A peak does not change with L, or `admitted` ≫ L/S + 1 | The limit does not govern admission. Claim wrong. |
| U-A `unpausedAfterCompletions` ≠ 2 (e.g. 1, or never) | Line 127's `>=`/BELOW semantics differ from the trace. Amend A3. |
| U-B peak = L + S + C·S and stable across cycles, with `unpausedWhileGlobalAboveLimit` = true | The overshoot is bounded per connection but unbounded in C. Confirms the "soft cap, overshoot ∝ C" part of the claim. |
| U-B peak grows across cycles | There is an unbounded leak path. The claim of a bound is wrong. |
| U-B `unpausedWhileGlobalAboveLimit` = false | The early-unpause branch is not reached as traced. Amend A3. |
| `final`/`afterDrain` ≠ 0 | Accounting leak. Report it as a separate finding. |
| U-E usage does not grow, or U-D admits > 10 | The workload or harness is not driving the operand. Not confirmed; fix the harness. |

*Stage-4 audit amendment (2026-10-22), before any reading: the unit tier's verdict.* The table above gives no verdict words and has no row for U-C or for a peak that follows L with a different overshoot. The tier verdict is read from the lines below; the first that applies is the verdict. "Controls valid" means U-E `usage` = 20,000,000 with `autoRead` = true, **and** U-D `admitted` = 10, `rejected` = 10, `maxUsage` ≤ 1,000,000.

| # | Readings | Verdict — Effect |
|---|---|---|
| U1 | Controls not valid (the row "U-E usage does not grow, or U-D admits > 10", or U-D `rejected` = 0), or the test class does not run to completion | **Invalid** — undetermined |
| U2 | U-A `peak` is the same at all three L, or `admitted` ≥ 2·(L/S + 1) at any L, or U-B `maxDuring100Cycles` > `peak` at any C | **Refuted** — does not cap |
| U3 | U-A `admitted` = L/S + 1 and `peak` = L + S at all three L; U-A `unpausedAfterCompletions` = 2 at all three L; U-B `peak` = L + S + C·S and `maxDuring100Cycles` = `peak` at C = 1, 8, 64, with `unpausedWhileGlobalAboveLimit` = true at every C; U-C `usage` = 5,000,000 with `autoRead` = false | **Confirmed** — caps (soft cap: overshoot one request per pausing connection) |
| U4 | U1–U3 do not apply; U-A `peak` rises with L and lies in [L, L + 2S] at every L; U-B `peak` ≤ L + S + 2·C·S at every C; but some part of U3 fails (for example `unpausedAfterCompletions` ≠ 2, `unpausedWhileGlobalAboveLimit` = false, or U-C `usage` ≠ 50·S) | **Not confirmed (trace differs)** — caps; section D records the A3 amendment the failed part implies |
| U5 | Anything else | **Not confirmed (no matching row)** — undetermined |

`final` or `afterDrain` ≠ 0 is reported as a separate accounting-leak finding and does not change the line.

**B2h. Controls.**
- U-E (unlimited) shows that the workload moves the operand linearly when no cap binds.
- U-D (throw-on-overload) is the same workload where a known hard cap binds.
- `final = 0` rules out residue between runs; every run uses fresh channels and resets limits.
- The `HoldingDispatcher` removes executor timing, so the numbers are deterministic.

### B3. Cluster tier

**B3a. Environment and build.**
- One node on 127.0.0.1, from the local clone built in B2a (`ant jar`). A second node is not needed: the limit is per node, and per-IP is pinned equal to global. The client runs on the same host.
- JVM: `export MAX_HEAP_SIZE=8G` (G1 by default from `conf/jvm11-server.options:63`; leave `HEAP_NEWSIZE` unset).
- `export JVM_EXTRA_OPTS="-Dio.netty.maxDirectMemory=0 -XX:NativeMemoryTracking=summary"`, which `conf/cassandra-env.sh:307` appends. `io.netty.maxDirectMemory=0` makes Netty allocate its pooled chunks through `ByteBuffer.allocateDirect` (the cleaner path) rather than `Unsafe` "no-cleaner" buffers. This makes them visible in the `java.nio:type=BufferPool,name=direct` MXBean. Accounting and the pooling behaviour are unchanged.
- Edits to the local clone's `conf/cassandra.yaml`. All data stays under `$W/cassandra/data` on local disk.
  ```yaml
  native_transport_max_request_data_in_flight: <L>          # knob
  native_transport_max_request_data_in_flight_per_ip: <L>   # pinned equal to L
  commitlog_sync: group                                      # replaces "periodic"
  commitlog_sync_group_window: 10000ms                       # remove commitlog_sync_period
  write_request_timeout: 30000ms
  native_transport_timeout: 60s
  auto_snapshot: false
  ```
- Rationale for the commitlog change: group commit makes each write wait for the next commitlog sync, up to 10 s (`GroupCommitLogService.java:34-41`). Each request therefore stays in flight, holding its envelope, for up to 10 s. Ingress then reliably outruns completion, and the in-flight set is governed by the limit rather than by server speed.
- *Stage-4 audit amendment (2026-10-22), timeouts and paths, before any reading.* The wait at `awaitDiskSync` blocks the thread applying the mutation, and at most `concurrent_writes` = 32 mutations apply at once (`conf/cassandra.yaml:723`), so completion runs at about 32 writes per 10-s window (≈ 3.2 writes/s), not "L per window". 1024 writes take about 320 s, and in the 4GiB and default runs most requests wait far longer than 30 s / 60 s, which would end them as timeouts. So the yaml uses `write_request_timeout: 600000ms` and `native_transport_timeout: 600000ms` (no upper bound in `DatabaseDescriptor.checkForLowestAcceptedTimeouts`). Node paths on `pc12`: the clone is `~/cassandra-pv5`; `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` and `cdc_raw_directory` are under `~/stage4-pv5/data/` (emptied per run); `CASSANDRA_LOG_DIR` is `~/stage4-logs/pv5/<run>/`; the tools (`v4load.py`, `InflightProbe`) are the harness copies in `~/stage4-harness-run/pv5/`. `JVM_EXTRA_OPTS` is given to the `bin/cassandra` command only, not exported.
- *Stage-4 runbook fix D1 (2026-10-22, step 1, before any cluster-tier run; B3f and B3g unchanged):* the yaml also sets **`commitlog_segment_size: 1536MiB`** in every run. With the shipped 32 MiB segments the group-commit hold does not hold 1 MiB writes: every segment switch requests an out-of-band sync (`AbstractCommitLogSegmentManager.java:334`, `commitLog.requestExtraSync()`), so all waiting writes are released every ~32 writes. The step-1 check (L = 4GiB, 64 requests) finished all 64 writes in 0.41 s. With one 1536 MiB segment, a run's ≈1.03 GiB of commit log never switches segment, and each write waits for the timed 10-s sync as this section intends. The yaml also pins **`max_mutation_size: 16MiB`**, the value the shipped 32 MiB segment implies (`DatabaseDescriptor.java:898-899`, segment/2). Left unset, it would become 768 MiB, and the hint buffer slab sized from it took 1.6 GB of direct memory at idle in a step-1 check, which would swamp the direct-memory observable.
- Client: the Python 3.10 script below (raw protocol V4 over a socket, no driver needed), and a JMX poller compiled with the JDK. Both live in `$W/tools`, never in the source clone.

`$W/tools/v4load.py`:
```python
#!/usr/bin/env python3
# usage: v4load.py HOST PORT CONNS TOTAL_REQS BLOB_BYTES THROW(0|1) [setup]
import socket, struct, sys, threading, time
H, P, C, N, B, THROW = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), sys.argv[6] == '1'
SETUP = len(sys.argv) > 7 and sys.argv[7] == 'setup'
def frame(st, op, body): return struct.pack('>BBhBi', 0x04, 0, st, op, len(body)) + body
def s(x): b = x.encode(); return struct.pack('>H', len(b)) + b
def ls(x): b = x.encode(); return struct.pack('>i', len(b)) + b
def rx(k, n):
    buf = bytearray()
    while len(buf) < n:
        c = k.recv(min(1 << 20, n - len(buf)))
        if not c: raise EOFError
        buf += c
    return bytes(buf)
def rframe(k):
    _, _, st, op, ln = struct.unpack('>BBhBi', rx(k, 9)); return st, op, rx(k, ln)
def connect():
    k = socket.create_connection((H, P)); k.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    opts = {'CQL_VERSION': '3.0.0'}
    if THROW: opts['THROW_ON_OVERLOAD'] = '1'
    k.sendall(frame(0, 0x01, struct.pack('>H', len(opts)) + b''.join(s(a) + s(v) for a, v in opts.items())))
    _, op, body = rframe(k); assert op == 0x02, (op, body)       # READY
    return k
def q(st, cql, vals=None):
    body = ls(cql) + struct.pack('>H', 1)                         # consistency ONE
    body += b'\x00' if vals is None else b'\x01' + struct.pack('>H', len(vals)) + b''.join(struct.pack('>i', len(v)) + v for v in vals)
    return frame(st, 0x07, body)
if SETUP:
    k = connect()
    for i, c in enumerate(["CREATE KEYSPACE IF NOT EXISTS s3 WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
                           "CREATE TABLE IF NOT EXISTS s3.t (k int PRIMARY KEY, v blob)"]):
        k.sendall(q(i + 1, c)); print(rframe(k)[1]); time.sleep(1)
    sys.exit(0)
blob = b'\xab' * B
per = N // C
res = {'ok': 0, 'overloaded': 0, 'other_err': 0}; lock = threading.Lock()
def worker(cid):
    k = connect()
    def reader():
        for _ in range(per):
            _, op, body = rframe(k)
            code = struct.unpack('>i', body[:4])[0] if op == 0x00 else None
            with lock:
                if op == 0x08: res['ok'] += 1
                elif code == 0x1001: res['overloaded'] += 1
                else: res['other_err'] += 1
    t = threading.Thread(target=reader); t.start()
    for i in range(per):
        key = cid * per + i
        k.sendall(q(1 + i % 32000, "INSERT INTO s3.t (k, v) VALUES (?, ?)", [struct.pack('>i', key), blob]))
    t.join(); k.close()
t0 = time.time(); ts = [threading.Thread(target=worker, args=(c,)) for c in range(C)]
[t.start() for t in ts]; [t.join() for t in ts]
print('RESULT', 'conns=%d reqs=%d blob=%d throw=%d secs=%.1f' % (C, N, B, THROW, time.time() - t0), res)
```
Each request body is 37 (query) + 4 + 2 + 1 + 2 + (4+4) + (4+B) = B + 58 bytes. For B = 1,048,576 that gives S = 1,048,634 bytes ≈ 1.0001 MiB.

`$W/tools/InflightProbe.java`:
```java
import javax.management.*; import javax.management.remote.*; import javax.management.openmbean.CompositeData;
public class InflightProbe {
  public static void main(String[] a) throws Exception {
    JMXConnector c = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + ":" + a[1] + "/jmxrmi"));
    MBeanServerConnection m = c.getMBeanServerConnection(); long period = Long.parseLong(a[2]), dur = Long.parseLong(a[3]);
    ObjectName rs = new ObjectName("org.apache.cassandra.metrics:type=Client,name=RequestsSize");
    ObjectName pc = new ObjectName("org.apache.cassandra.metrics:type=Client,name=PausedConnections");
    ObjectName dp = new ObjectName("java.nio:type=BufferPool,name=direct");
    ObjectName me = new ObjectName("java.lang:type=Memory");
    long t0 = System.currentTimeMillis(); System.out.println("t_ms,requests_size,paused,direct_used,direct_count,heap_used");
    while (System.currentTimeMillis() - t0 < dur) {
      System.out.println((System.currentTimeMillis() - t0) + "," + m.getAttribute(rs, "Value") + "," + m.getAttribute(pc, "Value") + ","
        + m.getAttribute(dp, "MemoryUsed") + "," + m.getAttribute(dp, "Count") + ","
        + ((CompositeData) m.getAttribute(me, "HeapMemoryUsage")).get("used"));
      Thread.sleep(period);
    }
    c.close();
  }
}
```
Build it with `cd $W/tools && javac InflightProbe.java`.

**B3b. Knobs.**
- L = `native_transport_max_request_data_in_flight`, with per-IP equal to it, set in yaml and applied by a restart per run. A restart also resets the Netty pool high-water mark.
- Values: **64MiB**, **256MiB**, and **4GiB**. 4 GiB is above the 1 GiB offered load, so it acts as "unbounded". It is explicit because the default heap/10 = ~819 MiB would bind partially.
- C (connections): 1 for all three L. Also 32 at L = 64MiB, to measure the per-connection overshoot.
- THROW: 0 for all runs, plus 1 at L = 64MiB, C = 1 as the hard-cap control.
- Control: commitlog `periodic` (the default) at L = 4GiB.
- *Stage-4 audit amendment (2026-10-22), before any reading: the default value is added.* The audit requires the default among the values. Added run **(default, C1, T0)**: `native_transport_max_request_data_in_flight` left unset (heap/10, `DatabaseDescriptor.java:649-652`), and `native_transport_max_request_data_in_flight_per_ip: 858993459B` (heap/10 for `-Xmx8G`, so the per-IP reserve is pinned to the same value as the global one, as in every other run; the shipped per-IP default heap/40 would otherwise bind first). D = the smaller of the global limit read over JMX in B3e step 3 and 858,993,459. With S = 1,048,634, floor(D/S) = 819 when D = 858,993,459, so 820 requests (≈ 820.0 MiB) are expected in flight at the peak, below the 1024 offered.

**B3c. Workload.**
- Per run: `v4load.py 127.0.0.1 9042 C 1024 1048576 THROW`, i.e. 1024 INSERTs of a 1 MiB blob. That is 1024·S ≈ 1.0 GiB offered, pipelined with no waiting, split evenly over C connections.
- Loopback ingress is ≥1 GB/s, so the full GiB can arrive within about 1–2 s. Each write is held for up to 10 s by group commit.
- So without a cap, about 1 GiB would be in flight at the peak. With L = 64 MiB, 1024 S ≫ L, so the limit is reached within the first ~64 frames.
- Each run lasts about 30–120 s. Throughput is bounded by roughly L per 10-second sync cycle: about 160 s for 1 GiB at 64 MiB with C = 1. Set the probe duration to 240 s.
- Disk: ≤1 GiB of commitlog plus ≤1 GiB of sstables per run, deleted between runs.
- *Stage-4 audit amendment (2026-10-22):* completion is about 32 writes per 10-s window (B3a amendment), so a group-commit run with 1024 requests lasts about 320 s whatever L is, and the THROW and periodic runs well under a minute. The probe duration is **480 s** (480000 ms) in every run, so the whole run including the drain to 0 is sampled.

**B3d. Observables and instruments.**
- `InflightProbe` every 200 ms:
  - `RequestsSize`, the global accounted operand;
  - `PausedConnections`;
  - `java.nio BufferPool direct MemoryUsed`, the actual pooled direct memory: Netty chunks are 16 MiB with `maxOrder=11` (`conf/jvm11-server.options:145`), plus Cassandra's own `BufferPool`;
  - heap used.
- Cross-check of direct memory with `jcmd <pid> VM.native_memory summary`, section "Other", once a second in a shell loop.
- Client `RESULT` line: ok / overloaded / other error counts.
- What cannot be observed directly:
  - per-request retained bytes;
  - which cumulation buffer each slice pins;
  - the bytes Netty has decoded but that have not yet reached `checkLimits`.
- The direct-memory measure includes pool slack (freed space inside live chunks) and is chunk-granular. Compare peak deltas over the idle baseline, not absolute values.

**B3e. Procedure.** For each run R in [ (64MiB, C1, T0), (256MiB, C1, T0), (4GiB, C1, T0), (64MiB, C32, T0), (64MiB, C1, T1), (4GiB, C1, T0, periodic) ]:
1. Make sure no node is running: `pgrep -f CassandraDaemon` must print nothing. Then `rm -rf $W/cassandra/data $W/cassandra/logs`.
2. Edit `$W/cassandra/conf/cassandra.yaml` per B3a with L for this run.
   - For the periodic control, keep the default `commitlog_sync: periodic` / `commitlog_sync_period: 10000ms` and drop the group-window line.
   - Check with `grep -nE 'request_data_in_flight|commitlog_sync|write_request_timeout|native_transport_timeout|auto_snapshot' conf/cassandra.yaml`.
3. Start the node:
   ```
   cd $W/cassandra && export MAX_HEAP_SIZE=8G JVM_EXTRA_OPTS="-Dio.netty.maxDirectMemory=0 -XX:NativeMemoryTracking=summary"
   bin/cassandra -p $W/cassandra.pid > $W/run.out 2>&1
   ```
   Wait until `bin/nodetool status` shows `UN`. Confirm the knob with `bin/nodetool sjk mx -b org.apache.cassandra.db:type=StorageService -mg -f NativeTransportMaxConcurrentRequestsInBytes`; it should equal L in bytes.
4. Run `python3 $W/tools/v4load.py 127.0.0.1 9042 1 1 1 0 setup` to create the schema. Then sleep 15 s and record a 10 s idle baseline: `java -cp $W/tools InflightProbe 127.0.0.1 7199 200 10000 > $W/R.base.csv`.
5. Start the probe in the background with `java -cp $W/tools InflightProbe 127.0.0.1 7199 200 240000 > $W/R.csv &`. Also start `while sleep 1; do jcmd $(cat $W/cassandra.pid) VM.native_memory summary | grep -A1 '^-  *Other' ; done > $W/R.nmt &`.
6. Run `python3 $W/tools/v4load.py 127.0.0.1 9042 C 1024 1048576 T | tee $W/R.client`.
7. Wait for the probe to end, then kill the NMT loop.
8. Stop the node with `bin/nodetool stopdaemon`, or `kill $(cat $W/cassandra.pid)`. Wait, then confirm `pgrep -f CassandraDaemon` prints nothing.
9. Reduce each run to:
   - peak `requests_size`;
   - max `paused`;
   - peak `direct_used` − median baseline `direct_used`;
   - peak heap;
   - client counts.

*Stage-4 audit amendment (2026-10-22), runbook details:*
- Run list: the six runs above plus **(default, C1, T0)** from the B3b amendment, in the order 64MiB-C1, 256MiB-C1, default-C1, 4GiB-C1, 64MiB-C32, 64MiB-C1-T1, 4GiB-periodic.
- Steps 1 and 8: a running node is detected as a `java` process whose arguments name `CassandraDaemon` and whose working directory or arguments name `~/cassandra-pv5` (command lines show `bin/../`), not by `pgrep -f`. The data directory emptied in step 1 is `~/stage4-pv5/data`.
- Step 3: `ulimit -n 100000` in the shell that starts the node; wait (up to 900 s) for `nodetool status` to show `UN` **and** `nodetool statusbinary` to print `running`; stop at once if the daemon dies. For the default run, the knob check must print D (B3b amendment).
- Steps 4–6: the probe duration is 480000 ms (B3c amendment); the client's start and end are logged in epoch milliseconds; the `RESULT` line is kept.
- Step 9 also reduces NMT "Other" committed: peak − first sample, as the cross-check of Δdirect.

**B3f. Predictions.** Stated before any run; S ≈ 1.0001 MiB, F = S.

| Run | Peak `RequestsSize` | Peak Δdirect (over baseline) | Other |
|---|---|---|---|
| L=64MiB, C=1 | in [L, L + 2S] = [64, ≈66.0] MiB: 64 admitted (63 by `tryAllocate` + 1 forced), + ≤1 more completed in-batch/partial frame | ≤ 2·(peak RequestsSize) + 32 MiB ≈ ≤165 MiB, and ≥ 64 MiB | `paused` max = 1; ok = 1024, overloaded = 0 |
| L=256MiB, C=1 | in [256, ≈258] MiB | in [256, ≈550] MiB | as above |
| L=4GiB, C=1 | ≈ offered in flight, ≥ 700 MiB (most of the 1 GiB lands within one 10-s window); `paused` stays 0 | ≥ 700 MiB | both peaks strictly greater than in the 64 MiB and 256 MiB runs; ok = 1024 |
| L=64MiB, C=32 | > L and ≤ L + 2·C·S ≈ 128 MiB; expected ≥ L + 8 MiB (most connections overshoot by ≥1 frame) | ≥ peak RequestsSize; ceiling ≈ 2·128 MiB + one 16 MiB pool chunk per active event-loop arena (≤32) ≈ 770 MiB; expected well below the 4GiB run's Δdirect | `paused` max between 1 and 32 |
| L=64MiB, C=1, THROW=1 (control) | ≤ L = 64 MiB exactly (hard cap) | ≤ the T0 64MiB run | overloaded > 0 (expected several hundred), ok + overloaded = 1024 |
| L=4GiB, periodic (control) | much lower than the group-commit 4GiB run (writes complete in ms) | lower than the group-commit 4GiB run | shows that the accumulation comes from the hold, not from a leak |

Key relations:
- peak `RequestsSize` and Δdirect satisfy 64MiB-run < 256MiB-run < 4GiB-run;
- peak `RequestsSize`(64MiB, C=1) ≤ 66 MiB;
- peak `RequestsSize`(64MiB, C=32) > peak `RequestsSize`(64MiB, C=1).

*Stage-4 audit amendment (2026-10-22), before any reading:*

| Run | Peak `RequestsSize` | Peak Δdirect (over baseline) | Other |
|---|---|---|---|
| default, C=1 (added) | in [D, D + 2S] (D ≈ 819.2 MiB; expected 820·S ≈ 820.0 MiB) | > the 256MiB run's Δdirect | `paused` max = 1; ok = 1024, overloaded = 0 |
| L=64MiB, C=1, THROW=1 (control), **Δdirect replaced** | (unchanged) ≤ L | **not predicted to be ≤ the T0 64MiB run.** From the source (A3 note), every rejected request's body slice is never released, so Δdirect may grow by about `overloaded` × S or more (each slice can pin a cumulation buffer of up to 2 MiB) and stay after the run | (unchanged) |

Peak `RequestsSize` ordering becomes 64MiB-run < 256MiB-run < default-run < 4GiB-run. With the B3a timeouts, `other_err` = 0 is predicted in every run.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Peak RequestsSize ≈ L (+≤2S) at C=1 for 64 and 256 MiB, ≈ offered at 4 GiB, and Δdirect ordered the same way | Limit governs retained request memory. Claim confirmed. |
| Δdirect(64MiB) ≈ Δdirect(4GiB) while RequestsSize differs | The counter is capped but actual memory is not, e.g. cumulation-buffer pinning or allocation outside accounting. Claim wrong for the actual resource; report the gap. |
| Peak RequestsSize(64MiB, C=1) > L + 2S | Admission beyond the traced overshoot; there is an unknown bypass. Claim wrong as stated. |
| Peak RequestsSize(64MiB, C=32) clearly > peak at C=1, within L + 2CS | Soft-cap overshoot grows with connections, as traced from line 127 and the forced allocation. Confirms the soft-cap part. |
| C=32 peak ≈ C=1 peak | The per-connection overshoot did not materialize (e.g. all connections paused before crossing). Soft-cap part not confirmed. The hard part of the claim still stands if C=1 holds. |
| 4GiB run peak RequestsSize small (< 256 MiB) | The hold did not work; ingress did not outrun completion. Not confirmed: re-check the group-commit settings or increase the window. |
| THROW=1 control shows overloaded = 0 and RequestsSize > L | The workload did not reach the limit, or the option was not honoured. Not confirmed. |
| `other_err` > 0 (timeouts) | Some requests were released by timeout rather than completion. Re-run with larger timeouts; does not refute. |

*Stage-4 audit amendment (2026-10-22), before any reading: the cluster tier's verdict, and rows added.* The table above gives no verdict words, and its last row asked for a re-run, which the protocol does not allow after a reading. The `other_err` row is replaced: **`other_err` > 0 is a missed sub-prediction; the peak readings stand (a timed-out request is released only when its error response is flushed, which can lower the in-flight count but never raise it); no re-run.** Rows added:

| Observation | Meaning |
|---|---|
| THROW=1 control: overloaded > 0, peak RequestsSize ≤ L, and Δdirect well above the T0 64MiB run (≥ 0.5 × `overloaded` × S) | The hard cap holds on the counter; the throw path leaks the rejected requests' buffers (A3 note). A separate finding; it does not bear on B1 and does not change the verdict line. |
| THROW=1 control: overloaded > 0, peak RequestsSize ≤ L, and Δdirect ≤ the T0 64MiB run | Hard cap holds and no throw-path leak is visible; the A3 note is wrong. Does not change the verdict line. |
| Periodic control: peak RequestsSize not below the group-commit 4GiB run | The accumulation does not come from the hold alone (server slower than ingress anyway). Recorded; does not change the verdict line. |
| Δdirect(4GiB, C1) < 0.5 × peak RequestsSize(4GiB, C1) on both the BufferPool MXBean and NMT "Other" | The direct-memory instruments do not see the request buffers; the actual-resource part of the claim cannot be judged (line C2 below). |

The tier verdict is the first line below that applies. Sub-predictions not named in a line (Δdirect bands, `paused` counts, `ok` counts, heap, the periodic control) are reported as hits or misses and do not change the line.

| # | Readings | Verdict — Effect |
|---|---|---|
| C1 | The 4GiB C1 run's peak RequestsSize < 256 MiB (hold did not work), or the THROW=1 control shows overloaded = 0 or peak RequestsSize > L | **Invalid** — undetermined |
| C2 | C1 does not apply, and Δdirect(4GiB, C1) < 0.5 × peak RequestsSize(4GiB, C1) on both direct-memory instruments | **Not confirmed (instrument)** — undetermined for memory; the counter readings are reported |
| C3 | Peak RequestsSize(64MiB, C1) ≥ 0.9 × peak RequestsSize(4GiB, C1); or peak RequestsSize not ordered 64MiB < 256MiB < 4GiB; or Δdirect(64MiB, C1) ≥ 0.8 × Δdirect(4GiB, C1) (the row "Δdirect(64MiB) ≈ Δdirect(4GiB) while RequestsSize differs") | **Refuted** — does not cap |
| C4 | C1–C3 do not apply, and peak RequestsSize > L + 2S in the 64MiB C1 or 256MiB C1 run, or > D + 2S in the default run, or > L + 2·C·S in the 64MiB C32 run | **Refuted (bypass)** — caps only on some paths |
| C5 | Peak RequestsSize in [L, L + 2S] in the 64MiB C1 and 256MiB C1 runs and in [D, D + 2S] in the default run; Δdirect ordered 64MiB < 256MiB < 4GiB; peak RequestsSize(64MiB, C32) ≥ peak RequestsSize(64MiB, C1) + 4S | **Confirmed** — caps (soft cap; overshoot grows with C) |
| C6 | C1–C4 do not apply; peak RequestsSize in [L, L + 2S] in the 64MiB C1 and 256MiB C1 runs and Δdirect ordered 64MiB < 256MiB < 4GiB; but the C32 peak is < the C1 peak + 4S, or the default run's peak is < D | **Not confirmed (partial)** — caps; the soft-cap or default part not shown |
| C7 | Anything else | **Not confirmed (no matching row)** — undetermined |

**B3h. Controls.**
- The 4GiB run is the same workload with no binding limit; it shows the workload moves actual memory.
- The THROW=1 run is a known hard cap.
- The periodic-commitlog run shows the in-flight accumulation is caused by the held writes.
- The idle baseline per run separates Cassandra's own `BufferPool` and startup allocations.
- Restarting per run resets the Netty pool high-water mark.
- Per-IP is pinned equal to global, so either reserve gives the same threshold. `RequestsSize` is the global counter and is directly comparable to L.
- NMT "Other" cross-checks the BufferPool MXBean.

**B4. Risks and cleanup.**
- Everything runs in `$W=/tmp/s3-inflight`. Check `df -h /tmp` first: at least 15 GB free is needed for the clone, the build (~3 GB), and ≤2 GiB of data per run.
- `rm -rf $W/cassandra/data` between runs. At the end, `rm -rf $W`.
- Never write in `/proj/...`.
- Processes started: the Cassandra JVM (`$W/cassandra.pid`), the probe, the NMT loop, the Python client, and the Ant test JVMs. After each run, and at the end, check `pgrep -af 'CassandraDaemon|InflightProbe|v4load.py|jcmd'` and kill any leftovers. Ant test JVMs exit with the build.
- Memory: the node uses 8 GiB heap plus ≤~3 GiB direct, well within 251 GiB.
- Ports 9042, 7000 and 7199 on 127.0.0.1 must be free. Check with `ss -ltn` first; if they are in use, pick another loopback address and ports in the yaml.

## C. Sources read

- src/java/org/apache/cassandra/transport/PreV5Handlers.java
- src/java/org/apache/cassandra/transport/ClientResourceLimits.java
- src/java/org/apache/cassandra/net/ResourceLimits.java
- src/java/org/apache/cassandra/config/Config.java (lines 151-154, 283-299, 313, 392-395, 1384-1399)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 513-525, 619-622, 640-660, 890-920, 3153-3245, 3364-3395)
- src/java/org/apache/cassandra/transport/Envelope.java
- src/java/org/apache/cassandra/transport/PipelineConfigurator.java
- src/java/org/apache/cassandra/transport/InitialConnectionHandler.java (grep)
- src/java/org/apache/cassandra/transport/Connection.java
- src/java/org/apache/cassandra/transport/Dispatcher.java (parts)
- src/java/org/apache/cassandra/transport/Flusher.java (parts)
- src/java/org/apache/cassandra/transport/Message.java (parts)
- src/java/org/apache/cassandra/transport/CBUtil.java (parts)
- src/java/org/apache/cassandra/transport/QueueBackpressure.java (grep)
- src/java/org/apache/cassandra/transport/messages/StartupMessage.java (grep)
- src/java/org/apache/cassandra/transport/messages/ResultMessage.java (grep)
- src/java/org/apache/cassandra/transport/Server.java (grep)
- src/java/org/apache/cassandra/metrics/ClientMetrics.java
- src/java/org/apache/cassandra/service/StorageService.java (7040-7070), StorageServiceMBean.java (grep)
- src/java/org/apache/cassandra/db/commitlog/GroupCommitLogService.java
- src/java/org/apache/cassandra/exceptions/ExceptionCode.java (grep)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (grep)
- test/unit/org/apache/cassandra/transport/ClientResourceLimitsTest.java
- test/unit/org/apache/cassandra/transport/NativeProtocolLimitsTestBase.java
- test/unit/org/apache/cassandra/cql3/CQLTester.java (grep)
- tools/stress/src/org/apache/cassandra/stress/settings/SettingsMode.java (grep)
- conf/cassandra.yaml (grep), conf/cassandra-env.sh (grep), conf/jvm11-server.options (grep)
- build.xml (grep), .build/parent-pom-template.xml (netty version)
- CHANGES.txt (grep)
- https://issues.apache.org/jira/browse/CASSANDRA-15519
- https://issues.apache.org/jira/browse/CASSANDRA-16886
- https://netty.io/4.1/api/io/netty/handler/codec/ByteToMessageDecoder.html

## D. Stage-4 feedback

**2026-10-22, run 1 (both tiers, `pc12`, clone `~/cassandra-pv5`; no run 2).** Results:
[`../../stage4-runtime-verification/results/native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous.md`](../../stage4-runtime-verification/results/native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous.md). Not committed.

- **Unit: Confirmed — caps (soft)** (line U3). Every B2f number exact: peak = L + S at L = 1e6 / 4e6 / 16e6, `unpausedAfterCompletions` = 2 (still paused at using = L, resumed at L − S), peak = L + S + C·S at C = 1 / 8 / 64 and stable over 100 cycles, `unpausedWhileGlobalAboveLimit` = true (the `channelPayloadBytesInFlight == 0` disjunct of `:127`), U-C 5·L with `autoRead` false, controls exact.
- **Cluster: Confirmed — caps (soft)** (line C5). Peak `RequestsSize` = (⌊L/S⌋ + 1)·S exactly: 64.0 / 256.0 / 820.0 MiB at 64MiB / 256MiB / default (heap/10), against 1,005 MiB with no binding limit (4GiB); 95·S at C = 32 (one forced request per connection, all 32 paused). THROW=1 capped the counter at 63·S with 929 refused; the periodic control peaked at 10 MiB.
- **Missed sub-prediction (B1's memory clause):** Δdirect was 1,233 / 1,872 / 3,010 / 3,264 MiB, i.e. ≈ 1.2 GiB + 2.1 × the accounted bytes. The slope matches the ≤ 2× cumulation-buffer factor; the offset does not depend on L (inferred: Netty pool slack over many direct arenas touched by the request threads that encode responses). The B3f Δdirect bands for 64MiB, 256MiB and C32 were missed.
- **Finding (source plus run):** on the throw path, direct memory rose to +3,182 MiB and stayed at +3,040 MiB after the counter returned to 0. This is consistent with the A3 note that a rejected request's envelope is never released. It is an upstream candidate; the leak itself is inferred, not proven.
- **Defects:** H1, a missing `ErrorMessage` import in the B2e test (harness fix). D1: 32 MiB commit-log segments defeat the group-commit hold (each switch forces a sync), fixed in B3a with `commitlog_segment_size: 1536MiB` and `max_mutation_size: 16MiB`. A node start under the 10-s group window takes about 7 min.
- **For stage 3:** the Estimate stands. The audit added the default value and verdict lines, and corrected the throughput arithmetic (≈ 32 writes per window, not L per window) and the line citations `:176/:181/:182` → `:179/:184/:185`.
