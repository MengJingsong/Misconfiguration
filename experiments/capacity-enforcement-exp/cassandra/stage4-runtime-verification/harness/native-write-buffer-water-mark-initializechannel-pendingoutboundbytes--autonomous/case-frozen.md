# Native-transport write-buffer high water mark (32 KiB): verification solution  <!-- file: cases/native-write-buffer-water-mark-initializechannel-pendingoutboundbytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (a capacity-set place), **linked**: [`PipelineConfigurator.java:139`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L139): `.childOption(ChannelOption.WRITE_BUFFER_WATER_MARK, new WriteBufferWaterMark(8 * 1024, 32 * 1024));` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `negative`. The 8 KiB/32 KiB water mark only switches Netty's `Channel.isWritable()` flag. No code on the CQL native-transport path reads that flag or the writability event. Cassandra hands each response to Netty and releases its own accounting at once, so when a client stops reading, a connection's queued response bytes grow with no limit and pass 32 KiB. |
| Ground | Netty's `ChannelOutboundBuffer.addMessage` always queues the message. Going over the high mark only calls `setUnwritable` and fires `channelWritabilityChanged`, and enforcing it is left to the application. In `src/java/org/apache/cassandra/transport/` the only mention of writability or the water mark is line 139 itself. `Flusher` writes and flushes without checking writability (`Flusher.java:145`, `:205`) and then releases the request-side reserves (`Flusher.java:249-250`). The only per-connection read pause on the native path follows inbound request bytes and rate limits (`PreV5Handlers.java:200-237`), not outbound bytes. So the water mark is a signal that nothing consumes, and it does not cap memory. |

## A. Constraint trace

**A1. The constraint.**
- *Name:* the native-transport (CQL client) channel write-buffer water mark, with low = 8 KiB and high = 32 KiB. It has no configuration name.
- *Kind:* constant, hard-coded in the code that builds the server bootstrap.
- *Declaration (where first declared):* [`PipelineConfigurator.java:139`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L139). Inside `initializeChannel` (`PipelineConfigurator.java:128-150`) it is set as a **child option**, so every accepted client channel carries it from creation. Both the pre-v5 pipeline and the v5 pipeline inherit it. `configureModernPipeline` changes only the allocator (`PipelineConfigurator.java:282-283`), not the water mark.
- *Unit:* bytes of pending outbound data per channel, as counted by Netty's `ChannelOutboundBuffer`.
- *Default and how it is derived:* the literals `8 * 1024` and `32 * 1024`. There is no derivation and no configuration lookup.
- *How it can be set:* it cannot be set. There is no yaml key, no `-D` property and no JMX attribute. The only ways to change it are a code change or a test subclass that resets `channel.config().setWriteBufferWaterMark(...)` (this is how B2 varies it). A change would need a restart.

**A2. What it caps.**
- *Nominal resource:* off-heap (direct) memory that holds response bytes queued on a client channel but not yet written to the socket. In v4 the response bodies come from `CBUtil.allocator`, a `PooledByteBufAllocator(true)` that is direct unless `-Dcassandra.netty_use_heap_allocator=true` (`CBUtil.java:59-60`, `Message.java:367`). Headers and bodies are passed down the pipeline as `ByteBuf`s by `Envelope.Encoder.encode` (`Envelope.java:503-512`). In v5 the framed payloads come from `BufferPools.forNetworking()` (`net/FrameEncoder.java:32`).
- *Quantity compared against the limit:* Netty's `ChannelOutboundBuffer.totalPendingSize`, the sum of the estimated sizes of the queued, unflushed and unwritten messages. Netty compares it against `getWriteBufferHighWaterMark()` in `incrementPendingOutboundBytes`. That comparison is in the Netty jar, not the Cassandra tree. It is read with `totalPendingWriteBytes()` and `Channel.bytesBeforeUnwritable()`.

**A3. Mechanism.**
1. The constraint is set on every accepted native-transport channel at [`PipelineConfigurator.java:139`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L139). The bootstrap is bound at `PipelineConfigurator.java:149`, and `Server.start` calls it (`Server.java:141`).
2. A request is decoded and passed to `Dispatcher.dispatch` (`PreV5Handlers.java:87` for v4, `CQLMessageHandler.java:391` for v5). It runs on the request executor (`Dispatcher.java:125`), and its response is wrapped in a `FlushItem` and queued on the event loop's `Flusher` (`Dispatcher.java:467-480`).
3. `Flusher.processUnframedResponse` calls `channel.write(...)` (v4, `Flusher.java:145`). `FlushBuffer.finish` and `flushLargeMessage` call `channel.writeAndFlush(...)` (v5, `Flusher.java:197`, `:205`, `:305`, `:313`). **No writability check is made before any of these writes.**
4. Inside Netty, each write goes to `ChannelOutboundBuffer.addMessage`, which queues it unconditionally and raises `totalPendingSize`. The check is in `incrementPendingOutboundBytes`: `if (newWriteBufferSize > channel.config().getWriteBufferHighWaterMark()) setUnwritable(...)` (Netty, see A5).
   - *Outcome when pending > 32 KiB:* `isWritable()` becomes `false` and `channelWritabilityChanged` is fired down the pipeline. **No Cassandra native-transport handler acts on either.** A search of `src/java/org/apache/cassandra/transport/` for `writab`/`waterMark` finds only line 139. `LegacyDispatchHandler` (`PreV5Handlers.java:56`) and `CQLMessageHandler`/`AbstractMessageHandler` do not override `channelWritabilityChanged`. The write is queued anyway.
   - *Outcome when pending < 8 KiB:* writability returns to `true`. Nothing in Cassandra consumes this either.
