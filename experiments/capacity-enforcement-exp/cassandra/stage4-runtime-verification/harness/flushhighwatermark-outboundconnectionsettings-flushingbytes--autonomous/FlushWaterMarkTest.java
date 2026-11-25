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
