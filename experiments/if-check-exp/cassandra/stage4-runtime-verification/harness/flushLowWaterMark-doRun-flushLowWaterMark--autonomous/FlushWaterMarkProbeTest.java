/*
 * Stage-4 harness, unit tier (B2) of the case file flushLowWaterMark-doRun-flushLowWaterMark--autonomous
 * (frozen sha256 f754e36f...). Not part of upstream Cassandra. Copy into test/unit/org/apache/cassandra/net/ of a clone at
 * cassandra-5.0.9 and run with ant testsome -Dtest.name=org.apache.cassandra.net.FlushWaterMarkProbeTest -Dtest.methods=...
 *
 * handshake  step-1 instrument check (B2d end / amendment A1): connect through the PausableProxy, deliver one message,
 *            read back the template and the established settings. Records no reading of B2f.
 * sweep      B2b-B2e: S0 (stock), L-set (H = 1 MiB; L = 1024, 32768, 524288, 1040384), P-set (H = 64 KiB, 1 MiB, 8 MiB;
 *            L = H/2), three repetitions; one CSV row per run (-Dstage4.csv) and one "PROBE" line per run on stdout.
 * The R instrument follows amendment A2 (flip in the listener detected from the call stack plus the inferred pre-listener
 * isWritable, with consistency counters).
 * The test does not fail on a prediction miss (the readings are the result); it fails only on an exception or a timeout.
 */
package org.apache.cassandra.net;

import java.io.Closeable;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Supplier;
import java.util.function.ToLongFunction;

import org.junit.AfterClass;
import org.junit.BeforeClass;
import org.junit.Test;

import io.netty.channel.Channel;
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

import static java.util.concurrent.TimeUnit.MINUTES;
import static java.util.concurrent.TimeUnit.SECONDS;
import static org.apache.cassandra.net.MessagingService.current_version;
import static org.apache.cassandra.utils.Clock.Global.nanoTime;

public class FlushWaterMarkProbeTest
{
    static final SocketFactory factory = new SocketFactory();
    static PrintWriter csv;
    static Supplier<? extends IVersionedAsymmetricSerializer<?, ?>> origSerializer;
    static Supplier<? extends IVerbHandler<?>> origHandler;
    static ToLongFunction<TimeUnit> origExpiration;
    static final AtomicLong handled = new AtomicLong();

    /** B2c: a Long payload written 128 times = 1024 B. */
    static final IVersionedSerializer<Long> LONGS = new IVersionedSerializer<Long>()
    {
        public void serialize(Long v, DataOutputPlus o, int ver) throws IOException { for (int i = 0; i < 128; i++) o.writeLong(v); }
        public Long deserialize(DataInputPlus in, int ver) throws IOException { long v = 0; for (int i = 0; i < 128; i++) v = in.readLong(); return v; }
        public long serializedSize(Long v, int ver) { return 1024; }
    };

    @BeforeClass
    public static void up() throws Throwable
    {
        DatabaseDescriptor.daemonInitialization();
        CommitLog.instance.start();
        origSerializer = Verb._TEST_1.unsafeSetSerializer(() -> LONGS);
        origHandler = Verb._TEST_1.unsafeSetHandler(() -> m -> handled.incrementAndGet());
        origExpiration = Verb._TEST_1.unsafeSetExpiration(u -> u.convert(10, MINUTES));
        String f = System.getProperty("stage4.csv");
        if (f != null)
        {
            boolean fresh = !new java.io.File(f).exists();
            csv = new PrintWriter(new FileWriter(f, true));
            if (fresh)
                csv.println("set,H,L,rep,S,N,U,P,writableAtStable,stableMs,nR,maxR,medR,minR,nResumeSend,maxResumeSend,medResumeSend,"
                            + "flips,guardMiss,inferErr,syncSent,asyncSent,failed,peakPre,enqueued,handled,drainMs,"
                            + "templateH,templateL,establishedH,establishedL,U0,usedStable,messageSize,messagingVersion");
            csv.flush();
        }
        line("STAGE4 info FlushWaterMarkProbeTest start; current_version=" + current_version
             + " LARGE_MESSAGE_THRESHOLD=" + OutboundConnections.LARGE_MESSAGE_THRESHOLD
             + " networkingPoolThreshold=" + BufferPools.forNetworking().memoryUsageThreshold()
             + " maxHeap=" + Runtime.getRuntime().maxMemory());
    }