5. Right after the write and flush, `Flusher.flushWrittenChannels` releases every processed item (`Flusher.java:249-250`). That returns the request's bytes to the per-endpoint and global in-flight reserves (`PreV5Handlers.java:99-110`, `CQLMessageHandler.java:500-504`). It can also re-enable `autoRead` (`PreV5Handlers.java:112+`). The server therefore keeps reading requests from a client that has stopped reading responses.
- *Bypass or overshoot:* every write overshoots, because the cap is never enforced. Pending bytes are bounded only by how many requests the client sends times the response size. In the end that bound is Netty's direct-memory limit (`OutOfDirectMemoryError`) or the JVM's `MaxDirectMemorySize`. The optional idle timeout (`native_transport_idle_timeout`, default `0ms` = off, `Config.java:139`; handler at `PipelineConfigurator.java:247-258`) closes only *idle* connections, and a client that keeps sending requests is not idle.

**A4. Other consumers.**
- The same off-heap memory is also used by the following, none of which this water mark governs:
  - inbound request buffers, bounded by `native_transport_receive_queue_capacity` (default 1 MiB, `Config.java:302`) and by `native_transport_max_request_data_in_flight[_per_ip]` (default heap/10 and heap/40, `DatabaseDescriptor.java:649-656`). These count *request* bytes and are released at flush, so they do not bound response bytes.
  - the chunk cache and `BufferPool`, including the networking pool used by v5 framing.
  - internode messaging. `OutboundConnection` and `AsyncMessageOutputPlus` do read their own channel's water mark (`net/AsyncMessageOutputPlus.java:69-71`, `net/OutboundConnection.java:857-873`), but that is a different channel type with its own setting.
  - off-heap memtables, if configured.
- Outside the JVM, kernel socket buffers (`SO_SNDBUF` on the server side, `SO_RCVBUF` on the client side) also hold response bytes.

**A5. Evidence beyond the source.**
- Netty `ChannelOutboundBuffer` (4.1 branch): `addMessage` always appends, `incrementPendingOutboundBytes` only calls `setUnwritable` above the high mark, `totalPendingWriteBytes()` returns `totalPendingSize`, and `bytesBeforeUnwritable()` = high − pending + 1. Source: https://github.com/netty/netty/blob/4.1/transport/src/main/java/io/netty/channel/ChannelOutboundBuffer.java (read through raw.githubusercontent.com; the pinned Netty version is `4.1.130.Final` per `.build/parent-pom-template.xml:748-749`).
- Netty `WriteBufferWaterMark` javadoc: the high mark makes `Channel.isWritable()` return false; it is advisory. https://netty.io/4.1/api/io/netty/channel/WriteBufferWaterMark.html
- `CHANGES.txt` and `NEWS.txt` have no entry about this water mark (searched for "water mark", "watermark" and "writability"). The git history was not available in the copy.

## B. Verification solution

**B1. Claim under test.** On a native-transport (CQL v4) connection whose client stops reading, the server-side queued response bytes (`ChannelOutboundBuffer.totalPendingWriteBytes()`) and the matching off-heap memory grow in proportion to (requests sent × response size), far past the 32 KiB high water mark. Changing the high mark leaves them unchanged. The claim is refuted if the queued bytes level off near 32 KiB plus a few responses, independent of the number of requests.

### B2. Unit tier

The unit tier runs an in-process `Server` started by `CQLTester` inside the test JVM. There is no separately running node. A raw-socket v4 client talks to the server. The operand is read directly from the server-side child channel.

**B2a. Environment and build.**
- Linux, JDK 11, Ant.
- Copy the tree to local disk, never building in a shared tree: `rsync -a ~/cassandra-5.0.9/ /mydata/$USER-s4/wm-unit/ && cd /mydata/$USER-s4/wm-unit`
- Add the test file `test/unit/org/apache/cassandra/transport/WriteWaterMarkBacklogTest.java` (below).
- Build with `ant jar build-test`.
- JVM: the test JVM `-Xmx` comes from `build.xml:1245-1255` (4G or 8G). Pass the knobs through `-Dtest.jvm.args` (`build.xml:1192`).

> **Amendment S4-A1 (2026-11-25, stage-4 audit, before any reading; runbook only).** On the stage-4 node the tree is a copy of
> the built `/mydata/s4/cassandra-base` (`cp -a` to `/mydata/jingsong-cass-s4/o133/c509`, md5-checked against the repository's
> `systems/cassandra/source`), not an rsync of `~/cassandra-5.0.9`; `ant build-test` after adding the test file. Run data and
> logs under `/mydata/jingsong-cass-s4/o133/`. The test's result line also echoes the channel's configured marks
> (`cfgHigh`, `cfgLow`), the gate mode, `autoRead`, `open`, the stable-sample count and the pipeline handler names, and is printed
> to stdout and stderr (both land in the junit XML). Each B2e cell is one `ant testsome` JVM run from a logged script.

