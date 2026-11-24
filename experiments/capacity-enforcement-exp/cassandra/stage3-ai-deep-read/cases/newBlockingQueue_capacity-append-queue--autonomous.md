# Default capacity of `AsyncStreamingInputPlus.queue` (`newBlockingQueue()`, Integer.MAX_VALUE elements) — verification solution  <!-- file: cases/newBlockingQueue_capacity-append-queue--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line, `queue.add(buf);`, **linked**: [`AsyncStreamingInputPlus.java:75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AsyncStreamingInputPlus.java#L75) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `negative`: the only limit at the given line is the queue's capacity, the JDK default for `new LinkedBlockingQueue<>()`, 2,147,483,647 elements, which a streaming connection never approaches. The bytes the queue holds are bounded by read-on-demand flow control (`autoRead=false`, and one `channel.read()` only when the queue is empty), not by the capacity. |
| Ground | The capacity counts `ByteBuf` elements, is not configurable, and is 2^31−1, so `add` at :75 would refuse a buffer only after about 2^31 queued buffers, far more memory than any heap or direct-memory limit. What actually bounds the queue is [`AsyncStreamingInputPlus.java:62`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AsyncStreamingInputPlus.java#L62) together with :96-97: the event loop reads from the socket only when the consumer asks, so the queue holds about one socket read (at most 64 KiB with Netty's default receive allocator) per connection. Lowering the capacity to any value of 2 or more would not change usage, and the default value is never reached, so usage does not follow this constraint. |

## A. Constraint trace

**A1. The constraint.**
- **Name:** capacity of the inbound streaming byte queue `AsyncStreamingInputPlus.queue`. The field is declared at `AsyncStreamingInputPlus.java:49` and built at `AsyncStreamingInputPlus.java:59` by `newBlockingQueue()`.
- **Kind:** a constant, the JDK's default capacity, not something Cassandra configures. It is first declared at [`BlockingQueues.java:37-40`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/concurrent/BlockingQueues.java#L37-L40): the no-argument `newBlockingQueue()` returns `new LinkedBlockingQueue<>()` (line 39). The JDK's `LinkedBlockingQueue()` constructor sets capacity `Integer.MAX_VALUE`. The overload `newBlockingQueue(int capacity)` (`BlockingQueues.java:42-47`) exists, but this class does not use it.
- **Unit:** number of elements (`ByteBuf`s) in the queue, not bytes.
- **Default:** 2,147,483,647. It comes from the JDK constructor and nothing in Cassandra derives it.
- **How set:** it cannot be set. There is no yaml key, `-D` property or JMX attribute. `@Intercept` (`BlockingQueues.java:36`) only lets the simulator replace the factory. Changing it means a code change and a rebuild. The verification below changes it with a reflection swap in the unit tier and a `-D`-driven test build in the cluster tier.

**A2. What it caps.**
- **Resource:** off-heap (direct) memory. Every element is a received network buffer. Inbound child channels use `GlobalBufferPoolAllocator` (`InboundConnectionInitiator.java:108`), which hands out direct buffers from the networking `BufferPool` (`BufferPoolAllocator.java:40`, `:61-65`, `:72-75`). Past the pool's threshold (`networking_cache_size`, by default `min(128 MiB, heap/16)`, `DatabaseDescriptor.java:573-574`, `BufferPools.java:44-45`), buffers are plain `ByteBuffer.allocateDirect` overflow (`BufferPool.java:235-239`, `:263`).
- **Quantity compared against the limit:** the queue's element count. `LinkedBlockingQueue.add` → `AbstractQueue.add` → `offer` fails when `count == capacity`. The memory held is the sum of `readableBytes()` of the queued buffers (the same sum `unsafeAvailable()` computes, `AsyncStreamingInputPlus.java:164-171`), and nothing compares that sum against any limit.

**A3. Mechanism.**
1. Each inbound streaming connection, once the handshake identifies it as streaming, gets a `NettyStreamingChannel` of kind `CONTROL` (`InboundConnectionInitiator.java:447-451`). That constructs one `AsyncStreamingInputPlus` (`NettyStreamingChannel.java:81-86`) and starts one consumer thread, `Stream-Deserializer-…` (`InboundConnectionInitiator.java:452-453`). The initiating side does the same for its control channel (`NettyStreamingConnectionFactory.java:69-73`).
2. The constructor builds the queue with the default capacity (`AsyncStreamingInputPlus.java:59`) and turns off auto-read on the channel (`AsyncStreamingInputPlus.java:62`).
3. **The given line:** on the event loop, `NettyStreamingChannel.channelRead` (`NettyStreamingChannel.java:215-219`) calls `append`. Once the producer is closed, `append` returns false and the caller releases the buffer (`AsyncStreamingInputPlus.java:72-73`). Otherwise it runs [`queue.add(buf)` at `AsyncStreamingInputPlus.java:75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AsyncStreamingInputPlus.java#L75).
   - **Below capacity (always, in practice):** the buffer is enqueued and `append` returns true.
   - **At capacity (2^31−1 buffers):** `add` throws `IllegalStateException("Queue full")`. It propagates out of `channelRead` without the buffer being released. Netty routes it to `NettyStreamingChannel.exceptionCaught` (`NettyStreamingChannel.java:229-236`), which logs a WARN ("exception occurred while in processing streaming data") and closes the channel, so the stream session fails. There is no back-pressure or retry; the check is a hard failure.
4. **What really bounds the queue, the consumer-driven read:** `reBuffer()` (`AsyncStreamingInputPlus.java:91-124`) runs on the deserializer thread. It calls `channel.read()` only when the queue is empty (`:96-97`), then blocks in `queue.take()` (`:108`). With auto-read off, each `channel.read()` makes the transport do one socket read into one buffer sized by the channel's `RecvByteBufAllocator`. Cassandra does not set one, so it is Netty's `AdaptiveRecvByteBufAllocator`, at most 65,536 bytes. The transport then stops, because `MaxMessageHandle.continueReading()` requires `isAutoRead()`. The result is one `channelRead` and one `append` per request. In steady state a queue holds 0–1 data buffers, and a second buffer (the consumer's current one, `currentBuf`, `:47`, `:122-123`) is outside the queue.
5. **Paths that bypass or overshoot that bound** (none of them involve the capacity):
   - (a) Handshake hand-over. The handshake handler is a `ByteToMessageDecoder` (`InboundConnectionInitiator.java:277`). When `pipeline.replace` swaps it out (`:451`), bytes left in its cumulation are fired once into the new handler.
   - (b) TLS. `SslHandler` can decode one socket read into several buffers, and with auto-read off it issues extra reads until a record completes. The overshoot is bounded by the record size and the read size.
   - (c) The close sentinel. `requestClosure` adds `Unpooled.EMPTY_BUFFER` (`AsyncStreamingInputPlus.java:219-226`), which is 0 bytes.
   - (d) Any code that turned auto-read back on would remove the bound. None does in 5.0.9: `channel.read()` is called only here, at `:97`, in the streaming code.
6. **Per-node total:** one queue per inbound streaming connection. The sender opens one control channel plus up to `cassandra.streaming.session.parallelTransfers` file channels, default the number of processors (`StreamingMultiplexedChannel.java:94-98`). So the per-node total is about (peers × (1 + parallel transfers)) × 64 KiB. That number does not involve the capacity.

**A4. Other consumers.** These use the same direct memory and are not governed by this queue's capacity:
- the networking `BufferPool`, for internode messaging frames and native-protocol client buffers (`BufferPools.forNetworking`);
- `StreamCompressionInputStream`'s decompression buffers, taken from the channel's allocator (`StreamCompressionInputStream.java:59-60`);
- the chunk-cache pool (`BufferPools.java:38-39`);
- the sending side's `AsyncStreamingOutputPlus` buffers;
- the stream receiver's sstable writers, which use disk rather than memory: `SSTableZeroCopyWriter` (`SSTableZeroCopyWriter.java:208-221`) and the compressed and uncompressed stream readers.

**A5. Evidence beyond the source.**
- JDK 11 `LinkedBlockingQueue` (the no-argument constructor has capacity `Integer.MAX_VALUE`; `add` throws `IllegalStateException` if no space): https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html
- JDK 11 `AbstractQueue.add`: https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/AbstractQueue.html#add(E)
- Netty 4.1 `ChannelConfig.setAutoRead`/`Channel.read()` semantics: https://netty.io/4.1/api/io/netty/channel/ChannelConfig.html
- Netty 4.1 `AdaptiveRecvByteBufAllocator` (default minimum 64, initial 2048 in 4.1, maximum 65536): https://netty.io/4.1/api/io/netty/channel/AdaptiveRecvByteBufAllocator.html
- Netty 4.1 `DefaultMaxMessagesRecvByteBufAllocator.MaxMessageHandle.continueReading` (requires `isAutoRead()`): https://github.com/netty/netty/blob/4.1/transport/src/main/java/io/netty/channel/DefaultMaxMessagesRecvByteBufAllocator.java
- The pinned Netty version is 4.1.130.Final (`.build/parent-pom-template.xml:747-749`).
- The existing tests `test/unit/org/apache/cassandra/net/AsyncStreamingInputPlusTest.java` only exercise `append`/`read` on an `EmbeddedChannel`. None tests the capacity.
- The source copy has no git history, so no ticket is relied on.
- The library URLs are cited from documentation knowledge and were not fetched in this session. Stage 4's counters (`maxQueueSize`, `maxQueuedBytes` per read) check the Netty read-once behaviour directly.

## B. Verification solution

**B1. Claim under test.** The default capacity of `AsyncStreamingInputPlus.queue` (Integer.MAX_VALUE elements, checked at `AsyncStreamingInputPlus.java:75`) does not cap memory. The bytes held in the queue and the node's direct memory stay at about one socket read per connection whatever the capacity (2, 8, 16 or the default), the consumer speed or the volume streamed. They grow with the volume streamed only when the read-on-demand flow control is removed, and a capacity binds (fails the stream with `IllegalStateException: Queue full`) only when it is small enough to be reached, which needs that same removal.

### B2. Unit tier

**B2a. Environment and build.**
- **Host and JDK:** one Linux host, JDK 11 (`java -version` shows 11), Ant ≥ 1.10, at least 8 GiB free RAM and at least 10 GiB free local disk.
- **Work copy:** `export WORK=/mydata/$USER/o181` (any local disk; check with `df -h $WORK`). Make a copy for the unit tier with `rsync -a ~/cassandra-5.0.9/ $WORK/stock/`. The shared tree is never built in.
- **Test source:** `$WORK/stock/test/unit/org/apache/cassandra/net/AsyncStreamingInputPlusCapacityTest.java`, exactly the source in the listing below. It uses only Netty, JUnit and the stock `AsyncStreamingInputPlus`. It does not need `DatabaseDescriptor`.
- **Build:** `cd $WORK/stock && ant -Dno-checkstyle=true jar`. This builds main, test and stress classes, and the cluster tier reuses it.
- **JVM options:** those of `ant testsome` (`build.xml:1382-1392` and the `testmacro` options). No heap or direct-memory option is needed: the largest arm holds 256 MiB of direct memory, and the JVM's default direct limit equals the default heap, a quarter of RAM.
- **Transports:** each arm runs on NIO and on epoll. Cassandra uses epoll on Linux (`SocketFactory.java:164`). The epoll arms are skipped (JUnit assumption) if `Epoll.isAvailable()` is false.

<details><summary><code>AsyncStreamingInputPlusCapacityTest.java</code> (save verbatim)</summary>

```java
/*
 * o181 unit-tier harness (test copy only, never the shared tree).
 * Drives the stock AsyncStreamingInputPlus over a real loopback socket. The private `queue` is swapped,
 * by reflection, for a LinkedBlockingQueue subclass of a chosen capacity that records the bytes and
 * elements it holds (the operand of the check at AsyncStreamingInputPlus.java:75).
 */
package org.apache.cassandra.net;

import java.io.OutputStream;
import java.lang.reflect.Field;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.LockSupport;

import org.junit.Assert;
import org.junit.Assume;
import org.junit.Test;

import io.netty.bootstrap.ServerBootstrap;
import io.netty.buffer.ByteBuf;
import io.netty.buffer.Unpooled;
import io.netty.buffer.UnpooledByteBufAllocator;
import io.netty.channel.Channel;
import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.ChannelInboundHandlerAdapter;
import io.netty.channel.ChannelInitializer;
import io.netty.channel.ChannelOption;
import io.netty.channel.EventLoopGroup;
import io.netty.channel.FixedRecvByteBufAllocator;
import io.netty.channel.RecvByteBufAllocator;
import io.netty.channel.epoll.Epoll;
import io.netty.channel.epoll.EpollEventLoopGroup;
import io.netty.channel.epoll.EpollServerSocketChannel;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.nio.NioServerSocketChannel;
import io.netty.util.ReferenceCountUtil;

public class AsyncStreamingInputPlusCapacityTest
{
    static final int KIB = 1024, MIB = 1024 * KIB;
    static final int DEFAULT_CAP = Integer.MAX_VALUE;   // what newBlockingQueue() gives (BlockingQueues.java:39)
    static final long NO_CONSUMER = -1;                 // nobody calls reBuffer(), so nobody calls channel.read()
    static final long READ_MAX = 65536;                 // AdaptiveRecvByteBufAllocator default maximum (Netty 4.1)

    /** Same queue type as stock, chosen capacity, records the operand of the check at :75. */
    static final class TrackingQueue extends LinkedBlockingQueue<ByteBuf>
    {
        final AtomicLong bytes = new AtomicLong(), maxBytes = new AtomicLong();
        final AtomicInteger maxSize = new AtomicInteger();

        TrackingQueue(int capacity) { super(capacity); }

        @Override
        public boolean offer(ByteBuf b) // AbstractQueue.add -> offer; add throws IllegalStateException("Queue full") on false
        {
            int n = b.readableBytes();
            long q = bytes.addAndGet(n);
            if (!super.offer(b))
            {
                bytes.addAndGet(-n);
                return false;
            }
            maxBytes.accumulateAndGet(q, Math::max);
            if (b != Unpooled.EMPTY_BUFFER)
                maxSize.accumulateAndGet(size(), Math::max);
            return true;
        }

        @Override
        public ByteBuf take() throws InterruptedException
        {
            ByteBuf b = super.take();
            bytes.addAndGet(-b.readableBytes());
            return b;
        }
    }

    static final class Result
    {
        String arm; long maxQueuedBytes; int maxQueueSize; long ise; long maxDirect; long sent; long received;
        public String toString()
        {
            return String.format("O181 arm=%s maxQueuedBytes=%d maxQueueSize=%d ise=%d maxDirectBytes=%d sent=%d received=%d",
                                 arm, maxQueuedBytes, maxQueueSize, ise, maxDirect, sent, received);
        }
    }

    static Result run(String arm, boolean epoll, int capacity, boolean flowControl, long consumerDelayMs,
                      long totalBytes, RecvByteBufAllocator recv) throws Exception
    {
        if (epoll)
            Assume.assumeTrue("epoll not available", Epoll.isAvailable());
        EventLoopGroup boss = epoll ? new EpollEventLoopGroup(1) : new NioEventLoopGroup(1);
        EventLoopGroup worker = epoll ? new EpollEventLoopGroup(1) : new NioEventLoopGroup(1);
        UnpooledByteBufAllocator alloc = new UnpooledByteBufAllocator(true);
        CompletableFuture<AsyncStreamingInputPlus> inF = new CompletableFuture<>();
        CompletableFuture<Channel> chF = new CompletableFuture<>();
        TrackingQueue tq = new TrackingQueue(capacity);
        AtomicLong ise = new AtomicLong(), sent = new AtomicLong(), received = new AtomicLong(), maxDirect = new AtomicLong();
        AtomicBoolean stop = new AtomicBoolean();
        Result r = new Result();
        r.arm = arm + (epoll ? "/epoll" : "/nio");
        Channel server = null;
        try
        {
            ServerBootstrap b = new ServerBootstrap()
                                .group(boss, worker)
                                .channel(epoll ? EpollServerSocketChannel.class : NioServerSocketChannel.class)
                                .childOption(ChannelOption.ALLOCATOR, alloc)
                                .childHandler(new ChannelInitializer<Channel>()
            {
                protected void initChannel(Channel ch) throws Exception
                {
                    if (recv != null)
                        ch.config().setRecvByteBufAllocator(recv);
                    AsyncStreamingInputPlus in = new AsyncStreamingInputPlus(ch); // stock: sets autoRead=false (:62)
                    Field f = AsyncStreamingInputPlus.class.getDeclaredField("queue");
                    f.setAccessible(true);
                    f.set(in, tq);
                    if (!flowControl)
                        ch.config().setAutoRead(true); // positive control: remove read-on-demand
                    ch.pipeline().addLast(new ChannelInboundHandlerAdapter()
                    {
                        public void channelRead(ChannelHandlerContext ctx, Object msg)
                        {
                            // mirrors NettyStreamingChannel.channelRead (NettyStreamingChannel.java:215-219)
                            try
                            {
                                if (!in.append((ByteBuf) msg))
                                    ReferenceCountUtil.release(msg);
                            }
                            catch (IllegalStateException e) // the outcome of :75 when the queue is full
                            {
                                ise.incrementAndGet();
                                ReferenceCountUtil.release(msg);
                            }
                        }
                    });
                    inF.complete(in);
                    chF.complete(ch);
                }
            });
            server = b.bind("127.0.0.1", 0).sync().channel();
            int port = ((InetSocketAddress) server.localAddress()).getPort();

            Thread sampler = new Thread(() -> {
                while (!stop.get())
                {
                    maxDirect.accumulateAndGet(alloc.metric().usedDirectMemory(), Math::max);
                    LockSupport.parkNanos(TimeUnit.MILLISECONDS.toNanos(5));
                }
            }, "o181-sampler");
            sampler.setDaemon(true);
            sampler.start();

            Thread client = new Thread(() -> {
                byte[] chunk = new byte[64 * KIB];
                try (Socket s = new Socket("127.0.0.1", port))
                {
                    OutputStream out = s.getOutputStream();
                    long left = totalBytes;
                    while (left > 0)
                    {
                        int n = (int) Math.min(chunk.length, left);
                        out.write(chunk, 0, n);
                        sent.addAndGet(n);
                        left -= n;
                    }
                    out.flush();
                    s.getInputStream().read(); // hold the socket open until the server side closes
                }
                catch (Exception ignore) { }
            }, "o181-client");
            client.setDaemon(true);
            client.start();

            AsyncStreamingInputPlus in = inF.get(10, TimeUnit.SECONDS);
            Channel ch = chF.get(10, TimeUnit.SECONDS);

            if (consumerDelayMs == NO_CONSUMER)
            {
                // wait until the sender has sent everything or has been stalled for 2 s (max 60 s)
                long last = -1, lastChange = System.nanoTime(), deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(60);
                while (System.nanoTime() < deadline)
                {
                    long s = sent.get();
                    if (s >= totalBytes) break;
                    if (s != last) { last = s; lastChange = System.nanoTime(); }
                    else if (System.nanoTime() - lastChange > TimeUnit.SECONDS.toNanos(2)) break;
                    LockSupport.parkNanos(TimeUnit.MILLISECONDS.toNanos(50));
                }
                LockSupport.parkNanos(TimeUnit.SECONDS.toNanos(1)); // let the event loop deliver what it has read
                ch.close().sync();
                ByteBuf x;
                while ((x = tq.poll()) != null)
                    if (x != Unpooled.EMPTY_BUFFER && x.refCnt() > 0) x.release();
            }
            else
            {
                Thread consumer = new Thread(() -> {
                    try
                    {
                        in.consume(buf -> {
                            int n = buf.remaining();
                            received.addAndGet(n);
                            if (consumerDelayMs > 0)
                                LockSupport.parkNanos(TimeUnit.MILLISECONDS.toNanos(consumerDelayMs));
                            return n;
                        }, totalBytes);
                    }
                    catch (Exception e) { throw new RuntimeException(e); }
                }, "o181-consumer");
                consumer.start();
                consumer.join(TimeUnit.MINUTES.toMillis(5));
                Assert.assertFalse("consumer did not finish in 5 min", consumer.isAlive());
                ch.eventLoop().submit(in::requestClosure).sync();
                in.close();  // drains to the sentinel and releases the current buffer
                ch.close().sync();
            }
            r.maxQueuedBytes = tq.maxBytes.get();
            r.maxQueueSize = tq.maxSize.get();
            r.ise = ise.get();
            r.sent = sent.get();
            r.received = received.get();
        }
        finally
        {
            stop.set(true);
            if (server != null) server.close().sync();
            worker.shutdownGracefully(0, 1, TimeUnit.SECONDS).sync();
            boss.shutdownGracefully(0, 1, TimeUnit.SECONDS).sync();
        }
        r.maxDirect = maxDirect.get();
        System.out.println(r);
        return r;
    }

    // ---- U1: stock capacity, flow control on, consumer speed and volume varied ----
    void u1(boolean epoll) throws Exception
    {
        long[][] grid = { { 0, 256 * MIB }, { 1, 64 * MIB }, { 1, 256 * MIB }, { 10, 64 * MIB } };
        for (long[] g : grid)
        {
            Result r = run("U1-cap=default-flow=on-d=" + g[0] + "ms-T=" + (g[1] / MIB) + "MiB", epoll, DEFAULT_CAP, true, g[0], g[1], null);
            Assert.assertEquals(g[1], r.received);
            Assert.assertEquals(0, r.ise);
            Assert.assertTrue(r.toString(), r.maxQueuedBytes <= 2 * READ_MAX);
            Assert.assertTrue(r.toString(), r.maxQueueSize <= 2);
            Assert.assertTrue(r.toString(), r.maxDirect <= 4 * READ_MAX);
        }
    }
    @Test public void u1Nio() throws Exception { u1(false); }
    @Test public void u1Epoll() throws Exception { u1(true); }

    // ---- U2: the constraint itself varied (capacity 2, 16), flow control on ----
    void u2(boolean epoll) throws Exception
    {
        for (int cap : new int[]{ 2, 16 })
        {
            Result r = run("U2-cap=" + cap + "-flow=on-d=1ms-T=64MiB", epoll, cap, true, 1, 64 * MIB, null);
            Assert.assertEquals(64 * MIB, r.received);
            Assert.assertEquals(r.toString(), 0, r.ise);
            Assert.assertTrue(r.toString(), r.maxQueuedBytes <= 2 * READ_MAX);
        }
    }
    @Test public void u2Nio() throws Exception { u2(false); }
    @Test public void u2Epoll() throws Exception { u2(true); }

    // ---- U3: stock capacity, flow control on, no consumer at all ----
    void u3(boolean epoll) throws Exception
    {
        Result r = run("U3-cap=default-flow=on-noconsumer-T=256MiB", epoll, DEFAULT_CAP, true, NO_CONSUMER, 256 * MIB, null);
        Assert.assertEquals(r.toString(), 0, r.maxQueuedBytes);
        Assert.assertTrue(r.toString(), r.sent < 256 * MIB);
    }
    @Test public void u3Nio() throws Exception { u3(false); }
    @Test public void u3Epoll() throws Exception { u3(true); }

    // ---- P1: positive control, flow control removed, stock capacity, no consumer ----
    void p1(boolean epoll) throws Exception
    {
        Result r = run("P1-cap=default-flow=off-noconsumer-T=256MiB", epoll, DEFAULT_CAP, false, NO_CONSUMER, 256 * MIB, null);
        Assert.assertEquals(r.toString(), 256L * MIB, r.maxQueuedBytes);
        Assert.assertEquals(r.toString(), 0, r.ise);
        Assert.assertTrue(r.toString(), r.maxDirect >= 256L * MIB);
    }
    @Test public void p1Nio() throws Exception { p1(false); }
    @Test public void p1Epoll() throws Exception { p1(true); }

    // ---- P2: positive control for the capacity: flow control removed, capacity 16, no consumer ----
    void p2(boolean epoll) throws Exception
    {
        Result r = run("P2-cap=16-flow=off-noconsumer-T=256MiB", epoll, 16, false, NO_CONSUMER, 256 * MIB, null);
        Assert.assertEquals(r.toString(), 16, r.maxQueueSize);
        Assert.assertTrue(r.toString(), r.ise > 0);
        Assert.assertTrue(r.toString(), r.maxQueuedBytes <= 16 * READ_MAX);
    }
    @Test public void p2Nio() throws Exception { p2(false); }
    @Test public void p2Epoll() throws Exception { p2(true); }

    // ---- U5: flow control on, read size raised to 1 MiB: the bound follows the read size ----
    void u5(boolean epoll) throws Exception
    {
        Result r = run("U5-cap=default-flow=on-d=1ms-T=64MiB-recv=fixed1MiB", epoll, DEFAULT_CAP, true, 1, 64 * MIB,
                       new FixedRecvByteBufAllocator(MIB));
        Assert.assertEquals(64 * MIB, r.received);
        Assert.assertTrue(r.toString(), r.maxQueuedBytes <= 2L * MIB);
    }
    @Test public void u5Nio() throws Exception { u5(false); }
    @Test public void u5Epoll() throws Exception { u5(true); }
}
```
</details>

**B2b. Knobs.**
- **Capacity `C` (the constraint):** default (Integer.MAX_VALUE), 16, 2. `C` is set by replacing the private `queue` with a `LinkedBlockingQueue` subclass of capacity `C`, through reflection, right after the stock constructor runs. 2 is the smallest value that still leaves room for the close sentinel, and 16 is used for the positive control.
- **Flow control:** on (stock, `autoRead=false`), or off (`ch.config().setAutoRead(true)` after construction). Off is the positive control only.
- **Consumer delay `d` per buffer:** none (no consumer: `reBuffer` is never called), 0, 1 ms, 10 ms. These make the consumer from far faster than to far slower than a loopback sender.
- **Volume `T`:** 64 MiB, 256 MiB, enough to be about 1000–4000 times the read size.
- **Read size (U5 only):** the default adaptive allocator (≤ 64 KiB), or `FixedRecvByteBufAllocator(1 MiB)`. This shows what the bound does follow.

**B2c. Workload.** A `java.net.Socket` client on 127.0.0.1 writes `T` bytes in 64 KiB chunks to a Netty server whose child channel holds a stock `AsyncStreamingInputPlus`. The server's handler is the same `append` call as `NettyStreamingChannel.channelRead`. A consumer thread calls `in.consume(...)` for exactly `T` bytes, sleeping `d` per buffer.
- **Arithmetic that the limit cannot be reached:** reaching the default capacity needs 2^31−1 queued buffers. At even 64 bytes each (Netty's minimum read) that is 128 GiB, and at 64 KiB each it is 128 TiB. So no workload reaches it.
- **Arithmetic that a small capacity can be reached:** with flow control off and no consumer, 256 MiB arrives as at least 256 MiB / 64 KiB = 4096 buffers, which is 4096 ≫ 16, so capacity 16 must be hit (arm P2).
- **Arms** (each on NIO and on epoll):
  - **U1:** C = default, flow on, (d, T) ∈ {(0, 256 MiB), (1 ms, 64 MiB), (1 ms, 256 MiB), (10 ms, 64 MiB)}.
  - **U2:** C ∈ {2, 16}, flow on, d = 1 ms, T = 64 MiB.
  - **U3:** C = default, flow on, no consumer, T = 256 MiB.
  - **P1 (positive control):** C = default, flow off, no consumer, T = 256 MiB.
  - **P2 (positive control for the capacity):** C = 16, flow off, no consumer, T = 256 MiB.
  - **U5:** C = default, flow on, d = 1 ms, T = 64 MiB, fixed 1 MiB reads.

**B2d. Observables and instruments.**
- **The check's operand, measured exactly** (not sampled): `TrackingQueue` adds `readableBytes()` on every successful `offer` and subtracts it on every `take`. From that it records:
  - `maxQueuedBytes`, the peak bytes in the queue;
  - `maxQueueSize`, the peak element count, without the 0-byte sentinel;
  - `ise`, the count of `IllegalStateException` from `append`, which is the `add` at :75 failing.
- **The resource:** `UnpooledByteBufAllocator.metric().usedDirectMemory()` for the child channel's allocator, sampled every 5 ms (`maxDirectBytes`). It counts the capacity of every live direct buffer, both queued and being consumed.
- **Also recorded:** `sent` (client bytes written) and `received` (bytes the consumer saw).
- **Output:** one line per arm, `O181 arm=… maxQueuedBytes=… maxQueueSize=… ise=… maxDirectBytes=… sent=… received=…`, in `$WORK/stock/build/test/output/TEST-org.apache.cassandra.net.AsyncStreamingInputPlusCapacityTest.xml` (system-out).
- **Not observable:** the kernel socket buffers, which hold the unread bytes when flow control is on. They show up only as `sent` running ahead of what was read.

**B2e. Procedure.**
1. `export WORK=/mydata/$USER/o181; mkdir -p $WORK; df -h $WORK` (at least 10 GiB free).
2. `rsync -a ~/cassandra-5.0.9/ $WORK/stock/`
3. Save the test source above as `$WORK/stock/test/unit/org/apache/cassandra/net/AsyncStreamingInputPlusCapacityTest.java`.
4. `cd $WORK/stock && ant -Dno-checkstyle=true jar 2>&1 | tail -5` (expect `BUILD SUCCESSFUL`).
5. `ant -Dno-checkstyle=true -Dtest.timeout=900000 testsome -Dtest.name=org.apache.cassandra.net.AsyncStreamingInputPlusCapacityTest 2>&1 | tee $WORK/unit-run.log | tail -30`
6. `grep -o 'O181 arm=[^<]*' build/test/output/TEST-org.apache.cassandra.net.AsyncStreamingInputPlusCapacityTest.xml > $WORK/unit-results.txt; cat $WORK/unit-results.txt`
7. Record the pass or fail of each JUnit method. Each method's assertions are the predictions in B2f, so a failure names the refuted row.
8. Check that nothing is left with `pgrep -u $USER -f 'junit|JUnitTestRunner' || echo none`.

**B2f. Predictions** (before any run; each on NIO and epoll):

| Arm | maxQueueSize | maxQueuedBytes | ise | maxDirectBytes | other |
|---|---|---|---|---|---|
| U1, all four (d, T) | 1 (≤ 2) | ≤ 65,536 (assert ≤ 131,072); the same for 64 and 256 MiB and for d = 0, 1, 10 ms | 0 | ≤ 196,608 (assert ≤ 262,144) | received = T |
| U2, C = 2 and C = 16 | 1 (≤ 2) | the same as U1 with d = 1 ms (≤ 131,072) | 0 | as U1 | received = 64 MiB |
| U3 (no consumer, flow on) | 0 | 0 | 0 | ≈ 0 | sent stalls at a few MiB (socket buffers), < 256 MiB |
| P1 (flow off, C default) | ≈ 4096+ | = 268,435,456 (all of T) | 0 | ≥ 268,435,456 | sent = T |
| P2 (flow off, C = 16) | = 16 | ≤ 16 × 65,536 = 1,048,576 | > 0 (thousands) | ≤ ~1.1 MiB | the rest is dropped |
| U5 (1 MiB reads) | 1 (≤ 2) | > 65,536 at least once and ≤ 1,048,576 (assert ≤ 2 MiB) | 0 | ≤ ~3 MiB | received = 64 MiB |

The claim is wrong if, under flow control (U1/U2), `maxQueuedBytes` or `maxDirectBytes` grows with T or with d, or if it differs between C = 2, 16 and default.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| U1 and U2 flat (≤ 2 × 64 KiB, the same for every C, T and d), while P1 holds all 256 MiB | **Claim confirmed:** the capacity is not what bounds the queue, and the flow control is. |
| U1 `maxQueuedBytes` grows with T or with d (e.g. ≥ 1 MiB at d = 10 ms) | **Claim refuted** for the flow-control part: reads are not on demand. The capacity is then the only limit, and at its default it is unbounded. |
| U2 with C = 2 shows `ise > 0`, or less memory than C = default | **Claim refuted:** usage follows the capacity. |
| U5 `maxQueuedBytes` rises above 64 KiB but stays ≤ about 1–2 MiB | The bound follows the read size, not the capacity. This is consistent with the claim. |
| P1 does not reach about 256 MiB (e.g. stays at 64 KiB) | **Not confirmed:** the positive control did not move. The harness is not delivering data the way claimed, so the flat U1 says nothing. |
| P2 shows `ise = 0` or `maxQueueSize ≠ 16` | **Not confirmed:** a reachable capacity did not bind. Check the reflection swap (wrong field, or a stock queue still in use). |
| U3 `maxQueuedBytes > 0` | Something reads without being asked (e.g. auto-read on). That would weaken the claim; look at transport behaviour before concluding. |
| Assumption skip on epoll | Only the NIO evidence counts. Note it; the cluster tier covers epoll. |

**B2h. Controls.**
- P1 is the positive control for "usage moves when nothing bounds it": the same harness and workload with auto-read on.
- P2 is the positive control that a capacity binds when it is reachable, and it uses the same queue type `newBlockingQueue(int)` would build.
- U3 shows that, with flow control on, no consumer means no reads at all.
- `TrackingQueue` is a `LinkedBlockingQueue`, the stock type, and changes only the capacity. The stock `append`/`reBuffer`/`consume` code runs unmodified.
- Each arm gets its own allocator and event loops, so `maxDirectBytes` does not carry over.
- Running on both NIO and epoll rules out a single-transport artefact.

### B3. Cluster tier

**B3a. Environment and build.**
- **Node:** one Linux node, JDK 11, at least 16 GiB RAM, and at least 30 GiB free local disk under `$WORK` (`/mydata/$USER/o181`). Ports 7000, 9042 and 7199 must be free (`ss -ltn | grep -E ':(7000|9042|7199)\b' || echo free`). If they are not, see B4.
- **Single Cassandra node on 127.0.0.1:** inbound streaming is driven by `sstableloader` from the same host. Every inbound streaming connection gets an `AsyncStreamingInputPlus` (`InboundConnectionInitiator.java:447-453`). One node is enough because the queue is per-connection on the receiver.
- **Builds:**
  - `$WORK/stock`: built in B2.
  - `$WORK/probe`: the same tree plus a test-only probe in `AsyncStreamingInputPlus`. The probe does three things:
    - It takes three `-D` properties: `asip.test.capacity` (0 = stock `newBlockingQueue()`), `asip.test.autoread` (false = stock) and `asip.test.rebuffer_sleep_ms` (0 = stock).
    - It counts queued bytes and elements and `IllegalStateException`s at :75.
    - It logs one `ASIP-PROBE` line a second to `system.log`.

    With no `-Dasip.test.*` property, its behaviour is stock 5.0.9. It is applied with the script below, which refuses to patch if any anchor is not found exactly once.

<details><summary><code>patch_asip.py</code> (save verbatim as <code>$WORK/patch_asip.py</code>)</summary>

```python
#!/usr/bin/env python3
# o181 probe patch for AsyncStreamingInputPlus (test build only). Usage: python3 -I patch_asip.py <path/to/AsyncStreamingInputPlus.java>
import sys
p = sys.argv[1]
s = open(p).read()
R = [
("import static org.apache.cassandra.utils.concurrent.BlockingQueues.newBlockingQueue;\n",
 "import static org.apache.cassandra.utils.concurrent.BlockingQueues.newBlockingQueue;\n"
 "import java.util.concurrent.atomic.AtomicInteger; // o181 probe\n"
 "import java.util.concurrent.atomic.AtomicLong; // o181 probe\n"),
("    private boolean isConsumerClosed = false;\n",
 "    private boolean isConsumerClosed = false;\n\n"
 "    // ---- o181 probe (test build only); with no -Dasip.test.* property the behaviour equals stock 5.0.9 ----\n"
 "    private static final org.slf4j.Logger PROBE_LOG = org.slf4j.LoggerFactory.getLogger(\"ASIP-PROBE\");\n"
 "    private static final int PROBE_CAPACITY = Integer.getInteger(\"asip.test.capacity\", 0); // 0 = stock newBlockingQueue()\n"
 "    private static final boolean PROBE_AUTOREAD = Boolean.getBoolean(\"asip.test.autoread\"); // false = stock\n"
 "    private static final long PROBE_SLEEP_MS = Long.getLong(\"asip.test.rebuffer_sleep_ms\", 0L); // 0 = stock\n"
 "    static final AtomicLong PROBE_QUEUED = new AtomicLong();\n"
 "    static final AtomicLong PROBE_MAX_QUEUED = new AtomicLong();\n"
 "    static final AtomicInteger PROBE_MAX_SIZE = new AtomicInteger();\n"
 "    static final AtomicInteger PROBE_LIVE = new AtomicInteger();\n"
 "    static final AtomicLong PROBE_ISE = new AtomicLong();\n"
 "    static\n"
 "    {\n"
 "        Thread t = new Thread(() -> {\n"
 "            while (true)\n"
 "            {\n"
 "                try { Thread.sleep(1000); } catch (InterruptedException e) { return; }\n"
 "                PROBE_LOG.info(\"live={} queued_bytes={} max_queued_bytes={} max_queue_size={} ise={} capacity={} autoread={} sleep_ms={}\",\n"
 "                               PROBE_LIVE.get(), PROBE_QUEUED.get(), PROBE_MAX_QUEUED.get(), PROBE_MAX_SIZE.get(), PROBE_ISE.get(),\n"
 "                               PROBE_CAPACITY == 0 ? \"default\" : String.valueOf(PROBE_CAPACITY), PROBE_AUTOREAD, PROBE_SLEEP_MS);\n"
 "            }\n"
 "        }, \"asip-probe\");\n"
 "        t.setDaemon(true);\n"
 "        t.start();\n"
 "    }\n"
 "    // ---- end o181 probe ----\n"),
("        queue = newBlockingQueue();\n\n        this.channel = channel;\n        channel.config().setAutoRead(false);\n",
 "        queue = PROBE_CAPACITY > 0 ? newBlockingQueue(PROBE_CAPACITY) : newBlockingQueue(); // o181 probe\n\n"
 "        this.channel = channel;\n"
 "        channel.config().setAutoRead(PROBE_AUTOREAD); // o181 probe; stock: false\n"
 "        PROBE_LIVE.incrementAndGet(); // o181 probe\n"),
("        queue.add(buf);\n\n        return true;\n",
 "        int probeN = buf.readableBytes(); // o181 probe\n"
 "        long probeQ = PROBE_QUEUED.addAndGet(probeN);\n"
 "        try\n"
 "        {\n"
 "            queue.add(buf);\n"
 "        }\n"
 "        catch (IllegalStateException e)\n"
 "        {\n"
 "            PROBE_QUEUED.addAndGet(-probeN);\n"
 "            PROBE_ISE.incrementAndGet();\n"
 "            throw e;\n"
 "        }\n"
 "        PROBE_MAX_QUEUED.accumulateAndGet(probeQ, Math::max);\n"
 "        PROBE_MAX_SIZE.accumulateAndGet(queue.size(), Math::max);\n\n"
 "        return true;\n"),
("        if (isConsumerClosed)\n            throw new ClosedChannelException();\n\n        if (queue.isEmpty())\n",
 "        if (isConsumerClosed)\n            throw new ClosedChannelException();\n\n"
 "        if (PROBE_SLEEP_MS > 0) // o181 probe: slow consumer\n"
 "        {\n"
 "            try { Thread.sleep(PROBE_SLEEP_MS); } catch (InterruptedException e) { /* ignore */ }\n"
 "        }\n\n"
 "        if (queue.isEmpty())\n"),
("        if (next == Unpooled.EMPTY_BUFFER) // the indicator that the input is closed\n",
 "        if (next != Unpooled.EMPTY_BUFFER) // o181 probe\n"
 "            PROBE_QUEUED.addAndGet(-next.readableBytes());\n\n"
 "        if (next == Unpooled.EMPTY_BUFFER) // the indicator that the input is closed\n"),
("                if (buf == Unpooled.EMPTY_BUFFER)\n                    break;\n                buf.release();\n",
 "                if (buf == Unpooled.EMPTY_BUFFER)\n                    break;\n"
 "                PROBE_QUEUED.addAndGet(-buf.readableBytes()); // o181 probe\n"
 "                buf.release();\n"),
("            queue.add(Unpooled.EMPTY_BUFFER);\n            isProducerClosed = true;\n",
 "            queue.add(Unpooled.EMPTY_BUFFER);\n            isProducerClosed = true;\n"
 "            PROBE_LIVE.decrementAndGet(); // o181 probe\n"),
]
for old, new in R:
    n = s.count(old)
    if n != 1:
        sys.exit("patch anchor found %d times (expected 1): %r" % (n, old[:60]))
    s = s.replace(old, new)
open(p, "w").write(s)
print("patched", p)
```
</details>

```bash
export WORK=/mydata/$USER/o181
rsync -a ~/cassandra-5.0.9/ $WORK/probe/
python3 -I $WORK/patch_asip.py $WORK/probe/src/java/org/apache/cassandra/net/AsyncStreamingInputPlus.java
(cd $WORK/probe && ant -Dno-checkstyle=true jar 2>&1 | tail -3)
# one conf dir, used by every arm; data, logs and commitlog under $WORK/run
cp -a $WORK/stock/conf $WORK/conf
cat >> $WORK/conf/cassandra.yaml <<EOF

# ---- o181 ----
data_file_directories: [$WORK/run/data]
commitlog_directory: $WORK/run/commitlog
hints_directory: $WORK/run/hints
saved_caches_directory: $WORK/run/saved_caches
cdc_raw_directory: $WORK/run/cdc_raw
EOF
sed -i 's/^listen_address: localhost/listen_address: 127.0.0.1/; s/^rpc_address: localhost/rpc_address: 127.0.0.1/; s/^auto_snapshot: true/auto_snapshot: false/' $WORK/conf/cassandra.yaml
grep -nE '^(data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory|auto_snapshot|listen_address|rpc_address):' $WORK/conf/cassandra.yaml
# each key must appear exactly once (in 5.0.9 the five directory keys are only commented out, cassandra.yaml:97,395,408,431,611)
```

- **Node JVM, for every arm:** `MAX_HEAP_SIZE=4G`, `MAX_DIRECT_MEMORY_SIZE=4G` (read by `conf/cassandra-env.sh:139-158`), and `-XX:NativeMemoryTracking=summary` through `JVM_EXTRA_OPTS` (`conf/cassandra-env.sh:307`). G1 is the default (`conf/jvm11-server.options:63`), so `HEAP_NEWSIZE` is not set.
- **Streaming defaults** stay as shipped: `stream_entire_sstables` default true, no TLS. `sstableloader` without `-f` is unthrottled (`LoaderOptions.java:512-520`).

**B3b. Knobs.**

| Arm | Build | `JVM_EXTRA_OPTS` additions | What it tests |
|---|---|---|---|
| N0 | stock | — | the baseline, stock behaviour |
| N1 | probe | — | the probe with stock behaviour (should equal N0) and the operand at full speed |
| N2 | probe | `-Dasip.test.rebuffer_sleep_ms=2` | stock capacity, a slow consumer (the receiver lags the sender) |
| N3 | probe | `-Dasip.test.rebuffer_sleep_ms=2 -Dasip.test.capacity=8` | **the constraint lowered** from 2^31−1 to 8, with a slow consumer |
| P1 | probe | `-Dasip.test.rebuffer_sleep_ms=2 -Dasip.test.autoread=true` | positive control: flow control removed, stock capacity |
| P2 | probe | `-Dasip.test.rebuffer_sleep_ms=2 -Dasip.test.autoread=true -Dasip.test.capacity=64` | positive control: a reachable capacity binds |
| N2h (optional) | probe | as N2 | loads half the sstables (D/2): usage does not follow the volume |

- **Why 8:** it is far below the default but above the at most 2–3 elements (one read, the handshake leftover and the close sentinel) that flow control allows, so with flow control it must never be hit.
- **Why 64:** with flow control off, a lagging consumer reaches it within about 4 MiB of backlog per connection.
- **Why 2 ms:** it keeps each consumer at ≤ 64 KiB / 2 ms ≈ 32 MiB/s, well below an unthrottled loopback sender, so the receiver must lag.
- **Loader parallelism:** fixed at 2 with `-Dcassandra.streaming.session.parallelTransfers=2`, which gives at most about 3 inbound connections (1 control + 2 file).

**B3c. Workload.**
- **Data set, made once with the stock build:** `cassandra-stress write n=2000000 -col 'n=FIXED(1)' 'size=FIXED(1024)' -rate threads=32 -node 127.0.0.1`, then flush and snapshot, then copy to `$WORK/loader/keyspace1/standard1/`. Target size D = `du -sb` ≈ 2 GiB. If D < 1.5 GiB, append another `n=1000000` and redo the snapshot copy.
- **Per arm:** a fresh node; create the same schema (`cassandra-stress write n=1`); disable autocompaction; then `sstableloader -d 127.0.0.1 $WORK/loader/keyspace1/standard1`.
- **Arithmetic for the slow-consumer arms:**
  - With flow control, the receiver drains about 2 × 32 MiB/s, so a 2 GiB load takes ≥ 32 s. That is long enough for 1 Hz sampling, and the queue never holds more than about one read per connection.
  - For P1, the loopback sender pushes at ≥ several hundred MiB/s while the consumer takes about 64 MiB/s. The backlog therefore reaches roughly D × (1 − 64/send rate): ≥ 1 GiB at a 150 MiB/s sender, and ≥ D/4 = 512 MiB in every case where the sender is at least 85 MiB/s. That fits under the 4 GiB direct limit.
  - The default capacity (2^31−1 elements) is unreachable for any D: it would need ≥ 128 GiB even at 64-byte reads.
- **Duration:** at most 10 minutes per arm (`timeout 600`).

**B3d. Observables and instruments.**
- **Operand** (probe builds only): `ASIP-PROBE` lines in `$WORK/run/logs/system.log`, one a second, with `live` (open queues), `queued_bytes`, `max_queued_bytes`, `max_queue_size`, `ise` and the active settings.
- **Resource, the node's direct memory**, sampled at 1 Hz by the sampler script into `$WORK/results/<arm>/samples.tsv`:
  - (i) NMT `Other` committed (`jcmd <pid> VM.native_memory summary`): direct `ByteBuffer`s are accounted there on JDK 11;
  - (ii) every 5th sample, Cassandra's networking pool `UsedSize` and `OverflowSize`, and the JVM `java.nio:type=BufferPool,name=direct` `MemoryUsed`, through `nodetool sjk mx` (the metric names are at `BufferPoolMetrics.java:30-40`, scope `networking`);
  - (iii) process RSS (`ps -o rss= -p <pid>`).
- **Outcome:** `sstableloader` exit code and its last 20 lines; `nodetool tablestats keyspace1.standard1` "Space used (live)" after the load; `grep -c 'Queue full' system.log`; `grep 'exception occurred while in processing streaming data'`.
- **Not observable directly:** which connection a byte belongs to (the probe is node-wide), and the kernel socket buffers (they hold the backlog when flow control is on).

Sampler, saved as `$WORK/sampler.sh`:

```bash
#!/bin/bash
# usage: sampler.sh <cassandra_home> <pid> <outfile>
H=$1; PID=$2; OUT=$3; i=0
echo -e "epoch\tnmt_other_committed_kb\trss_kb\tnet_used\tnet_overflow\tnio_direct_used" > $OUT
while kill -0 $PID 2>/dev/null; do
  nmt=$(jcmd $PID VM.native_memory summary 2>/dev/null | grep -A1 -- '- *Other' | grep -o 'committed=[0-9]*KB' | head -1 | tr -dc 0-9)
  rss=$(ps -o rss= -p $PID | tr -d ' ')
  if (( i % 5 == 0 )); then
    nu=$($H/bin/nodetool -h 127.0.0.1 sjk mx -mg -b 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize' -f Value 2>/dev/null | tail -1)
    no=$($H/bin/nodetool -h 127.0.0.1 sjk mx -mg -b 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=OverflowSize' -f Value 2>/dev/null | tail -1)
    nd=$($H/bin/nodetool -h 127.0.0.1 sjk mx -mg -b 'java.nio:type=BufferPool,name=direct' -f MemoryUsed 2>/dev/null | tail -1)
  else nu=; no=; nd=; fi
  echo -e "$(date +%s)\t$nmt\t$rss\t$nu\t$no\t$nd" >> $OUT
  i=$((i+1)); sleep 1
done
```

**B3e. Procedure.**
1. **Preparation (once):**
   ```bash
   export WORK=/mydata/$USER/o181; mkdir -p $WORK/results $WORK/loader/keyspace1/standard1; chmod +x $WORK/sampler.sh
   start_node() {  # $1 = build dir, $2 = extra -D options
     rm -rf $WORK/run; mkdir -p $WORK/run/logs
     CASSANDRA_CONF=$WORK/conf CASSANDRA_LOG_DIR=$WORK/run/logs MAX_HEAP_SIZE=4G MAX_DIRECT_MEMORY_SIZE=4G \
     JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary $2" $1/bin/cassandra -p $WORK/run/cassandra.pid > $WORK/run/logs/start.out 2>&1
     for i in $(seq 120); do $1/bin/nodetool -h 127.0.0.1 status 2>/dev/null | grep -q '^UN' && return 0; sleep 2; done; return 1; }
   stop_node() { kill $(cat $WORK/run/cassandra.pid); for i in $(seq 60); do kill -0 $(cat $WORK/run/cassandra.pid) 2>/dev/null || return 0; sleep 1; done; kill -9 $(cat $WORK/run/cassandra.pid); }
   start_node $WORK/stock ""
   $WORK/stock/tools/bin/cassandra-stress write n=2000000 -col 'n=FIXED(1)' 'size=FIXED(1024)' -rate threads=32 -node 127.0.0.1 > $WORK/results/stress-prep.log 2>&1
   $WORK/stock/bin/nodetool -h 127.0.0.1 flush keyspace1 standard1
   $WORK/stock/bin/nodetool -h 127.0.0.1 snapshot -t o181 keyspace1
   find $WORK/run/data/keyspace1 -path '*snapshots/o181/*' -type f ! -name manifest.json ! -name schema.cql -exec cp {} $WORK/loader/keyspace1/standard1/ \;
   du -sb $WORK/loader/keyspace1/standard1   # = D; need >= 1.5 GiB
   stop_node
   ```
2. **For each arm A in N0, N1, N2, N3, P1, P2** (and optionally N2h, after moving half of the sstable generations, all components of each, into a second loader dir), with `B` = its build dir and `X` = its options from B3b:
   ```bash
   A=N2; B=$WORK/probe; X="-Dasip.test.rebuffer_sleep_ms=2"
   mkdir -p $WORK/results/$A
   start_node $B "$X"
   $WORK/stock/tools/bin/cassandra-stress write n=1 -rate threads=1 -node 127.0.0.1 > /dev/null 2>&1   # same schema
   $B/bin/nodetool -h 127.0.0.1 disableautocompaction keyspace1
   PID=$(cat $WORK/run/cassandra.pid)
   $WORK/sampler.sh $B $PID $WORK/results/$A/samples.tsv & SP=$!
   sleep 15                                       # baseline: the first ~15 samples
   date +%s > $WORK/results/$A/load_start
   JVM_OPTS="-Dcassandra.streaming.session.parallelTransfers=2" timeout 600 \
     $WORK/stock/bin/sstableloader -d 127.0.0.1 $WORK/loader/keyspace1/standard1 > $WORK/results/$A/loader.log 2>&1
   echo $? > $WORK/results/$A/loader_exit; date +%s > $WORK/results/$A/load_end
   sleep 15
   $B/bin/nodetool -h 127.0.0.1 tablestats keyspace1.standard1 > $WORK/results/$A/tablestats.txt
   $B/bin/nodetool -h 127.0.0.1 info > $WORK/results/$A/info.txt
   cp $WORK/run/logs/system.log $WORK/results/$A/
   grep ASIP-PROBE $WORK/run/logs/system.log | tail -3 > $WORK/results/$A/probe-last.txt
   grep -c 'Queue full' $WORK/run/logs/system.log > $WORK/results/$A/queue_full_count
   stop_node; wait $SP
   pgrep -u $USER -f 'CassandraDaemon|BulkLoader|org.apache.cassandra.stress' && echo LEFTOVER || echo clean
   ```
3. **Per arm, compute:**
   - the baseline, the median of NMT `Other` over the samples before `load_start`;
   - the peak, the maximum over [`load_start`, `load_end`+15 s];
   - Δ = peak − baseline, the same for networking `UsedSize` + `OverflowSize` and for `nio_direct_used`;
   - from the last `ASIP-PROBE` line: `max_queued_bytes`, `max_queue_size`, `ise`;
   - the load duration, `load_end` − `load_start`.

**B3f. Predictions** (before any run; L = the maximum `live` seen in the probe lines, expected ≤ 3):

| Arm | `max_queue_size` | `max_queued_bytes` | `ise` / Queue full | Δ direct (NMT Other, nio direct) | loader |
|---|---|---|---|---|---|
| N0 | n/a (no probe) | n/a | 0 | ≤ 64 MiB | exit 0; live space ≈ D |
| N1 | ≤ 3 | ≤ L × 2 × 65,536 (≤ 393,216) | 0 | within ±32 MiB of N0 | exit 0 |
| N2 | ≤ 3 | ≤ 393,216 | 0 | within ±32 MiB of N0 | exit 0; duration ≥ D / 64 MiB/s |
| N3 (C = 8) | ≤ 3 | ≤ 393,216, the same as N2 | 0 | within ±32 MiB of N2 | exit 0, the same duration as N2 ±20 % |
| N2h (D/2) | ≤ 3 | ≤ 393,216 | 0 | within ±32 MiB of N2 | exit 0, about half N2's duration |
| P1 | ≫ 64 (thousands) | ≥ 512 MiB (expected ≥ 1 GiB) | 0 | ≥ 512 MiB, tracking `max_queued_bytes` | exit 0 |
| P2 (C = 64) | = 64 | ≤ L × 64 × 65,536 (≤ 12 MiB) | ≥ 1; WARN "exception occurred while in processing streaming data" with `IllegalStateException: Queue full` | ≤ 64 MiB | non-zero exit or failed session; live space < D |

The claim is wrong if Δ direct or `max_queued_bytes` in N2 grows with D (N2 vs N2h) or reaches the P1 range, or if N3 differs from N2 (`ise` > 0, a failed load, or different memory).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| N1, N2, N3 and N2h all have Δ ≤ 64 MiB and `max_queued_bytes` ≤ about 400 KiB, while P1's Δ is ≥ 512 MiB | **Claim confirmed:** usage does not follow the capacity, the flow control bounds it, and the same workload moves usage once that is removed. |
| N2 `max_queued_bytes` or Δ grows with D (N2h ≈ half of N2), or reaches hundreds of MiB | **Claim refuted:** on a real node the queue is not read-on-demand. The capacity is the only cap, and at its default it is none, so usage does not follow it either, but for a different reason. Record that. |
| N3 `ise` > 0, a failed load, or lower Δ than N2 | **Claim refuted:** the capacity reaches the operand under normal flow control, so usage follows the constraint. |
| P1 Δ stays flat (< 64 MiB) or `max_queued_bytes` stays small | **Not confirmed:** the positive control did not move (e.g. the receiver kept up with the sender). Raise `rebuffer_sleep_ms` to 10 and repeat P1 and N2 before concluding. |
| P2 `ise` = 0 | **Not confirmed:** a reachable capacity did not bind. Check that the `-D` options reached the JVM (the probe line prints `capacity=64 autoread=true`). |
| N1 differs from N0 by more than ±32 MiB | The probe disturbs the node. Use N0 as the baseline and the probe lines only as the operand. |
| A probe line shows `live` > 3 | More connections than expected. Rescale the bound to L × 2 × 64 KiB; the claim holds if each queue stays at about one read. |

**B3h. Controls.**
- N0 against N1 shows that the probe build without properties behaves like stock.
- N2 against N3 changes only the constraint.
- N2 against N2h changes only the volume.
- P1 is the positive control: the same workload, the same capacity, flow control removed. It shows the instruments see queue growth when it happens.
- P2 shows that a capacity binds when reachable, through the very `add` at :75.
- Autocompaction is disabled and nothing else runs on the node, so the networking pool sees only streaming. The baseline is taken on the same JVM just before the load.
- Every arm starts from an empty `$WORK/run`.

**B4. Risks and cleanup.**
- **Disk:**
  - everything is under `$WORK` on local disk: two source copies with builds (about 2 × 3 GiB), the loader set (about 2 GiB), and per arm about 2 GiB of data plus the commit log;
  - `$WORK/run` is wiped at the start of each arm;
  - nothing goes to shared storage or to the shared tree `~/cassandra-5.0.9`, which is only read by `rsync`.
- **Memory:** P1 deliberately holds up to about 2 GiB of direct memory, capped by `MAX_DIRECT_MEMORY_SIZE=4G`. Run it on a node with at least 16 GiB of free RAM.
- **Ports:** if 7000, 9042 or 7199 are busy:
  - set `storage_port`, `native_transport_port` (yaml) and the seed port in `$WORK/conf/cassandra.yaml`;
  - change `JMX_PORT="7199"` in `$WORK/conf/cassandra-env.sh:235`;
  - add `-p <jmx>` to `nodetool`, `-port native=<n>` to stress, and `-p <native> -sp <storage>` to `sstableloader`.
- **Processes:**
  - after every arm, `pgrep -u $USER -f 'CassandraDaemon|BulkLoader|org.apache.cassandra.stress'` must print nothing, and `stop_node` escalates to `kill -9` after 60 s;
  - the sampler exits when the node PID dies;
  - the unit tier's test JVM exits with `ant`, so check `pgrep -u $USER -f JUnitTestRunner`.
- **Final cleanup:** `rm -rf $WORK/run $WORK/loader` and, once results are copied, `rm -rf $WORK`.

## C. Sources read

src/java/org/apache/cassandra/net/AsyncStreamingInputPlus.java
src/java/org/apache/cassandra/utils/concurrent/BlockingQueues.java
src/java/org/apache/cassandra/streaming/async/NettyStreamingChannel.java
src/java/org/apache/cassandra/streaming/async/NettyStreamingConnectionFactory.java
src/java/org/apache/cassandra/streaming/async/StreamingMultiplexedChannel.java
src/java/org/apache/cassandra/streaming/StreamDeserializingTask.java
src/java/org/apache/cassandra/net/InboundConnectionInitiator.java
src/java/org/apache/cassandra/net/OutboundConnectionInitiator.java
src/java/org/apache/cassandra/net/SocketFactory.java
src/java/org/apache/cassandra/net/BufferPoolAllocator.java
src/java/org/apache/cassandra/net/GlobalBufferPoolAllocator.java
src/java/org/apache/cassandra/utils/memory/BufferPools.java
src/java/org/apache/cassandra/utils/memory/BufferPool.java
src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
src/java/org/apache/cassandra/io/sstable/SSTableZeroCopyWriter.java
src/java/org/apache/cassandra/streaming/compress/StreamCompressionInputStream.java
src/java/org/apache/cassandra/tools/BulkLoader.java
src/java/org/apache/cassandra/tools/LoaderOptions.java
src/java/org/apache/cassandra/tools/nodetool/Info.java
test/unit/org/apache/cassandra/net/AsyncStreamingInputPlusTest.java
conf/cassandra.yaml
conf/cassandra-env.sh
conf/jvm-server.options
conf/jvm11-server.options
bin/cassandra.in.sh
bin/sstableloader
tools/bin/cassandra-stress
build.xml
.build/parent-pom-template.xml
.build/checkstyle.xml
.build/checkstyle_test.xml
https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html
https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/AbstractQueue.html
https://netty.io/4.1/api/io/netty/channel/ChannelConfig.html
https://netty.io/4.1/api/io/netty/channel/AdaptiveRecvByteBufAllocator.html
https://github.com/netty/netty/blob/4.1/transport/src/main/java/io/netty/channel/DefaultMaxMessagesRecvByteBufAllocator.java

(The JDK and Netty URLs are cited from library documentation; they were not fetched in this session.)

## D. Stage-4 feedback

none yet