    @AfterClass
    public static void down() throws Throwable
    {
        Verb._TEST_1.unsafeSetSerializer(origSerializer);
        Verb._TEST_1.unsafeSetHandler(origHandler);
        Verb._TEST_1.unsafeSetExpiration(origExpiration);
        if (csv != null) csv.close();
        factory.shutdownNow();
    }

    static synchronized void line(String s)
    {
        System.out.println(s);
        System.out.flush();
    }

    static Object get(Object o, String f) throws Exception
    {
        Class<?> c = o.getClass();
        while (true)
        {
            try { Field x = c.getDeclaredField(f); x.setAccessible(true); return x.get(o); }
            catch (NoSuchFieldException e) { c = c.getSuperclass(); if (c == null) throw e; }
        }
    }

    static void setInt(Object o, String f, int v) throws Exception
    {
        Field x = OutboundConnectionSettings.class.getDeclaredField(f);
        x.setAccessible(true);
        x.setInt(o, v);
    }

    /** B2c: an in-test TCP proxy; while paused the forward pump does not read from the outbound side. */
    static final class PausableProxy implements Closeable
    {
        final ServerSocket server = new ServerSocket();
        final InetSocketAddress target;
        volatile boolean paused;
        volatile int sleepMsPerChunk;
        final ExecutorService ex = Executors.newCachedThreadPool();
        final List<Socket> socks = new CopyOnWriteArrayList<>();
        final AtomicLong forwarded = new AtomicLong();

        PausableProxy(InetSocketAddress target) throws IOException
        {
            this.target = target;
            server.setReceiveBufferSize(4096);
            server.bind(new InetSocketAddress("127.0.0.1", 0));
            ex.submit(this::accept);
        }

        int port() { return server.getLocalPort(); }

        void accept()
        {
            try
            {
                while (!server.isClosed())
                {
                    Socket a = server.accept();
                    Socket b = new Socket();
                    b.connect(target);
                    socks.add(a); socks.add(b);
                    ex.submit(() -> pump(a, b, true));
                    ex.submit(() -> pump(b, a, false));
                }
            }
            catch (IOException ignore) {}
        }

        void pump(Socket from, Socket to, boolean fwd)
        {
            byte[] buf = new byte[4096];
            try
            {
                InputStream in = from.getInputStream();
                OutputStream out = to.getOutputStream();
                while (true)
                {
                    if (fwd) while (paused) Thread.sleep(1);
                    int n = in.read(buf);
                    if (n < 0) break;
                    out.write(buf, 0, n);
                    out.flush();
                    if (fwd) forwarded.addAndGet(n);
                    if (fwd && sleepMsPerChunk > 0) Thread.sleep(sleepMsPerChunk);
                }
            }
            catch (Exception ignore) {}
        }

        public void close() throws IOException
        {
            server.close();
            for (Socket s : socks) s.close();
            ex.shutdownNow();
        }
    }

    /**
     * Amendment A2: all callbacks run on the connection's event loop (single-threaded), so plain fields suffice.
     * Each doRun sends exactly one frame (onSendSmallFrame); a synchronous completion calls onSentSmallFrame from doRun
     * itself (OutboundConnection.java:847), an asynchronous one from the listener lambda (:881), after :866-875.
     */
    static final class Resume implements OutboundDebugCallbacks
    {
        volatile Object delivery;
        int H, L;
        boolean trackedW = true;          // isWritable as inferred after the last observed event
        boolean pendingSend; int pendF0, pendBytes;
        final List<Integer> R = new ArrayList<>(), resumeSend = new ArrayList<>();
        boolean awaitingResumeSend;
        int flips, guardMiss, inferErr, syncSent, asyncSent, failed, sendNotWritable, peakPre;