```java
package org.apache.cassandra.transport;

import java.io.*;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.BeforeClass;
import org.junit.Test;

import io.netty.channel.*;
import org.apache.cassandra.config.EncryptionOptions;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.metrics.ClientMessageSizeMetrics;

public class WriteWaterMarkBacklogTest extends CQLTester
{
    static final List<Channel> CHANNELS = new CopyOnWriteArrayList<>();
    static int HIGH;  static boolean GATE;  static int SNDBUF;

    static class ProbeConfigurator extends PipelineConfigurator
    {
        ProbeConfigurator() { super(false, false, false, EncryptionOptions.TlsEncryptionPolicy.UNENCRYPTED); }

        @Override
        protected void onInitialPipelineReady(ChannelPipeline p)
        {
            Channel ch = p.channel();
            ch.config().setOption(ChannelOption.SO_SNDBUF, SNDBUF);            // shrink kernel slack
            if (HIGH != 32 * 1024)                                              // knob: vary the constraint
                ch.config().setWriteBufferWaterMark(new WriteBufferWaterMark(HIGH / 4, HIGH));
            if (GATE)                                                           // positive control: a consumer of writability
                p.addFirst("wm-gate", new ChannelDuplexHandler()
                {
                    boolean held;
                    @Override public void read(ChannelHandlerContext ctx)
                    { if (ctx.channel().isWritable()) ctx.read(); else held = true; }
                    @Override public void channelWritabilityChanged(ChannelHandlerContext ctx)
                    { if (ctx.channel().isWritable() && held) { held = false; ctx.read(); } ctx.fireChannelWritabilityChanged(); }
                });
            CHANNELS.add(ch);
        }
    }

    @BeforeClass
    public static void setUpNet()
    {
        HIGH = Integer.getInteger("wm.high", 32 * 1024);
        GATE = Boolean.getBoolean("wm.gate");
        SNDBUF = Integer.getInteger("wm.sndbuf", 16 * 1024);
        requireNetwork(b -> b.withPipelineConfigurator(new ProbeConfigurator()), c -> {});
    }

    static byte[] frame(int stream, int op, byte[] body)
    {
        ByteBuffer b = ByteBuffer.allocate(9 + body.length);
        b.put((byte) 0x04).put((byte) 0).putShort((short) stream).put((byte) op).putInt(body.length).put(body);
        return b.array();
    }
    static void str(DataOutputStream d, String s) throws IOException
    { byte[] x = s.getBytes(StandardCharsets.UTF_8); d.writeShort(x.length); d.write(x); }
    static byte[] startup() throws IOException
    { ByteArrayOutputStream o = new ByteArrayOutputStream(); DataOutputStream d = new DataOutputStream(o);
      d.writeShort(1); str(d, "CQL_VERSION"); str(d, "3.0.0"); return o.toByteArray(); }
    static byte[] query(String q) throws IOException
    { ByteArrayOutputStream o = new ByteArrayOutputStream(); DataOutputStream d = new DataOutputStream(o);
      byte[] x = q.getBytes(StandardCharsets.UTF_8); d.writeInt(x.length); d.write(x); d.writeShort(1); d.writeByte(0);
      return o.toByteArray(); }
    static int readFrame(DataInputStream in) throws IOException   // returns total bytes of one frame
    { byte[] h = new byte[9]; in.readFully(h); int len = ByteBuffer.wrap(h, 5, 4).getInt();
      in.readFully(new byte[len]); return 9 + len; }

    @Test
    public void backlog() throws Throwable
    {
        int B = Integer.getInteger("wm.blob", 64 * 1024);
        int K = Integer.getInteger("wm.k", 256);
        boolean clientReads = Boolean.getBoolean("wm.clientReads");
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob)");
        execute("INSERT INTO %s (k, v) VALUES (0, ?)", ByteBuffer.allocate(B));
        String q = formatQuery("SELECT v FROM %s WHERE k = 0");

        try (Socket s = new Socket())
        {
            s.setReceiveBufferSize(4096);
            s.connect(new InetSocketAddress(nativeAddr, nativePort));
            OutputStream out = s.getOutputStream();
            DataInputStream in = new DataInputStream(new BufferedInputStream(s.getInputStream()));
            out.write(frame(0, 0x01, startup())); out.flush();
            readFrame(in);                                             // READY
            Channel ch = CHANNELS.stream()
                                 .filter(c -> ((InetSocketAddress) c.remoteAddress()).getPort() == s.getLocalPort())
                                 .findFirst().get();
            AtomicLong clientBytes = new AtomicLong();
            Thread reader = null;
            if (clientReads)
            {
                reader = new Thread(() -> { try { for (int i = 0; i < K; i++) clientBytes.addAndGet(readFrame(in)); } catch (IOException e) {} });
                reader.start();
            }
            long sent0 = ClientMessageSizeMetrics.bytesSent.getCount();
            long max = 0;
            for (int i = 0; i < K; i++)
            {
                out.write(frame(i % 32768, 0x07, query(q))); out.flush();
                Thread.sleep(10);                                       // 100 requests/s trickle
                max = Math.max(max, pending(ch));
            }
            long last = -1; int stable = 0; long deadline = System.currentTimeMillis() + 30_000;
            while (stable < 20 && System.currentTimeMillis() < deadline)  // settle: 20 equal samples 100 ms apart
            {
                Thread.sleep(100);
                long p = pending(ch); max = Math.max(max, p);
                stable = (p == last) ? stable + 1 : 0; last = p;
            }
            long produced = ClientMessageSizeMetrics.bytesSent.getCount() - sent0;
            System.out.printf("WMRESULT high=%d gate=%b sndbuf=%d B=%d K=%d clientReads=%b produced=%d R=%d " +
                              "pendingMax=%d pendingSettled=%d writable=%b bytesBeforeUnwritable=%d clientBytes=%d%n",
                              HIGH, GATE, SNDBUF, B, K, clientReads, produced, K == 0 ? 0 : produced / K,
                              max, last, ch.isWritable(), ch.bytesBeforeUnwritable(), clientBytes.get());
            if (reader != null) reader.join(30_000);
        }
    }

    static long pending(Channel ch)
    {
        ChannelOutboundBuffer b = ch.unsafe().outboundBuffer();
        return b == null ? -1 : b.totalPendingWriteBytes();
    }
}
```

Notes on the test code:
- In the gate variant, `produced` counts only the responses actually produced.

