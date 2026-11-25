# flushHighWaterMark (internode small/urgent-message flush high-water mark) — verification solution  <!-- file: cases/flushhighwatermark-outboundconnectionsettings-flushingbytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (a capacity-set place: the field assignment `this.flushHighWaterMark = flushHighWaterMark;`), **linked**: [`OutboundConnectionSettings.java:145`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnectionSettings.java#L145) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-opus-5-5, Claude Code 2.1.330, 2026-11-24 |
| Estimate | `positive`: per small/urgent-message outbound connection, the bytes already serialized into off-heap frames and handed to Netty but not yet written to the socket (`flushingBytes`) stop growing once they reach `flushHighWaterMark` (65 536 B), with at most one frame (< 65 515 B) of overshoot; the rest of a backlog stays unserialized in the on-heap queue. The bound is real but small and hard-coded (not settable without a source change), and it does not cap the total backlog, which other limits govern. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- Name: `flushHighWaterMark` (paired with `flushLowWaterMark`), a field of `OutboundConnectionSettings`.
- Kind: a **hard-coded constant** passed through a settings object. It is not a yaml entry, not a JVM property, not JMX.
- First declared: [`OutboundConnectionSettings.java:87`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnectionSettings.java#L87) (`public final int flushLowWaterMark, flushHighWaterMark;`). Its value comes from the only public constructor path, [`OutboundConnectionSettings.java:103`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnectionSettings.java#L103), which passes the literals `1 << 15` (low = 32 768) and `1 << 16` (high = 65 536). The given line, [`OutboundConnectionSettings.java:145`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnectionSettings.java#L145), stores it in the private all-fields constructor.
- Unit: bytes, counted as "canonical size" (the message's serialized size at `current_version`, `OutboundConnection.java:1045-1048`).
- Default: 65 536 B (high), 32 768 B (low). The default is the literal itself and is not derived from anything.
- How it can be set: **not settable**. Every `with*` copy method copies the field unchanged (`OutboundConnectionSettings.java:167-321`), and `withDefaults` copies it too (`:467-480`). The one method named for it, `withNettyBufferBounds(WriteBufferWaterMark nettyBufferBounds)` (`:251-258`, `@SuppressWarnings("unused")`, no callers in `src/` or `test/`), **ignores its argument** and passes the old `flushLowWaterMark, flushHighWaterMark` on. The production construction sites all use the public constructor: `MessagingService.java:666`, `ReconnectableSnitchHelper.java:69`, `BulkLoadConnectionFactory.java:46,58`. So changing it needs a source change and a rebuild, then a restart. For tests, reflection on the `public final` instance field works.

**A2. What it caps.**
- Resource: **off-heap memory** (direct `ByteBuffer`s from the networking `BufferPool`, `FrameEncoder.java:32,64`, `BufferType.OFF_HEAP`), held by Netty's channel outbound buffer for frames that could not be written to the socket at once.
- Quantity compared: `EventLoopDelivery.flushingBytes` (`OutboundConnection.java:741`), the sum of canonical sizes of the messages in frames whose `writeAndFlush` did not finish at once and has not finished since. It applies per `OutboundConnection` that uses `EventLoopDelivery`: the **SMALL_MESSAGES and URGENT_MESSAGES** connections to each peer (`OutboundConnection.java:316-318`). LARGE_MESSAGES uses `LargeMessageDelivery` and does not read this field.

**A3. Mechanism.**
1. Messages are enqueued on the heap queue, with capacity taken from the per-link, per-endpoint and global send-queue limits (`OutboundConnection.java:325-356`). `pendingBytes()` counts everything enqueued and not yet flushed, including in-flight bytes, because capacity is released only in the flush listener (`:866`).
2. On the event loop, `doRun` returns at once if `!isWritable` (`:759-760`). Otherwise it sizes one frame as `maxSendBytes = min(pendingBytes() - flushingBytes, LARGE_MESSAGE_THRESHOLD)` (`:766`). `LARGE_MESSAGE_THRESHOLD = 65536 - max(max(21, 10), 12) = 65 515` (`OutboundConnections.java:62-70`, `CassandraRelevantProperties.java:388`, `FrameEncoderCrc.java:37`, `FrameEncoderLZ4.java:50`). It allocates an off-heap payload (`:782`), serializes queued messages into it until full (`:787-833`), and calls `AsyncChannelPromise.writeAndFlush` (`:840`).
3. If the write finished at once (the kernel took all of it), nothing is counted (`:843-848`). Otherwise `flushingBytes += canonicalSize` (`:851`), and then **the check**, [`OutboundConnection.java:854`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnection.java#L854): `boolean hasOverflowed = flushingBytes >= settings.flushHighWaterMark;`
   - **True:** `isWritable = false; promiseToExecuteLater()` (`:855-859`). Delivery stops serializing. Further messages stay unserialized in the heap queue.
   - **False:** the `finally` block reschedules delivery if `pendingBytes() > flushingBytes && isWritable` (`:908-909`), and another frame is built.
4. When a pending write completes, the listener subtracts its bytes and releases queue capacity (`:864-867`). If `!isWritable && flushingBytes <= settings.flushLowWaterMark`, it sets `isWritable = true` and calls `executeAgain()` (`:871-875`). That is hysteresis between 32 KiB and 64 KiB.
- Overshoot: the check runs **after** the frame is added, so `flushingBytes` can reach `H + (one frame) - 1`, which is under `H + 65 515` for normal small messages. Because a frame holds at most 65 515 B < 65 536, the stock setting always allows **two** full frames in flight (about 128 KiB). A message bigger than the frame space (computed for the wrong version) gets a larger buffer of its own (`:801-813`), which can overshoot further.
- Accounting skew: canonical size uses `current_version` (`:1047`), but serialization uses the peer's `messagingVersion`. With LZ4 framing the held buffer is the compressed frame, and the uncompressed input is released (`FrameEncoderLZ4.java:77,115`). So the off-heap bytes held can differ from `flushingBytes`, by being smaller with compression or slightly different across versions.
- Bypass: LARGE_MESSAGES connections (`AsyncMessageOutputPlus.java:69-71`, which uses the Netty channel's own `WriteBufferWaterMark`, not this field), streaming (`AsyncStreamingOutputPlus.java:66`), and writes that finish at once (the kernel socket buffer, sized by `internode_socket_send_buffer_size`).

**A4. Other consumers.**
- The heap send queue and its capacity limits, `internode_application_send_queue_capacity` (4 MiB per link) plus the reserve endpoint and global limits (128 MiB and 512 MiB) (`conf/cassandra.yaml:1370-1388`). These bound the total backlog. This constraint only decides how much of it is serialized off-heap.
- Large-message delivery and streaming use the Netty channel water mark instead (`AsyncMessageOutputPlus.java:69`, `AsyncStreamingOutputPlus.java:66`). The client-side native transport sets its own 8 KiB/32 KiB marks (`transport/PipelineConfigurator.java:139`).
- Kernel socket send and receive buffers (`OutboundConnectionInitiator.java:200-201`, `InboundConnectionInitiator.java:173-175`).
- The networking `BufferPool` is shared with inbound frame decoding and other internode buffers (`BufferPools.java:44-45,67-69`). Its size threshold is `networking_cache_size`, and allocations above it overflow to unpooled direct memory.

**A5. Evidence beyond the source.** Within the tree: `conf/cassandra.yaml:1370-1388` (send-queue limits), and `test/unit/org/apache/cassandra/net/ProxyHandlerConnectionsTest.java` (the harness pattern reused below). No unit test covers `flushHighWaterMark`. No git history is available in the copy. No external docs were relied on. Netty's `ChannelOutboundBuffer`/`writeAndFlush` semantics are standard (https://netty.io/4.1/api/io/netty/channel/ChannelOutboundBuffer.html).

## B. Verification solution

**B1. Claim under test.** For a small-message `OutboundConnection` whose peer has stopped reading, the off-heap in-flight bytes (`flushingBytes`, and the networking-pool memory behind them) settle at a value `F` with `H ≤ F < H + 65 515` whenever the backlog exceeds `H`, where `H = flushHighWaterMark`, and `F` follows `H` when `H` is changed. With the stock `H = 65 536`, the node's networking off-heap usage for a stalled peer stays within about 128 KiB per connection, while the backlog (`SmallMessagePendingBytes`) grows to tens of MiB on the heap. The claim is wrong if `F` exceeds `H + 65 515`, or if `F` tracks the backlog instead of `H`.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11 (`java -version` shows 11.x), Ant ≥ 1.10.
- `WORK=/mydata/$USER-s4/fhwm` on local disk with ≥ 10 GiB free (check with `df -h /mydata`).
- `rsync -a ~/cassandra-5.0.9/ $WORK/src/`, then do all work in `$WORK/src`. Never touch the shared tree.
- Build: `cd $WORK/src && ant -Dno-checkstyle=true jar build-test` (the test uses reflection only; no `src/` change is needed for this tier).
- Test source: `$WORK/src/test/unit/org/apache/cassandra/net/FlushWaterMarkTest.java` (below).
- JVM: the default unit-test JVM options from `build.xml` (test heap 1 GiB). Add `-Dfhwm.highs=16384,65536,262144,1048576,8388608` through `-Dtest.jvm.args` only if the default list is to be overridden. The test's default is that same list.

**B2b. Knobs.**
- `H = flushHighWaterMark` ∈ {16 384; 65 536 (stock); 262 144; 1 048 576; 8 388 608}, with `L = flushLowWaterMark = H/2` each time. The values are set by reflection on the settings object before the `OutboundConnection` is built, because `withDefaults` copies the field (A1).
- Why these values: 16 KiB sits under one frame (one frame expected), 64 KiB is stock (two frames), 256 KiB and 1 MiB check proportional scaling, and 8 MiB sits above the workload `W`, so the mark never binds (the uncapped control).
- Fixed settings: CRC framing, `socketSendBufferSizeInBytes = 4096`, `tcpUserTimeoutInMS = 0` (so a stalled link is not torn down), `applicationSendQueueCapacityInBytes = 16 MiB` (so the burst is never rejected).

**B2c. Workload.**
- `N = 3072` messages of `Verb._TEST_1`, each with a 1 024-byte payload (128 longs). Each message is `s ≈ 1 040 B` serialized, and the test prints the exact `s`. So `W = N·s ≈ 3.19 MB`.
- The burst is enqueued after the relay between outbound and inbound is paused.
- Kernel absorption is at most about 4.6 KiB (sender SO_SNDBUF floor) plus a few KiB (relay SO_RCVBUF 4 KiB) plus ≤ 1 KiB (relay buffer), so under 16 KiB. Therefore at least `W - 16 KiB ≈ 3.17 MB` cannot be written. That is ≫ H for every H except the control (8 MiB > W).
- A frame holds `m = floor(65 515 / s)` messages, about 62, so a full frame is `B = m·s ≈ 64.5 KB`.
- Expiration is raised to 1 hour so nothing expires during the stall.

**B2d. Observables and instruments.**
- `flushingBytes` and `isWritable` of `OutboundConnection.delivery` (an `EventLoopDelivery`), read by reflection **on the connection's event loop** (`eventLoop.submit(...)`), polled every 50 ms.
- `outbound.pendingBytes()` (public).
- `BufferPools.forNetworking().usedSizeInBytes()` delta from just before the burst. This is secondary: it is chunk-granular (128 KiB chunks, `BufferPool.java:128`) and shared with other pool users.
- After resume: the received count from the verb handler, and `flushingBytes` going back to 0.
- Cannot be observed directly: Netty's `ChannelOutboundBuffer` byte count, because Cassandra installs `NoSizeEstimator` (`OutboundConnectionInitiator.java:197`). `flushingBytes` stands in for it.

**B2e. Procedure.**
1. Create the test file:

```java
package org.apache.cassandra.net;

import java.io.*;
import java.lang.reflect.Field;
import java.net.*;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Supplier;
import java.util.function.ToLongFunction;

import org.junit.BeforeClass;
import org.junit.Test;

import io.netty.channel.EventLoop;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.commitlog.CommitLog;
import org.apache.cassandra.io.IVersionedAsymmetricSerializer;
import org.apache.cassandra.io.IVersionedSerializer;
import org.apache.cassandra.io.util.DataInputPlus;
import org.apache.cassandra.io.util.DataOutputPlus;
import org.apache.cassandra.locator.InetAddressAndPort;
import org.apache.cassandra.utils.FBUtilities;
import org.apache.cassandra.utils.memory.BufferPools;

import static java.util.Collections.singletonList;
import static java.util.concurrent.TimeUnit.SECONDS;

public class FlushWaterMarkTest
{
    static final SocketFactory factory = new SocketFactory();
    static final int LONGS = 128, N = 3072;

    static class Ser implements IVersionedSerializer<Long>
    {
        public void serialize(Long v, DataOutputPlus out, int version) throws IOException { for (int i = 0; i < LONGS; i++) out.writeLong(v); }
        public Long deserialize(DataInputPlus in, int version) throws IOException { long v = 0; for (int i = 0; i < LONGS; i++) v = in.readLong(); return v; }
        public long serializedSize(Long v, int version) { return 8L * LONGS; }
    }

    /** TCP relay whose client->server direction can be paused (stops reading). */
    static class Relay implements Closeable
    {
        final ServerSocket server = new ServerSocket();
        final List<Socket> sockets = new CopyOnWriteArrayList<>();
        volatile boolean paused;
        Relay(InetSocketAddress target) throws IOException
        {
            server.setReceiveBufferSize(4096);
            server.bind(new InetSocketAddress("127.0.0.1", 0));
            Thread t = new Thread(() -> {
                try { while (true) {
                    Socket in = server.accept(); in.setReceiveBufferSize(4096);
                    Socket out = new Socket(); out.connect(target);
                    sockets.add(in); sockets.add(out);
                    pump(in, out, true); pump(out, in, false);
                } } catch (IOException ignore) {}
            }, "relay-accept");
            t.setDaemon(true); t.start();
        }
        void pump(Socket from, Socket to, boolean pausable)
        {
            Thread t = new Thread(() -> {
                byte[] b = new byte[1024];
                try { InputStream i = from.getInputStream(); OutputStream o = to.getOutputStream();
                      while (true) { while (pausable && paused) Thread.sleep(5);
                                     int n = i.read(b); if (n < 0) break; o.write(b, 0, n); o.flush(); } }
                catch (Exception ignore) {}
            }, "relay-pump");
            t.setDaemon(true); t.start();
        }
        int port() { return server.getLocalPort(); }
        public void close() throws IOException { server.close(); for (Socket s : sockets) s.close(); }
    }

    static void setMarks(OutboundConnectionSettings s, int low, int high) throws Exception
    {
        Field lo = OutboundConnectionSettings.class.getField("flushLowWaterMark");  lo.setAccessible(true); lo.setInt(s, low);
        Field hi = OutboundConnectionSettings.class.getField("flushHighWaterMark"); hi.setAccessible(true); hi.setInt(s, high);
        if (s.flushHighWaterMark != high || s.flushLowWaterMark != low) throw new AssertionError("reflection failed");
    }

    static int[] probe(OutboundConnection c) throws Exception
    {
        Field d = OutboundConnection.class.getDeclaredField("delivery"); d.setAccessible(true);
        Object del = d.get(c);
        Field fb = del.getClass().getDeclaredField("flushingBytes"); fb.setAccessible(true);
        Field w  = del.getClass().getDeclaredField("isWritable");    w.setAccessible(true);
        Field el = OutboundConnection.class.getDeclaredField("eventLoop"); el.setAccessible(true);
        EventLoop loop = (EventLoop) el.get(c);
        return loop.submit(() -> new int[]{ fb.getInt(del), w.getBoolean(del) ? 1 : 0 }).get(5, SECONDS);
    }

    @BeforeClass
    public static void init()
    {
        DatabaseDescriptor.daemonInitialization();
        CommitLog.instance.start();
    }

    @Test
    public void sweep() throws Throwable
    {
        String highs = System.getProperty("fhwm.highs", "16384,65536,262144,1048576,8388608");
        System.out.println("FHWM,H,L,s,N,W,flushingBytes,isWritable,pendingBytes,poolDelta,received,flushingAfterResume");
        for (String h : highs.split(","))
            runOne(Integer.parseInt(h.trim()));
    }

    void runOne(int H) throws Throwable
    {
        Supplier<? extends IVersionedAsymmetricSerializer<?, ?>> oldSer = Verb._TEST_1.unsafeSetSerializer(Ser::new);
        AtomicLong received = new AtomicLong();
        Supplier<? extends IVerbHandler<?>> oldHandler = Verb._TEST_1.unsafeSetHandler(() -> m -> received.incrementAndGet());
        ToLongFunction<TimeUnit> oldExp = Verb._TEST_1.unsafeSetExpiration(u -> u.convert(1, TimeUnit.HOURS));

        InetAddressAndPort endpoint = FBUtilities.getBroadcastAddressAndPort();
        InboundSockets inbound = new InboundSockets(singletonList(new InboundConnectionSettings().withBindAddress(endpoint).withSocketFactory(factory)));
        inbound.open().sync();
        Relay relay = new Relay(new InetSocketAddress(endpoint.getAddress(), endpoint.getPort()));
        OutboundConnectionSettings os = new OutboundConnectionSettings(endpoint)
                .withConnectTo(InetAddressAndPort.getByAddressOverrideDefaults(InetAddress.getByName("127.0.0.1"), relay.port()))
                .withFraming(OutboundConnectionSettings.Framing.CRC)
                .withSocketSendBufferSizeInBytes(4096)
                .withTcpUserTimeoutInMS(0)
                .withApplicationSendQueueCapacityInBytes(16 << 20)
                .withDefaultReserveLimits()
                .withSocketFactory(factory);
        setMarks(os, H / 2, H);
        ResourceLimits.EndpointAndGlobal reserve = new ResourceLimits.EndpointAndGlobal(
                new ResourceLimits.Concurrent(os.applicationSendQueueReserveEndpointCapacityInBytes),
                os.applicationSendQueueReserveGlobalCapacityInBytes);
        OutboundConnection out = new OutboundConnection(ConnectionType.SMALL_MESSAGES, os, reserve);
        try
        {
            out.enqueue(Message.out(Verb._TEST_1, 1L));                        // connect + handshake through the relay
            long t = System.nanoTime();
            while (received.get() < 1) { if (System.nanoTime() - t > SECONDS.toNanos(10)) throw new AssertionError("no connect"); Thread.sleep(10); }

            int s = Message.out(Verb._TEST_1, 1L).serializedSize(MessagingService.current_version);
            long pool0 = BufferPools.forNetworking().usedSizeInBytes();
            relay.paused = true;
            Thread.sleep(200);
            for (int i = 0; i < N; i++) out.enqueue(Message.out(Verb._TEST_1, 1L));

            int[] p = probe(out); int stable = 0; t = System.nanoTime();          // wait until flushingBytes is stable for 1 s
            while (stable < 20 && System.nanoTime() - t < SECONDS.toNanos(30))
            { Thread.sleep(50); int[] q = probe(out); stable = (q[0] == p[0]) ? stable + 1 : 0; p = q; }
            long pending = out.pendingBytes();
            long poolDelta = BufferPools.forNetworking().usedSizeInBytes() - pool0;

            relay.paused = false;                                               // control: drain
            t = System.nanoTime();
            while (received.get() < N + 1 && System.nanoTime() - t < SECONDS.toNanos(60)) Thread.sleep(20);
            Thread.sleep(200);
            int[] after = probe(out);
            System.out.printf("FHWM,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d%n",
                              H, H / 2, s, N, (long) N * s, p[0], p[1], pending, poolDelta, received.get() - 1, after[0]);
        }
        finally
        {
            out.close(false).get(30, SECONDS);
            inbound.close().get(30, SECONDS);
            relay.close();
            MessagingService.instance().messageHandlers.clear();
            Verb._TEST_1.unsafeSetSerializer(oldSer);
            Verb._TEST_1.unsafeSetHandler(oldHandler);
            Verb._TEST_1.unsafeSetExpiration(oldExp);
        }
    }
}
```

   (Small compile fixes, such as missing imports or exact generic types of `unsafeSet*`, are allowed. Do not change the logic.)
2. Run: `cd $WORK/src && ant -Dno-checkstyle=true testsome -Dtest.name=org.apache.cassandra.net.FlushWaterMarkTest 2>&1 | tee $WORK/unit.log`.
3. Extract the rows: `grep '^FHWM' $WORK/unit.log` (the output goes to `build/test/output/TEST-org.apache.cassandra.net.FlushWaterMarkTest.xml` if it is not on the console).
4. Repeat the run 3 times and keep all rows.
5. Check that nothing is left: `pgrep -f FlushWaterMarkTest` shows nothing.

**B2f. Predictions.** Let `s` = printed size, `m = floor(65515/s)` (≈ 62), `B = m·s` (≈ 64.5 KB), and `W = N·s` (≈ 3.19 MB). In general, for `H < W`: `H ≤ flushingBytes < H + 65 515` and `isWritable = 0`. Usually `flushingBytes = ceil(H/B)·B`, because frames are full while the backlog is large. Early partial frames may make it smaller, but never below `H`.

| H | expected `flushingBytes` | isWritable | pendingBytes |
|---|---|---|---|
| 16 384 | ≈ 1·B ≈ 64.5 KB (in [16 384, 81 899)) | 0 | ≈ W − (≤ 16 KiB) |
| 65 536 (stock) | ≈ 2·B ≈ 129 KB (in [65 536, 131 051)) | 0 | same |
| 262 144 | ≈ 5·B ≈ 322 KB (in [262 144, 327 659)) | 0 | same |
| 1 048 576 | ≈ 17·B ≈ 1.10 MB (in [1 048 576, 1 114 091)) | 0 | same |
| 8 388 608 (control, > W) | ≈ W − (≤ 16 KiB) ≈ 3.17–3.19 MB | 1 | same |

- `poolDelta` rises with `flushingBytes`. It is within ±256 KiB of it for H ≥ 1 MiB and for the control, and it is ≤ 512 KiB for H ≤ 64 KiB.
- After resume: `received = N` and `flushingAfterResume = 0` for every H.
- All five values of `pendingBytes` are equal within 16 KiB. The backlog does not depend on H; only its off-heap share does.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `flushingBytes` in `[H, H+65 515)` for each H < W, and ≈ W for the 8 MiB control | Claim confirmed: the mark caps the in-flight serialized bytes, with at most one frame of overshoot. |
| `flushingBytes ≥ H + 65 515` for some H < W | Claim wrong: the cap is overshot by more than one frame (look for oversize frames or accounting skew). |
| `flushingBytes` ≈ W for all H | Claim wrong: the field does not govern delivery (or reflection did not take effect; see controls). |
| `flushingBytes` < H with `isWritable = 0` | Inconsistent with the check at `:854`. The probe or reflection is broken. |
| 8 MiB control also stalls near 64–128 KB | The stall is not reaching Netty, or another mechanism limits it. The workload is not testing this check (not confirmed). |
| `flushingBytes = 0` for all H while `pendingBytes` ≈ W | The relay did not stall the socket and writes finished at once. The limit was never reached (not confirmed). |
| `poolDelta` flat while `flushingBytes` follows H | `flushingBytes` is not backed by pool memory as traced (check LZ4/unpooled paths). The operand claim holds, but the memory claim is not shown. |
| After resume, `received < N` or `flushingAfterResume ≠ 0` | Messages are lost or the counter leaks. Report it; it weakens the readings. |

**B2h. Controls.**
- The 8 MiB run is the positive control: the same workload moves `flushingBytes` up to ≈ W when the mark cannot bind.
- The printed `s.flushHighWaterMark` assertion in `setMarks` confirms the reflection.
- `pendingBytes` constant across H shows the backlog is the same, so only the off-heap split varies.
- Drain after resume shows the stall was the relay, not a broken connection.
- Three repeats bound the run-to-run noise.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux host with JDK 11, two nodes: A on 127.0.0.1 and B on 127.0.0.2 (loopback /8). Cassandra data, commitlog and logs go under `$WORK/nodeA` and `$WORK/nodeB` on local disk, with ≥ 20 GiB free.
- Instrumentation patch (needed because the constant is not settable, A1), made in the copy only: `cp -a $WORK/src $WORK/cass`, then replace line 103 of `$WORK/cass/src/java/org/apache/cassandra/net/OutboundConnectionSettings.java` with:

```java
        this(null, to, preferred, null, null, null, null, null, null, null,
             Integer.getInteger("cassandra.test.flush_low_water_mark", 1 << 15),  // checkstyle: suppress nearby 'blockSystemPropertyUsage'
             Integer.getInteger("cassandra.test.flush_high_water_mark", 1 << 16),
             null, null, null, null, null, null, null, null);
```

   When the properties are absent, the behaviour is exactly the stock behaviour.
- Build: `cd $WORK/cass && ant -Dno-checkstyle=true jar`.
- Conf per node: `cp -a $WORK/cass/conf $WORK/confA` and the same for `confB`. In each `cassandra.yaml` set:
  - `cluster_name: fhwm`
  - `num_tokens: 16`
  - `seed_provider ... seeds: "127.0.0.1:7000"`
  - `listen_address` / `rpc_address`: `127.0.0.1` for A, `127.0.0.2` for B
  - `data_file_directories: [$WORK/nodeX/data]`, `commitlog_directory`, `saved_caches_directory`, `hints_directory` under `$WORK/nodeX`
  - `hinted_handoff_enabled: false`
  - `phi_convict_threshold: 12`
  - `write_request_timeout: 10000ms`
  - `internode_compression: none`
  - `internode_socket_send_buffer_size: 4KiB`
  - `internode_socket_receive_buffer_size: 4KiB`
  - `internode_tcp_user_timeout: 0ms`
  - `networking_cache_size: 128MiB`
- In `confB/cassandra-env.sh`, change `JMX_PORT="7199"` to `JMX_PORT="7299"`.
- JVM: `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`, and `JVM_EXTRA_OPTS="-XX:MaxDirectMemorySize=1G -XX:NativeMemoryTracking=summary $MARKS"` on A. B always runs stock (no `$MARKS`).

**B3b. Knobs.** On node A only, restarting between values:
- `MARKS=""` (stock, H = 65 536)
- `MARKS="-Dcassandra.test.flush_low_water_mark=524288 -Dcassandra.test.flush_high_water_mark=1048576"` (H = 1 MiB)
- `MARKS="-Dcassandra.test.flush_low_water_mark=134217728 -Dcassandra.test.flush_high_water_mark=268435456"` (H = 256 MiB, above the 132 MiB send-capacity backlog ceiling, so the mark cannot bind: the uncapped control)

Confirm each value with `jcmd $(cat $WORK/nodeA/pid) VM.system_properties | grep flush_`.

**B3c. Workload.**
- `cassandra-stress` writes against A only, at RF=2 and CL=ONE, so every write makes A send a ~1.1 KB mutation to B on the SMALL link. The stress command uses `duration=120s`, `threads=32` and 1 KiB values.
- At t = 40 s, B is frozen with `kill -STOP`, and at t = 60 s it is resumed with `kill -CONT`.
- At ≥ 5 MB/s of replica traffic, the backlog to B passes 64 MiB within ~13 s of the stop and is limited by the send-queue capacity of 4 MiB + 128 MiB ≈ 132 MiB (A4). So the backlog is 1000× H for stock H.
- Phi 12 delays conviction of B to about 25 s, so B stays a write target for the whole 20 s window.

**B3d. Observables and instruments.** A small JMX sampler on A, polling every 500 ms (`$WORK/Sampler.java`, run with `java $WORK/Sampler.java 7199 '127.0.0.2_7000' 180 > $RUN/samples.csv`):

```java
import javax.management.*; import javax.management.remote.*; import java.lang.management.*;
public class Sampler { public static void main(String[] a) throws Exception {
  JMXConnector c = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi"));
  MBeanServerConnection m = c.getMBeanServerConnection(); String p = a[1]; int n = Integer.parseInt(a[2]);
  ObjectName pb = new ObjectName("org.apache.cassandra.metrics:type=Connection,scope=" + p + ",name=SmallMessagePendingBytes");
  ObjectName ov = new ObjectName("org.apache.cassandra.metrics:type=Connection,scope=" + p + ",name=SmallMessageDroppedTasksDueToOverload");
  ObjectName nu = new ObjectName("org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize");
  ObjectName dm = new ObjectName("java.nio:type=BufferPool,name=direct");
  ObjectName hp = new ObjectName("java.lang:type=Memory");
  System.out.println("ms,pendingBytes,overloadDrops,netPoolUsed,directUsed,heapUsed");
  for (int i = 0; i < n; i++) {
    Object h = m.getAttribute(hp, "HeapMemoryUsage");
    System.out.println(System.currentTimeMillis() + "," + m.getAttribute(pb, "Value") + "," + m.getAttribute(ov, "Value") + ","
      + m.getAttribute(nu, "Value") + "," + m.getAttribute(dm, "MemoryUsed") + "," + ((javax.management.openmbean.CompositeData) h).get("used"));
    Thread.sleep(500); }
  c.close(); } }
```

- Primary readings: `netPoolUsed` (networking `BufferPool.usedSizeInBytes`, `BufferPoolMetrics.java:62`) and `directUsed`, each minus their mean over the 10 s before the STOP. Secondary readings: `pendingBytes` (the backlog), `overloadDrops`, `heapUsed` (noisy, GC), and an NMT summary (`jcmd PID VM.native_memory summary`, "Other" section) at STOP + 15 s.
- Cannot be observed directly: `flushingBytes`. It is inferred from the pool delta, which includes chunk rounding (128 KiB) and other pool users, such as inbound decoding from B, which drops to ~0 while B is frozen.

**B3e. Procedure.** For each knob value, as run `R` with `RUN=$WORK/runs/$R`:
1. `mkdir -p $RUN`. Clear the data dirs: `rm -rf $WORK/nodeA/* $WORK/nodeB/*`.
2. Start B, then A:
   - `CASSANDRA_CONF=$WORK/confB CASSANDRA_LOG_DIR=$WORK/nodeB/logs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M $WORK/cass/bin/cassandra -p $WORK/nodeB/pid`
   - Wait 30 s.
   - `CASSANDRA_CONF=$WORK/confA CASSANDRA_LOG_DIR=$WORK/nodeA/logs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M JVM_EXTRA_OPTS="-XX:MaxDirectMemorySize=1G -XX:NativeMemoryTracking=summary $MARKS" $WORK/cass/bin/cassandra -p $WORK/nodeA/pid`
   - Wait until `$WORK/cass/bin/nodetool -p 7199 status` shows two `UN` nodes.
3. Verify the knob: `jcmd $(cat $WORK/nodeA/pid) VM.system_properties | grep flush_ > $RUN/props.txt`.
4. Start the workload: `$WORK/cass/tools/bin/cassandra-stress write duration=120s cl=ONE no-warmup -schema "replication(strategy=SimpleStrategy,factor=2)" -col "n=FIXED(1)" "size=FIXED(1024)" -rate threads=32 -node whitelist 127.0.0.1 -log level=minimal > $RUN/stress.log 2>&1 &`
5. At t = 20 s, start the sampler: `java $WORK/Sampler.java 7199 127.0.0.2_7000 180 > $RUN/samples.csv &` (90 s at 0.5 s per sample).
6. At t = 40 s, `kill -STOP $(cat $WORK/nodeB/pid); date +%s%3N > $RUN/stop.ts`. At t = 55 s, run `jcmd $(cat $WORK/nodeA/pid) VM.native_memory summary > $RUN/nmt.txt`. At t = 60 s, `kill -CONT $(cat $WORK/nodeB/pid); date +%s%3N > $RUN/cont.ts`.
7. Wait for stress and the sampler to exit. Copy `$WORK/nodeA/logs/system.log` to `$RUN/`.
8. Stop both nodes: `kill $(cat $WORK/nodeA/pid) $(cat $WORK/nodeB/pid)`, then wait until `pgrep -f CassandraDaemon` is empty.
9. Repeat for the next knob value. Run the whole set twice. Also run one stock no-stall run (skip step 6).
10. Analysis: within [STOP + 5 s, STOP + 20 s], report max(`netPoolUsed`) − baseline, max(`directUsed`) − baseline, and max(`pendingBytes`).

**B3f. Predictions.** For all stalled runs, max `pendingBytes` ≥ 20 MiB, and in practice up to about 132 MiB, with `overloadDrops` rising once it saturates.

| Run | Δ `netPoolUsed` | Δ `directUsed` |
|---|---|---|
| stock (H = 64 KiB) | ≤ 1 MiB (2 frames ≈ 129 KB on SMALL, ~0 on URGENT, plus chunk rounding) | ≤ 8 MiB (at most one extra macro-chunk) |
| H = 1 MiB | between 1 MiB and 3 MiB (≈ 1.1 MB plus rounding) | ≤ 8 MiB |
| H = 256 MiB (uncapped control) | ≥ 0.8 × max `pendingBytes`, i.e. tens to ≈ 132 MiB, tracking `pendingBytes` | rises by ≥ 64 MiB (part of it as unpooled overflow beyond `networking_cache_size`) |

- No-stall stock run: Δ `netPoolUsed` ≤ 1 MiB and `pendingBytes` ≤ 1 MiB.
- After CONT, every run returns to baseline within 30 s.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Stock Δ ≤ 1 MiB and H = 1 MiB Δ ≈ 1–3 MiB while `pendingBytes` ≫ both, and the 256 MiB control's Δ follows `pendingBytes` | Claim confirmed at node level: the mark caps the off-heap in-flight bytes and the backlog stays on heap. |
| Stock Δ ≥ 8 MiB while `pendingBytes` ≫ 8 MiB | Claim wrong: off-heap usage is not held to H + one frame. |
| Δ is the same for all three H while `pendingBytes` is large | Claim wrong (or the `-D` did not take effect; check `props.txt`). |
| `pendingBytes` stays small (< 20 MiB) in stalled runs | The workload did not build a backlog, so the limit was never stressed (not confirmed). Raise `threads`. |
| The 256 MiB control's Δ stays ≤ 3 MiB | The positive control did not move. Either the pool metric does not see these buffers or the stall does not reach Netty (not confirmed). Check `directUsed` and NMT. |
| B convicted (`system.log` on A shows B DOWN) before STOP + 20 s | The window is shortened. Use only samples before the DOWN timestamp. |

**B3h. Controls.**
- The uncapped 256 MiB run is the positive control: the same workload with the mark out of reach moves off-heap usage.
- The no-stall stock run sets the baseline noise.
- B runs the stock build throughout, so only A's mark changes.
- Compression off, so canonical size ≈ wire size.
- Hints off, so there is no hint-file disk or heap noise.
- `props.txt` shows which value was in effect.
- Two repetitions.

**B4. Risks and cleanup.**
- Disk: stress writes ≈ 120 s × ~20 MB/s × 2 replicas ≈ 5 GB per run under `$WORK`. Clear the data dirs between runs and `rm -rf $WORK/nodeA $WORK/nodeB $WORK/runs/*/` large files at the end. Keep `samples.csv`, `props.txt`, `nmt.txt` and the logs.
- Memory: A uses up to 2 GiB heap + 1 GiB direct. Two nodes need ≈ 6 GiB RAM free.
- Leftover processes: after each run, `pgrep -f CassandraDaemon`, `pgrep -f cassandra-stress`, `pgrep -f Sampler` and `pgrep -f FlushWaterMarkTest` must all be empty. Never leave B in the STOP state; if a script aborts, run `kill -CONT` then `kill` on B.
- Nothing is written to the shared source tree. The patch and builds are only in `$WORK/cass` and `$WORK/src`.
- Ports used: 7000, 9042, 7199 and 7299 on 127.0.0.1/127.0.0.2. Check they are free first: `ss -ltn`.

## C. Sources read

- src/java/org/apache/cassandra/net/OutboundConnectionSettings.java
- src/java/org/apache/cassandra/net/OutboundConnection.java
- src/java/org/apache/cassandra/net/OutboundConnections.java
- src/java/org/apache/cassandra/net/OutboundConnectionInitiator.java
- src/java/org/apache/cassandra/net/InboundConnectionInitiator.java
- src/java/org/apache/cassandra/net/InboundSockets.java
- src/java/org/apache/cassandra/net/InboundConnectionSettings.java
- src/java/org/apache/cassandra/net/AsyncMessageOutputPlus.java
- src/java/org/apache/cassandra/net/AsyncStreamingOutputPlus.java
- src/java/org/apache/cassandra/net/AsyncChannelPromise.java
- src/java/org/apache/cassandra/net/FrameEncoder.java
- src/java/org/apache/cassandra/net/FrameEncoderCrc.java
- src/java/org/apache/cassandra/net/FrameEncoderLZ4.java
- src/java/org/apache/cassandra/net/MessagingService.java (line 666)
- src/java/org/apache/cassandra/net/Verb.java
- src/java/org/apache/cassandra/net/SocketFactory.java
- src/java/org/apache/cassandra/transport/PipelineConfigurator.java
- src/java/org/apache/cassandra/locator/ReconnectableSnitchHelper.java
- src/java/org/apache/cassandra/locator/InetAddressAndPort.java
- src/java/org/apache/cassandra/tools/BulkLoadConnectionFactory.java
- src/java/org/apache/cassandra/metrics/InternodeOutboundMetrics.java
- src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java
- src/java/org/apache/cassandra/utils/memory/BufferPool.java
- src/java/org/apache/cassandra/utils/memory/BufferPools.java
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- conf/cassandra.yaml
- .build/checkstyle.xml, .build/build-checkstyle.xml
- test/unit/org/apache/cassandra/net/ProxyHandlerConnectionsTest.java
- test/unit/org/apache/cassandra/net/OutboundConnectionSettingsTest.java
- https://netty.io/4.1/api/io/netty/channel/ChannelOutboundBuffer.html

## D. Stage-4 feedback

**Stage-4 amendments (2026-11-25, Jingsong's stage-4 session, made in the design audit before any reading; B1, B2f, B3f and the rows of B2g/B3g are unchanged):**

- **S4-A1 (runnability, B2a/B3a/B3e).** `WORK=/mydata/jingsong-cass-s4/o125` (created with `sudo mkdir` + `chown`, `/mydata` is root-owned). Instead of `rsync` + `ant jar build-test`, copy the built 5.0.9 copy: `cp -a /mydata/s4/cassandra-base $WORK/src` (unit) and `cp -a /mydata/s4/cassandra-base $WORK/cass` (cluster; patch line 103, then `ant -Dno-checkstyle=true jar`); `ant testsome` compiles the new test. Cluster conf: also set `cdc_raw_directory` under `$WORK/nodeX` (its default `$CASSANDRA_HOME/data/cdc_raw` would be shared by A and B), and comment out the stock lines of each overridden key so the yaml has no duplicate keys. Run `ulimit -n 100000` before starting a node; give `nodetool`/`cassandra-stress` `CASSANDRA_CONF` of the node they talk to. Step 2's wait also requires `nodetool statusbinary` = `running` on both nodes (environment.md §6). The no-stall run records `stop.ts`/`cont.ts` at t = 40 s / 60 s without signalling B, so step 10's window is the same.
- **S4-A2 (B2g verdict labels).** Over all three repeats: **Confirmed** = the first row holds for every H < W (`flushingBytes` in `[H, H+65 515)` with `isWritable = 0`) and the 8 MiB control has `flushingBytes ≥ W − 32 KiB` with `isWritable = 1`, and the control's `poolDelta ≥ 1 MiB`. **Refuted** = the second or third row (any H < W with `flushingBytes ≥ H + 65 515`, or every H ≈ W). **Not confirmed** = the fourth, fifth or sixth row, or the seventh row ("`poolDelta` flat" = control `poolDelta` < 1 MiB: operand capped, memory not shown). The eighth row (`received < N` or `flushingAfterResume ≠ 0`) is reported and weakens, but does not by itself change, the label. Effect: Confirmed → `caps` (the in-flight serialized off-heap bytes per small/urgent connection, not the total backlog).
- **S4-A3 (B3g verdict labels).** Bands are B3f's, read per repetition in step 10's window (cut at a DOWN of B, B3g last row). **Confirmed** = in both repetitions, stock Δ`netPoolUsed` ≤ 1 MiB, H = 1 MiB Δ`netPoolUsed` in [1, 3] MiB, the 256 MiB control's Δ`netPoolUsed` ≥ 0.8 × its max `pendingBytes`, and max `pendingBytes` ≥ 20 MiB in every stalled run. **Refuted** = stock Δ`netPoolUsed` ≥ 8 MiB in a repetition whose max `pendingBytes` ≥ 20 MiB, while the control moved. **Not confirmed** = `pendingBytes` < 20 MiB in a stalled run, or the control's Δ ≤ 3 MiB (positive control did not move), or any other miss of the bands that is not Refuted. `directUsed`, NMT and the return to baseline after CONT are secondary. Effect: Confirmed → `caps`.

- **S4-A4 (2026-11-25, second stage-4 session on `ms0640`, made in the audit review before any reading; B1, B2f, B3f and the rows of B2g/B3g are unchanged, and S4-A1 to S4-A3 stand).** (a) **Node:** the run is on `ms0640` (Utah m400, **aarch64**, 8 cores, 62 GiB, ≈17 GB free on `/mydata`), not `pc99`. Its `/mydata/s4/cassandra-base` is a full `build-test` copy (`src/`, `test/`, `build/test/`), and the 8 load-bearing files md5-match the repo's `systems/cassandra/source/`. No step is x86-specific: `lib/` carries Netty's native epoll for `linux-aarch_64`. (b) **Disk:** `$WORK/src` (unit tier) is deleted once the unit tier is done, before `$WORK/cass` is copied. A cluster run aborts as a runbook defect, with no reading used, if free space on `/mydata` drops below 3 GiB. (c) **Unit labels, catch-all:** S4-A2 is judged per repeat. A result that fits neither S4-A2's Confirmed definition (all 3 repeats) nor its Refuted definition is **Not confirmed**. (d) **Cluster workload remedy:** if B3g row 4 applies (`pendingBytes` < 20 MiB in a stalled run), the B3g hint "Raise `threads`" is a runbook-defect fix. The whole cluster tier then restarts with the new value. B3f and B3g are unchanged by it. (e) **Cleanup:** processes are stopped by PID file or by a pattern restricted to the run user.
- **S4-D1 (2026-11-25, runbook-defect fix, B2e step 3; B2f/B2g unchanged).** `grep '^FHWM'` finds no data rows: the test's `System.out.printf` reaches the `ant` log through Cassandra's `SubstituteLogger` one write at a time, so each row is split over about 22 log lines ("FHWM,", "16384", ",", "8192", …). Fix: rejoin the tokens after each "FHWM," marker (`harness/extract-rows.py`). The test itself is unchanged. The unit tier restarts from its beginning (three new repeats). The first three repeats were run before the fix; their rows were not read before the fix, and they are kept apart, superseded.
- **S4-D2 (2026-11-25, runbook-defect fix, B3a; B3f/B3g unchanged).** B3a says to replace "line 103" of `OutboundConnectionSettings.java`. At `cassandra-5.0.9` line 103 is the `{` of the constructor, and the call with the literals `1 << 15, 1 << 16` is **line 104** (A1's citation `:103` is off by one in the same way). The setup script stopped there ("line 103 unexpected"). Fix: replace the one line that holds the stock call, line 104, with B3a's patch text, unchanged. Nothing of the cluster tier had run, so the cluster tier starts from its beginning.
- **S4-D3 (2026-11-25, runbook-defect fix, B3e step 2; B3f/B3g unchanged).** B3e step 2 starts B, waits 30 s, then starts A. A (127.0.0.1) is the only seed, so B came up with no seed to reach. When A appeared, B logged "Didn't receive schemas for all known versions within the PT30S" and exited during start-up (first stock run, `runs/s1-stock-defect3/`). The m400 was also slow: B logged a 41 s local pause. Fix: start A first and wait until it is `UN` with `statusbinary` = `running`. Then start B and wait until both nodes are `UN` and both run the binary protocol. A node that dies while waiting stops the run. The node settings, `$MARKS` (on A only), the workload and the timing after start-up are unchanged. No workload had started, so there is no reading. The cluster tier restarts from its beginning.
- **S4-D4 (2026-11-25, harness-defect fix, B3e step 9; B3f/B3g unchanged).** The second run (`s1-1m`) stopped at the port check, before any node started: `127.0.0.1:7199` was still listening for a moment after the previous run's node had left the process list. Fix: the run script waits up to 90 s for the ports to close, both at the end of a run and before the next one. The cluster tier restarts from its beginning. The one complete run made before the fix (`s1-stock`) is kept apart as superseded and is not used for the verdict.
- **S4-D5 (2026-11-25, runbook-defect fix, B3e step 5; B3f/B3g and step 10's window and baseline unchanged).** On the loaded m400 (two nodes and stress on 8 cores, node A running back-to-back G1 old-generation collections), the sampler started at t = 20 s as a single-file source launch (`java Sampler.java`) gave its first sample only at the STOP (s1-stock +0.0 s, s1-1m +0.6 s). Step 10's 10 s baseline before the STOP was therefore empty in both runs. Fix: `Sampler.java` is compiled once with `javac` (unchanged source), started with `java -cp` at t = 5 s, and takes 210 samples, so it covers t = 5–110 s as the filed 180 samples from t = 20 s covered t = 20–110 s. A run stops (exit 3) if its first sample is later than STOP − 10 s. The two runs made with the late sampler (`s1-stock`, `s1-1m`) and the interrupted `s1-256m` are kept apart as superseded and not used. The cluster tier restarts from its beginning.

**Stage-4 result (2026-11-25, run on `ms0640`, aarch64; results: `~/writeup-ext/out/o125/results.md`).** **Unit tier: Confirmed — caps** (B2g row 1, 3/3 repeats). `flushingBytes` was 50 862–63 318, 83 120, 277 413–291 959 and 1 067 053–1 077 443 B for H = 16 KiB, 64 KiB, 256 KiB and 1 MiB, with `isWritable = 0`. The 8 MiB control held the whole W = 3 191 808 B with `isWritable = 1`. **Cluster tier: Not confirmed — undetermined** (B3g row 5): the control's Δ`netPoolUsed` was −67.6 / −27.9 MiB, and the H = 1 MiB Δ was 0.311 / 0.461 MiB. Two things broke the tier. On the m400, B could not keep up even unstalled (45–47 MiB backlog before the STOP), so the mark already bound in the baseline. The networking `BufferPool` `UsedSize` metric went negative (to ≈ −2 GiB) after the pool overflowed, while `directUsed` rose to 204 MiB and NMT "Other" rose by 157 MB. The likely cause is an overflow accounting bug, a double subtraction through `putUnusedPortion` (`BufferPool.java:877-886`) followed by `put`. **Outcome class: weak true positive.** A1's citation `OutboundConnectionSettings.java:103` should read `:104`.