        int f() throws Exception { return (Integer) get(delivery, "flushingBytes"); }
        boolean w() throws Exception { return (Boolean) get(delivery, "isWritable"); }

        /** a send not followed by its own synchronous completion was asynchronous: apply :851/:854 */
        void settlePendingSend()
        {
            if (!pendingSend) return;
            pendingSend = false;
            trackedW = pendF0 + pendBytes < H;
        }

        public void onSendSmallFrame(int c, int b)
        {
            if (delivery == null) return;
            try
            {
                settlePendingSend();
                int f0 = f();
                if (!w()) sendNotWritable++;
                if (awaitingResumeSend) { resumeSend.add(f0); awaitingResumeSend = false; }
                pendingSend = true; pendF0 = f0; pendBytes = b;
            }
            catch (Exception e) { throw new RuntimeException(e); }
        }

        public void onSentSmallFrame(int c, int b)
        {
            if (delivery == null) return;
            try
            {
                String caller = StackWalker.getInstance().walk(s -> s.skip(1).findFirst().map(StackWalker.StackFrame::getMethodName).orElse(""));
                boolean async = caller.startsWith("lambda$");
                int fNow = f(); boolean wNow = w();
                if (!async)
                {
                    syncSent++;
                    pendingSend = false;          // the frame just sent completed synchronously; flushingBytes unchanged
                    trackedW = wNow;
                    return;
                }
                asyncSent++;
                settlePendingSend();
                boolean wBefore = trackedW;
                peakPre = Math.max(peakPre, fNow + b);
                if (wBefore && !wNow) inferErr++;                 // a listener never sets isWritable false
                if (!wBefore && wNow) { flips++; R.add(fNow); awaitingResumeSend = true; }
                if (!wBefore && !wNow && fNow <= L) guardMiss++;  // :871 should have fired
                trackedW = wNow;
            }
            catch (Exception e) { throw new RuntimeException(e); }
        }

        public void onFailedSmallFrame(int c, int b) { failed++; }
        public void onConnect(int v, OutboundConnectionSettings s) {}
    }

    static <T> T onLoop(EventLoop loop, Callable<T> c) throws Exception
    {
        return loop.submit(c).get(10, SECONDS);
    }

    static long medianUsed() throws InterruptedException
    {
        long[] v = new long[20];
        for (int i = 0; i < 20; i++) { v[i] = BufferPools.forNetworking().usedSizeInBytes(); Thread.sleep(5); }
        java.util.Arrays.sort(v);
        return (v[9] + v[10]) / 2;
    }

    static String stats(List<Integer> l)
    {
        if (l.isEmpty()) return "0,,,";
        List<Integer> s = new ArrayList<>(l); Collections.sort(s);
        return s.size() + "," + s.get(s.size() - 1) + "," + s.get(s.size() / 2) + "," + s.get(0);
    }

    static boolean waitFor(Callable<Boolean> c, long ms) throws Exception
    {
        long end = System.currentTimeMillis() + ms;
        while (System.currentTimeMillis() < end)
        {
            if (c.call()) return true;
            Thread.sleep(10);
        }
        return c.call();
    }

    static final class Rig implements Closeable
    {
        InboundSockets inbound; PausableProxy proxy; OutboundConnection out; Resume cb = new Resume(); EventLoop loop;
        OutboundConnectionSettings template, established;