> **Amendment S4-A2 (2026-11-25, stage-4 audit, before any reading; control instrument only, B2f/B2g unchanged).** The gate
> as filed cannot pause reading: the server channel runs with `autoRead` on (Netty default; Cassandra turns it off only in
> `PreV5Handlers.java:224`), and Netty 4.1.130's NIO read loop (`AbstractNioByteChannel$NioByteUnsafe.read`, bytecode checked on
> the node) removes `OP_READ` only when `autoRead` is off, so reads continue without ever passing through a handler's `read()`.
> The positive-control gate is therefore a first-position inbound handler that sets `autoRead` to `isWritable()` on every
> `channelWritabilityChanged` (`-Dwm.gate=autoread`), which is the standard Netty consumer of writability. The as-filed gate
> (`-Dwm.gate=true`) is run once as a labelled diagnostic (B65536, K256); its reading is not used for the verdict.
>
> **Fix D1 (2026-11-25, runbook defect from the K = 8 shakedown, before any sweep reading; B2f/B2g unchanged).** The test's
> `ProbeConfigurator` passed `epoll = false`, so on a Linux node where `CQLTester`'s `Server` uses an `EpollEventLoopGroup`
> the NIO server channel fails to register (`IllegalStateException: incompatible event loop type`, "Failed to bind port").
> The configurator now passes `NativeTransportService.useEpoll()`, as `Server` does (`Server.java:107`). Epoll keeps the same
> read semantics S4-A2 relies on (`AbstractEpollChannel` clears `EPOLLIN` only when `autoRead` is off; bytecode checked).
> The result line reaches the `ant` console log, not the junit XML; the harness collects it from there.
- `bytesSent` is incremented in `Envelope.Encoder.encode` (`Envelope.java:507`), so `produced/K` is the exact response size R, header included.

**B2b. Knobs.**

| Knob | Values | Why | How set |
|---|---|---|---|
| High water mark (the constraint) | 32768 (stock), 1048576, 67108864 | If the mark capped memory, pending bytes would follow it. 64 MiB is above every backlog in the grid, so the channel never becomes unwritable. | `-Dwm.high=` (test-only reset in `onInitialPipelineReady`; the low mark is high/4, so 8 KiB at the stock value) |
| Response size B (blob bytes) | 16384, 65536, 262144 | Pending bytes should scale with R ≈ B + ~60 | `-Dwm.blob=` |
| Request count K | 64, 256 | Pending bytes should scale with K | `-Dwm.k=` |
| Client reads | false (main), true (control) | Separates "the client stopped reading" from any server-side leak | `-Dwm.clientReads=` |
| Gate | false (stock), true (positive control) | The same water mark with a consumer of `isWritable()` | `-Dwm.gate=` |

`wm.sndbuf` stays at 16384 for every run. Linux doubles it, giving about 32 KiB of kernel slack.

**B2c. Workload.**
- After STARTUP, the client sends K `SELECT v FROM ks.t WHERE k=0` queries (each ~60 bytes) at 100/s and never reads.
- Each response is R ≈ B + 60 bytes (9-byte header, rows metadata, row count, 4-byte value length, B).
- Bytes produced = K·R:
  - largest cell: K=256, B=256 KiB → about 64 MiB, well inside the 4 GiB heap and default direct limit;
  - smallest: K=64, B=16 KiB → about 1 MiB.
- The kernel can absorb at most about 32 KiB (server `SO_SNDBUF` doubled) + about 8 KiB (client `SO_RCVBUF`, minimum doubled) + a little loopback. So the operand passes 32 KiB after the first response in every cell. For example, at B=16 KiB, 3 responses exceed the about 40 KiB kernel slack plus the 32 KiB mark.

**B2d. Observables and instruments.**
- `pendingSettled` and `pendingMax`: the value of `ChannelOutboundBuffer.totalPendingWriteBytes()` on the server child channel, which is the operand. It is sampled in the test thread after every request and then every 100 ms until it is stable. The field is volatile, so it is safe to read from another thread.
- `writable` and `bytesBeforeUnwritable`: show whether the water mark is in force on the channel.
- `produced`: the `ClientMessageSize.BytesSent` delta, giving K·R exactly.
- `clientBytes`: bytes the client read (only when it reads).
- *Not observed directly:* the bytes held in kernel socket buffers (inferred as `produced − pendingSettled − clientBytes`), and the pooled-arena memory behind the buffers. Pooled memory is measured in the cluster tier instead.

**B2e. Procedure.** From `/mydata/$USER-s4/wm-unit`:
1. `ant jar build-test`
2. For each (high, B, K) in {32768, 1048576, 67108864} × {16384, 65536, 262144} × {64, 256}, with gate=false and clientReads=false:
   `ant testsome -Dtest.name=org.apache.cassandra.transport.WriteWaterMarkBacklogTest -Dtest.jvm.args="-Dwm.high=$H -Dwm.blob=$B -Dwm.k=$K"`
   Collect the `WMRESULT` line from `build/test/output/TEST-org.apache.cassandra.transport.WriteWaterMarkBacklogTest.xml` (or from the console log).
3. Control (client reads): high=32768, B=65536, K=256, `-Dwm.clientReads=true`.
4. Positive control (gate): high=32768, B ∈ {65536, 262144}, K=256, `-Dwm.gate=true`.
5. Repeat step 2 at (32768, 65536, 256) three times to measure noise.
6. Run `pgrep -f WriteWaterMarkBacklogTest` and confirm that no test JVM is left. Then run `rm -rf build/test/cassandra` to remove the in-process data.

**B2f. Predictions.** R = `produced/K` ≈ B + 60.

| Run | pendingSettled | writable / bytesBeforeUnwritable |
|---|---|---|
| Stock (high=32 KiB), any B, K | between K·R − 64 KiB and K·R. For example, B=64 KiB, K=256: ≈ 16.0 MiB (≥ 16,770,000 bytes). B=256 KiB, K=256: ≈ 64 MiB. B=16 KiB, K=64: ≈ 1.0 MiB. | false / 0 |
| high=1 MiB | same as stock, within ±64 KiB for the same (B, K) | false if K·R > 1 MiB + slack, else true |
| high=64 MiB | same as stock, within ±64 KiB | true; bytesBeforeUnwritable = 64 MiB − pending + 1 |
| Stock vs. B and K | pendingSettled roughly doubles from K=64 to K=256 (×4), and from B=16 KiB to 64 KiB to 256 KiB (×4 each), linear in K·R | |
| Client reads | ≤ 64 KiB (normally ≤ R) and clientBytes = produced | |
| Gate (positive control) | ≤ 32 KiB + 4·R. For example, B=64 KiB: ≤ ~300 KiB, which is ≤ 2% of the stock 16 MiB. produced < K·R while held. | |

> **Amendment S4-A3 (2026-11-25, stage-4 audit, before any reading; arithmetic, not data).** Netty counts each queued message as
> its readable bytes **plus a fixed 96-byte entry overhead** (`ChannelOutboundBuffer` `CHANNEL_OUTBOUND_BUFFER_ENTRY_OVERHEAD`,
> `io.netty.transport.outboundBufferEntrySizeOverhead`, default 96), and `Envelope.Encoder.encode` emits **two** messages per v4
> response (header and body, `Envelope.java:503-512`). So the stock band is
> **K·R − 64 KiB ≤ pendingSettled ≤ K·(R + 192)** (the upper end adds up to 48 KiB at K = 256), and the gate bound is
> ≤ 32 KiB + 4·(R + 192). At high = 64 MiB, the cell B = 256 KiB, K = 256 has K·(R + 192) ≈ 64.05 MiB > 64 MiB, so `writable`
> may read false there; the writable column is informational and no B2g row depends on it.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Stock pendingSettled ≈ K·R ≫ 32 KiB, `writable=false`, and the same pendingSettled at high = 32 KiB, 1 MiB and 64 MiB | The claim is confirmed: the water mark is in force as a flag but does not cap usage. |
| Stock pendingSettled ≤ 32 KiB + a few R and flat in K | The claim is refuted: something enforces the mark (usage follows the constraint). |
| pendingSettled changes with `wm.high` (for example ≈ high at each setting) | The claim is refuted: usage follows the knob. |
| Usage flat with respect to the mark, while the gate control keeps pending near 32 KiB + a few R and the client-reads control keeps it near 0 | The claim is confirmed: the same workload is bounded when a writability consumer exists, so the instrument and workload can show a binding cap. Without the consumer it is not bounded. |
| Stock pendingSettled small because K·R never passed the kernel slack (produced < 100 KiB), or the gate control did not reduce pending | Not confirmed: the limit was never reached, or the control failed. Increase K or B, or check that the gate handler is in the pipeline. |
| pendingSettled = −1 | The channel closed (for example an `OutOfDirectMemoryError` or an exception). Check the test log. Not confirmed. |

> **Amendment S4-A4 (2026-11-25, stage-4 audit, before any reading; thresholds and labels for the rows above, no row changed).**
> Let P(h, B, K) be pendingSettled. *Noise* n = max(64 KiB, 2 × the spread of the four stock (32768, 65536, 256) runs).
> - **Stock in band:** every stock cell inside the S4-A3 band, with `writable=false`.
> - **Flat in the mark:** for each (B, K), |P(1 MiB) − P(32 KiB)| ≤ n and |P(64 MiB) − P(32 KiB)| ≤ n.
> - **Follows the workload:** P(·, ·, 256) / P(·, ·, 64) ∈ [3.5, 4.5] at each B for the stock mark.
> - **Client-reads control holds:** P ≤ 64 KiB and clientBytes = produced. **Gate control holds:** P ≤ 32 KiB + 4·(R + 192),
>   P ≤ 2 % of the stock P for the same (B, K), and produced < K·R.
> - Row 1 / row 4 → **Confirmed — does not cap**: stock in band, flat in the mark, follows the workload, both controls hold.
> - Row 2 → **Refuted — caps**: stock P ≤ 32 KiB + 4·(R + 192) in a cell with K·R ≥ 1 MiB. Row 3 → **Refuted — caps**: P(1 MiB)
>   ≤ 1 MiB + 4·(R + 192) in a cell where P(32 KiB) > 2 MiB, or P(32 KiB) ≤ 32 KiB + 4·(R + 192) while P(64 MiB) is in band.
> - Row 5 / row 6 → **Not confirmed**: produced < 100 KiB in a stock cell, a control fails, or P = −1 / `open=false`. Any other
>   pattern (for example flat in the mark but outside the band) → **Not confirmed**, with the reason.

**B2h. Controls.**
- The client-reads run shows that the backlog comes from the client not reading, not from a leak.
- The gate run shows that the same mark binds when consumed, which proves the workload can reveal a cap.
- `produced` checks that K responses of size R were actually produced.
- Fixed `SO_SNDBUF` bounds the kernel's share.
- Varying the mark itself (32 KiB to 64 MiB) separates "a flag in force" from "usage follows the flag".
- Three repeats measure noise.

### B3. Cluster tier

The cluster tier uses one real node, because the constraint is per connection and does not involve other nodes. The actual off-heap memory is measured while a raw v4 client stops reading.

**B3a. Environment and build.**
- Linux node with at least 4 GiB of free RAM, JDK 11, Ant, Python 3 (standard library only).
- Prepare the copy:
  ```
  rsync -a ~/cassandra-5.0.9/ /mydata/$USER-s4/wm-node/
  cd /mydata/$USER-s4/wm-node && ant jar
  ```
  The data, commitlog, hints and saved caches default to `$CASSANDRA_HOME/data/`, on local disk.
- To avoid clashing with other users on the host, make these changes in the copied `conf/cassandra.yaml`:
  - `native_transport_port: 19142`
  - `storage_port: 17100`
  - `ssl_storage_port: 17101`
  - seeds `"127.0.0.1:17100"`
  - `listen_address: 127.0.0.1`
  - `rpc_address: 127.0.0.1`
- In the copied `conf/cassandra-env.sh`, set `JMX_PORT="17199"`.
- JVM settings:
  ```
  export MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M
  export JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=1G"
  ```
  JDK 11 records `Unsafe.allocateMemory`, which backs Netty's direct pooled arenas, under NMT "Other".
- Leave the defaults `-Dio.netty.allocator.maxOrder=11` and `useCacheForAllThreads=true` (`conf/jvm11-server.options:141-145`). With them, pooled arenas grow in chunks of 8 KiB × 2^11 = 16 MiB.