        Rig(int H, int L, boolean reflect) throws Throwable
        {
            InetAddressAndPort ep = FBUtilities.getBroadcastAddressAndPort();
            inbound = new InboundSockets(Collections.singletonList(new InboundConnectionSettings().withBindAddress(ep).withSocketFactory(factory)));
            inbound.open().sync();
            proxy = new PausableProxy(new InetSocketAddress(ep.getAddress(), ep.getPort()));
            OutboundConnectionSettings s = new OutboundConnectionSettings(ep)
                .withConnectTo(InetAddressAndPort.getByAddressOverrideDefaults(InetAddress.getByName("127.0.0.1"), proxy.port()))
                .withFraming(OutboundConnectionSettings.Framing.CRC).withSocketSendBufferSizeInBytes(4096)
                .withApplicationSendQueueCapacityInBytes(64 << 20).withDefaultReserveLimits()
                .withSocketFactory(factory).withDebugCallbacks(cb);
            if (reflect) { setInt(s, "flushHighWaterMark", H); setInt(s, "flushLowWaterMark", L); }
            ResourceLimits.EndpointAndGlobal reserve = new ResourceLimits.EndpointAndGlobal(
                new ResourceLimits.Concurrent(s.applicationSendQueueReserveEndpointCapacityInBytes), s.applicationSendQueueReserveGlobalCapacityInBytes);
            out = new OutboundConnection(ConnectionType.SMALL_MESSAGES, s, reserve);
            template = (OutboundConnectionSettings) get(out, "template");
            loop = (EventLoop) get(out, "eventLoop");
            cb.H = template.flushHighWaterMark; cb.L = template.flushLowWaterMark;
        }

        /** B2e/B2c step 1: one message through the proxy; returns true if it was handled within 10 s */
        boolean connect() throws Exception
        {
            long before = handled.get();
            out.enqueue(Message.out(Verb._TEST_1, 1L, nanoTime() + MINUTES.toNanos(10)));
            boolean ok = waitFor(() -> handled.get() > before, 10_000);
            Object state = get(out, "state");
            if (state.getClass().getSimpleName().equals("Established"))
                established = (OutboundConnectionSettings) get(state, "settings");
            cb.delivery = get(out, "delivery");
            return ok;
        }

        public void close()
        {
            try { out.close(false).get(30, SECONDS); } catch (Throwable t) { line("STAGE4 info close outbound " + t); }
            try { proxy.close(); } catch (Throwable t) { line("STAGE4 info close proxy " + t); }
            try { inbound.close().get(30, SECONDS); } catch (Throwable t) { line("STAGE4 info close inbound " + t); }
        }
    }

    /** Step-1 instrument check (not a reading of B2f): the handshake and one message go through the TCP proxy. */
    @Test
    public void handshake() throws Throwable
    {
        try (Rig r = new Rig(65536, 32768, false))
        {
            boolean ok = r.connect();
            line("STAGE4 handshake through proxy: delivered=" + ok + " proxyForwardedBytes=" + r.proxy.forwarded.get()
                 + " state=" + get(r.out, "state").getClass().getSimpleName()
                 + " template(H,L)=(" + r.template.flushHighWaterMark + "," + r.template.flushLowWaterMark + ")"
                 + " established(H,L)=" + (r.established == null ? "null" : "(" + r.established.flushHighWaterMark + "," + r.established.flushLowWaterMark + ")")
                 + " connectTo=" + r.template.connectTo + " framing=" + r.template.framing
                 + " channel=" + get(get(r.out, "state"), "channel"));
            if (!ok) throw new AssertionError("handshake/message did not go through the proxy");
        }
    }