**B3b. Knobs.**
- The water mark itself is **n/a in this tier**: it is hard-coded and not settable without patching (B2 varies it).
- What is varied:

| Knob | Values | Why | How set |
|---|---|---|---|
| Requests K | 64, 256 | Usage should scale with K | client `--k` |
| Response size, through page size P (rows of 1 KiB) | unpaged (1024 rows, R ≈ 1.00 MiB), P=64 (R ≈ 64.4 KiB) | **Positive control:** page size is a cap known to bind on each response's size, so the same workload with P=64 must cut usage about 16 times | client `--page` (QUERY flag 0x04) |
| Client reads | no (main), yes (control) | Separates backlog from leak | client `--mode flood` / `read` |

**B3c. Workload.**
- *Data:* keyspace `wm`, table `wm.t (k int, c int, v blob, PRIMARY KEY (k, c))`, partition k=0 with 1024 rows, each holding a 1024-byte blob.
- *Load:* `SELECT v FROM wm.t WHERE k=0`, sent at 100/s, K times, over a v4 connection with the client's `SO_RCVBUF`=4096, never read.
- *Response size:* each row is 4 + 1024 = 1028 bytes, so unpaged R ≈ 1,052,700 bytes and P=64 gives R ≈ 65,900 bytes.
- *Produced K·R:* 64 MiB (K=64, unpaged), 257 MiB (K=256, unpaged), 16 MiB (K=256, P=64). All are below `MaxDirectMemorySize=1G`, and all are ≫ 32 KiB and ≫ the kernel slack. The kernel slack is the server send buffer, autotuned up to `net.ipv4.tcp_wmem` max (read it; typically 4 MiB), plus the client receive buffer of about 8 KiB.
- *Duration:* K/100 s of sending plus a 60 s hold, then a drain.

Client `wm_client.py` (kept outside the source tree, for example in `/mydata/$USER-s4/wm-tools/`):

```python
import socket, struct, sys, time, argparse, threading
p = argparse.ArgumentParser()
p.add_argument('--port', type=int, default=19142); p.add_argument('--mode', choices=['insert','flood','read'])
p.add_argument('--k', type=int, default=256); p.add_argument('--page', type=int, default=0)
p.add_argument('--hold', type=int, default=60); a = p.parse_args()
def s(x): b = x.encode(); return struct.pack('>H', len(b)) + b
def frame(st, op, body): return struct.pack('>BBhBi', 4, 0, st, op, len(body)) + body
def q(text, page=0):
    b = text.encode(); body = struct.pack('>i', len(b)) + b + struct.pack('>H', 1)
    return body + (b'\x04' + struct.pack('>i', page) if page else b'\x00')
def rd(sock, n):
    out = b''
    while len(out) < n:
        c = sock.recv(n - len(out))
        if not c: raise EOFError
        out += c
    return out
def read_frame(sock):
    h = rd(sock, 9); op = h[4]; n = struct.unpack('>i', h[5:9])[0]; body = rd(sock, n)
    if op == 0: raise RuntimeError('ERROR frame: %r' % body[:200])
    return 9 + n
sock = socket.socket(); sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
sock.connect(('127.0.0.1', a.port)); sock.sendall(frame(0, 1, struct.pack('>H', 1) + s('CQL_VERSION') + s('3.0.0'))); read_frame(sock)
print('local port', sock.getsockname()[1], flush=True)
SEL = 'SELECT v FROM wm.t WHERE k=0'
if a.mode == 'insert':
    for st in ["CREATE KEYSPACE IF NOT EXISTS wm WITH replication={'class':'SimpleStrategy','replication_factor':1}",
               "CREATE TABLE IF NOT EXISTS wm.t (k int, c int, v blob, PRIMARY KEY (k, c))"]:
        sock.sendall(frame(1, 7, q(st))); read_frame(sock)
    for c in range(1024):
        sock.sendall(frame(1, 7, q('INSERT INTO wm.t (k,c,v) VALUES (0,%d,0x%s)' % (c, 'ab' * 1024)))); read_frame(sock)
    print('inserted'); sys.exit(0)
got = [0]
if a.mode == 'read':
    t = threading.Thread(target=lambda: [got.__setitem__(0, got[0] + read_frame(sock)) for _ in range(a.k)]); t.start()
for i in range(a.k):
    sock.sendall(frame(i % 32768, 7, q(SEL, a.page))); time.sleep(0.01)
print('sent', a.k, 'at', time.time(), flush=True)
if a.mode == 'read':
    t.join(); print('read bytes', got[0]); sys.exit(0)
time.sleep(a.hold)                                 # operator samples during this window
print('draining at', time.time(), flush=True)
for _ in range(a.k): got[0] += read_frame(sock)
print('drained bytes', got[0], 'R', got[0] // a.k)
```

**B3d. Observables and instruments.** Sample every 2 s from before the flood until 10 s after the drain:
- *Actual off-heap memory (main measure):* `jcmd $PID VM.native_memory summary`, the line `- Other (reserved=…, committed=…)`. Take its committed value. Also run `jcmd $PID VM.native_memory baseline` once before the flood and `summary.diff` at the end of the hold.
- *Process RSS:* `grep VmRSS /proc/$PID/status`.
- *Heap control:* `jcmd $PID GC.heap_info`, to check that the backlog is not on the heap.
- *Kernel share:* `ss -tmn 'sport = :19142'` gives Send-Q on the server socket, and `ss -tmn 'dport = :19142'` gives Recv-Q on the client socket.
- *Bytes produced:*
  ```
  bin/nodetool -p 17199 sjk mx -mg -b "org.apache.cassandra.metrics:type=ClientMessageSize,name=BytesSent" -f Count
  ```
  Read it before the flood and after the drain. The client's `drained bytes` must equal the delta.
- *Derived server user-space backlog during the hold:* `produced − SendQ_server − RecvQ_client`.
- *Not observable directly:* the per-channel `totalPendingWriteBytes` (no JMX); B2 measures it. Pooled arenas also keep chunks after release, so NMT "Other" may not fall back after the drain. Only the rise during the hold is evidence.

**B3e. Procedure.**
1. Start the node and record its PID:
   `cd /mydata/$USER-s4/wm-node && bin/cassandra -p /mydata/$USER-s4/wm-node/pid > /mydata/$USER-s4/wm-node/out.log 2>&1`
   Wait until `bin/nodetool -p 17199 status` shows `UN`. Then `PID=$(cat pid)`.
2. Load the data with `python3 /mydata/$USER-s4/wm-tools/wm_client.py --mode insert`, then flush it with `bin/nodetool -p 17199 flush wm`.
3. Warm up (control) with `python3 wm_client.py --mode read --k 256`. This fills caches and pools. Wait 30 s.
4. Read the baselines: NMT baseline, Other committed, RSS, BytesSent.
5. Run cell A: `python3 wm_client.py --mode flood --k 64 --hold 60`. Start a 2 s sampling loop (NMT summary, RSS, ss, heap_info) and write it to `samples-A.txt`. At the end of the hold (before `draining`), record `summary.diff`. After the client exits, record BytesSent.
6. Cell B: as step 5 with `--k 256`.
7. Cell C (positive control, page size): as step 5 with `--k 256 --page 64`.
8. Cell D (client reads): `--mode read --k 256`, sampled the same way.
9. Repeat cell B once to check repeatability.
10. Stop the node with `kill $(cat pid)`. Wait, then confirm with `pgrep -f CassandraDaemon -u $USER` (expect nothing) and `pgrep -f wm_client.py` (expect nothing). Remove `data/` and `logs/` in the copy.

> **Amendment S4-A5 (2026-11-25, stage-4 audit, before any reading; runbook and definitions, B3f unchanged).** Paths: the node
> runs from the same built copy `/mydata/jingsong-cass-s4/o133/c509` (no rebuild; the unit-tier test class does not touch
> `conf/`), tools in `/mydata/jingsong-cass-s4/o133/harness/`, `ulimit -n 100000`, `MAX_HEAP_SIZE`/`HEAP_NEWSIZE`/`JVM_EXTRA_OPTS`
> scoped to the `bin/cassandra` command only. Each cell is driven by `cluster-cell.sh`, which logs every command and adds: a
> `GC.run` + `GC.heap_info` and an NMT `baseline` just before the cell's client starts; `BytesSent` read **also at the end of the
> hold** (before `draining`), so B3g row 2's "produced ≪ K·R until the drain" is observable; `ss` read with `-tmn` on both ends;
> `GC.run` + `GC.heap_info` and `summary.diff` at the end of the hold. **ΔOther of a cell** = NMT "Other" committed in the last
> sample before `draining` minus the value in the sample just before the cell's client started (pooled chunks freed by the
> previous cell's drain are not counted against the next cell). **Backlog** = BytesSent at end of hold − its pre-cell value −
> server Send-Q − client Recv-Q (last sample before `draining`). Thresholds: row 1 holds if ΔOther(A) ≥ 48 MiB, ΔOther(B) ≥
> 200 MiB, backlog(B)/backlog(A) ∈ [3, 5] and ΔOther(B)/ΔOther(A) ∈ [2.5, 6]; the control row (row 3) holds if ΔOther(C) ≤
> ΔOther(B)/7 and ΔOther(D) ≤ 32 MiB; row 2 needs backlog(A) and backlog(B) ≤ 1 MiB + 32 KiB, or produced at end of hold < 25 %
> of K·R with no ERROR frame; row 4 (instrument blind) is taken when backlog(B) ≥ 200 MB but ΔOther(B) < 48 MiB, and then RSS
> (VmRSS rise over the same window) replaces ΔOther with the same thresholds. Labels: rows 1 + 3 → **Confirmed — does not cap**;
> row 2 → **Refuted — caps**; row 4 without an RSS rise, a failed control, or row 6 → **Not confirmed** / **Invalid**.

**B3f. Predictions.** ΔOther is NMT "Other" committed at the end of the hold minus the baseline. Kslack = SendQ + RecvQ, which should be ≤ about `tcp_wmem` max + 8 KiB.

| Cell | produced (BytesSent Δ) | User-space backlog (produced − Kslack) | ΔOther (committed) |
|---|---|---|---|
| A: K=64, unpaged | ≈ 67.4 MB (64 × 1.0527 MB) | ≥ 67.4 MB − Kslack (≈ 63 MB if Kslack = 4 MiB) | ≥ 48 MiB (pool granularity 16 MiB) |
| B: K=256, unpaged | ≈ 269.5 MB | ≈ 265 MB | ≥ 240 MiB, about 4 × cell A |
| C: K=256, P=64 | ≈ 16.9 MB | ≈ 13 MB or less | ≤ 32 MiB (0 to 2 chunks), at least 7× smaller than cell B |
| D: reading, K=256 | ≈ 269.5 MB = client read bytes | ≈ 0 | ≤ 16 MiB |