    void runOne(String set, int H, int L, boolean reflect, int rep) throws Throwable
    {
        Rig r = new Rig(H, L, reflect);
        try
        {
            if (!r.connect()) throw new AssertionError("connect failed " + set + " H=" + H + " L=" + L + " rep=" + rep);
            Channel ch = (Channel) get(get(r.out, "state"), "channel");
            long U0 = medianUsed();
            r.proxy.paused = true;
            Thread.sleep(200);
            int n = (int) ((2L * H + (2 << 20) + 1023) / 1024);
            long base = handled.get();
            int messageSize = Message.out(Verb._TEST_1, 1L).serializedSize(current_version);
            for (int i = 0; i < n; i++)
                r.out.enqueue(Message.out(Verb._TEST_1, (long) i, nanoTime() + MINUTES.toNanos(10)));
            // step 5: every 10 ms read (flushingBytes, isWritable) on the event loop; stable = unchanged 2 s and !isWritable
            long t0 = System.currentTimeMillis(), lastChange = t0; int last = -1; boolean w = true; boolean stable = false;
            while (System.currentTimeMillis() - t0 < 60_000)
            {
                int[] fw = onLoop(r.loop, () -> new int[]{ r.cb.f(), r.cb.w() ? 1 : 0 });
                long now = System.currentTimeMillis();
                if (fw[0] != last) { last = fw[0]; lastChange = now; }
                w = fw[1] == 1;
                if (!w && now - lastChange >= 2000) { stable = true; break; }
                Thread.sleep(10);
            }
            long stableMs = System.currentTimeMillis() - t0;
            int S = onLoop(r.loop, () -> r.cb.f());
            boolean wS = onLoop(r.loop, () -> r.cb.w());
            long N = onLoop(r.loop, () -> ch.unsafe().outboundBuffer() == null ? -1L : ch.unsafe().outboundBuffer().totalPendingWriteBytes());
            long usedStable = medianUsed();
            long U = usedStable - U0;
            long P = r.out.pendingBytes();
            if (!stable) line("STAGE4 info never stalled " + set + " H=" + H + " L=" + L + " rep=" + rep);
            // step 7: resume, throttled
            r.proxy.sleepMsPerChunk = 1;
            r.proxy.paused = false;
            long td = System.currentTimeMillis();
            boolean all = waitFor(() -> handled.get() - base >= n, 120_000);
            long drainMs = System.currentTimeMillis() - td;
            Resume cb = r.cb;
            String row = set + "," + H + "," + L + "," + rep + "," + S + "," + N + "," + U + "," + P + "," + wS + "," + stableMs + ","
                         + stats(cb.R) + "," + statsNoMin(cb.resumeSend) + "," + cb.flips + "," + cb.guardMiss + "," + cb.inferErr + ","
                         + cb.syncSent + "," + cb.asyncSent + "," + cb.failed + "," + cb.peakPre + "," + n + "," + (handled.get() - base) + ","
                         + drainMs + "," + r.template.flushHighWaterMark + "," + r.template.flushLowWaterMark + ","
                         + (r.established == null ? "" : r.established.flushHighWaterMark) + ","
                         + (r.established == null ? "" : r.established.flushLowWaterMark) + "," + U0 + "," + usedStable + "," + messageSize
                         + "," + current_version;
            line("PROBE " + row + " sendNotWritable=" + cb.sendNotWritable + " allHandled=" + all + " R=" + cb.R
                 + " resumeSend=" + cb.resumeSend);
            if (csv != null) { csv.println(row); csv.flush(); }
            if (!all) throw new AssertionError("not all messages handled " + set + " H=" + H + " L=" + L + " rep=" + rep);
        }
        finally
        {
            r.close();
        }
    }

    static String statsNoMin(List<Integer> l)
    {
        if (l.isEmpty()) return "0,,";
        List<Integer> s = new ArrayList<>(l); Collections.sort(s);
        return s.size() + "," + s.get(s.size() - 1) + "," + s.get(s.size() / 2);
    }

    @Test
    public void sweep() throws Throwable
    {
        for (int rep = 0; rep < 3; rep++)
        {
            runOne("S0", 65536, 32768, false, rep);
            for (int L : new int[]{ 1024, 32768, 524288, 1040384 }) runOne("L", 1048576, L, true, rep);
            for (int H : new int[]{ 65536, 1048576, 8388608 }) runOne("P", H, H / 2, true, rep);
        }
    }
}