- The heap used after GC stays about the same as the baseline (within ±64 MiB) in every cell.
- RSS increases by at least ΔOther − 16 MiB.
- If the 32 KiB water mark capped usage, cells A and B would both show a backlog ≤ 32 KiB + 1 R (about 1 MiB) and ΔOther ≈ 0.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Backlog and ΔOther scale with K (B ≈ 4·A) and reach hundreds of MiB, ≫ 32 KiB | The claim is confirmed: usage does not follow the water mark. |
| Backlog in A and B ≤ about 1 MiB and ΔOther ≈ 0 while the client is not reading (the server stops producing: produced ≪ K·R until the drain) | The claim is refuted: something enforces the 32 KiB mark. |
| Cell C (page cap) cuts the backlog and ΔOther about 16× relative to B, while B is unbounded by the mark | The claim is confirmed, and the positive control works: the workload and instruments show a cap that binds. |
| Cell C does not differ from B, or ΔOther does not move in A or B even though produced − Kslack is large | Not confirmed: the instrument does not see the memory. For example, NMT does not tag Netty's allocation as Other in this JDK. Fall back to RSS, or rerun with `-Dcassandra.netty_use_heap_allocator=true` and use heap after GC as the measure. |
| produced < 64 MiB in A (the server stopped responding) and no ERROR frames | Look for a read pause: `ClientMetrics` paused connections and the debug log. If writability causes it, the claim is refuted. If it is the in-flight or rate limits, record and adjust. |
| Node log shows `OutOfDirectMemoryError` or the connection closes | Unbounded growth reached the 1 GiB direct limit. This is consistent with the claim but the run is invalid for the numbers. Reduce K. |

**B3h. Controls.**
- Cell D (the client reads) rules out leaks and shows that steady-state usage is near zero when the client keeps up.
- Cell C (page size) is a known binding cap on the same workload, showing that usage moves when a real cap applies.
- `ss` Send-Q and Recv-Q separate the kernel's share from the JVM's.
- The heap-after-GC check makes sure the measured memory is off-heap response buffers.
- The warm-up before the baseline keeps chunk-cache and pool first-use from mixing into ΔOther.
- No writes happen during the flood, so memtables stay flat.
- The repeat of cell B gives the noise.

**B4. Risks and cleanup.**
- *Memory:* growth is unbounded by design, so keep K·R ≤ 25% of `MaxDirectMemorySize` (1 GiB) and ≤ 64 MiB in the unit tier. The node needs about 2.5 GiB of RAM in total.
- *Disk:* about 1 MiB of data, plus logs and commitlog of at most a few hundred MiB, all under `/mydata/$USER-s4/` on local disk. Never use shared storage.
- *Ports:* 19142, 17100, 17101 and 17199. Check they are free first: `ss -ltn | grep -E '19142|1710[01]|17199'`.
- *Leftover processes:* afterwards, run `pgrep -fa CassandraDaemon`, `pgrep -fa wm_client.py` and `pgrep -fa WriteWaterMarkBacklogTest`, and kill any found.
- *Remove* `/mydata/$USER-s4/wm-node/data`, `/mydata/$USER-s4/wm-node/logs` and `/mydata/$USER-s4/wm-unit/build/test/cassandra`. Delete the copies when the runs are done.
- A held connection keeps its memory until the client drains or closes. Always let `wm_client.py` finish, or kill it, which closes the socket and frees the queued buffers.

## C. Sources read

- src/java/org/apache/cassandra/transport/PipelineConfigurator.java
- src/java/org/apache/cassandra/transport/Flusher.java
- src/java/org/apache/cassandra/transport/Dispatcher.java (dispatch, flush, eventDispatcher)
- src/java/org/apache/cassandra/transport/PreV5Handlers.java (LegacyDispatchHandler, releaseItem, pause/unpause)
- src/java/org/apache/cassandra/transport/CQLMessageHandler.java (dispatch, toFlushItem, release)
- src/java/org/apache/cassandra/transport/CBUtil.java (allocator)
- src/java/org/apache/cassandra/transport/Message.java (encode, body allocation)
- src/java/org/apache/cassandra/transport/Envelope.java (Encoder)
- src/java/org/apache/cassandra/transport/Server.java (Builder, ConnectionTracker)
- src/java/org/apache/cassandra/net/FrameEncoder.java
- src/java/org/apache/cassandra/net/AsyncMessageOutputPlus.java, net/OutboundConnection.java, net/OutboundConnectionSettings.java (internode water-mark use, by search)
- src/java/org/apache/cassandra/metrics/ClientMessageSizeMetrics.java
- src/java/org/apache/cassandra/config/Config.java, config/DatabaseDescriptor.java, config/CassandraRelevantProperties.java (in-flight limits, idle timeout, heap-allocator property)
- conf/cassandra.yaml, conf/cassandra-env.sh, conf/jvm-server.options, conf/jvm11-server.options, conf/jvm17-server.options
- build.xml (testsome, test JVM args, heap), .build/parent-pom-template.xml, .build/cassandra-deps-template.xml (Netty version)
- test/unit/org/apache/cassandra/cql3/CQLTester.java (requireNetwork, startServer)
- test/unit/org/apache/cassandra/transport/CQLConnectionTest.java (custom PipelineConfigurator pattern, by search)
- CHANGES.txt, NEWS.txt (searched)
- https://raw.githubusercontent.com/netty/netty/4.1/transport/src/main/java/io/netty/channel/ChannelOutboundBuffer.java
- https://netty.io/4.1/api/io/netty/channel/WriteBufferWaterMark.html (cited for the javadoc wording; not fetched in this session)

## D. Stage-4 feedback

**Stage-4 audit amendments (2026-11-25, before any reading):** S4-A1 (B2a: node paths, built copy, extra echo fields),
S4-A2 (B2a gate: the as-filed `read()` gate cannot pause an `autoRead` NIO channel; the control uses `setAutoRead(isWritable())`,
the as-filed gate runs once as a diagnostic), S4-A3 (B2f: Netty's 96-byte entry overhead × 2 messages per v4 response widens the
stock band to K·R − 64 KiB … K·(R + 192); the 64 MiB-mark writable column may read false in the largest cell), S4-A4 (B2g
thresholds and verdict labels), D1 (B2a test: the configurator's `epoll` flag follows the server's; found in the shakedown), S4-A5 (B3e: paths, per-cell NMT baseline, BytesSent at end of hold, ΔOther and backlog defined,
B3g thresholds and labels). Sections A, B1, B2b–B2e, B2g rows, B3a–B3d, B3f and the B3g rows are otherwise unchanged.

Result: pending.
