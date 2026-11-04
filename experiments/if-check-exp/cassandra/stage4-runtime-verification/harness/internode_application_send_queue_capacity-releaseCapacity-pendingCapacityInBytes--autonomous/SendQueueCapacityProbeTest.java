/*
 * Stage-4 harness, unit tier (B2) of the case file
 * internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous (frozen sha256 658ca786...).
 * Not part of upstream Cassandra. Copy into test/unit/org/apache/cassandra/net/ of a clone at cassandra-5.0.9.
 *
 * u1Accounting   B2c/B2f U1 and U1-stress (amendment A1): C = 64 KiB, 1 MiB, 4 MiB; R_e = 256 KiB; R_g = 1 MiB.
 * u2HeapConnected B2c/B2f U2 and the B2h M = 0 control: C = 8, 32, 128 MiB; R_e = R_g = 1 MiB; a connected peer whose
 *                 delivery is blocked by holding the queue lock in the test thread.
 * u3FailingToConnect B2c/B2f U3 (amendment A3): C = 8, 32 MiB; a loopback port nothing listens on.
 * Every reading is one "PROBE ..." line; every assertion one "STAGE4 check <name> <expected> <actual> ok|MISMATCH" line
 * (stdout and the file named by -Dstage4.out). The test does not fail on a mismatch (the readings are the result); it
 * fails only on an exception, so that a mutant's exception is visible as a failure.
 */
package org.apache.cassandra.net;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.commitlog.CommitLog;
import org.apache.cassandra.io.IVersionedAsymmetricSerializer;
import org.apache.cassandra.io.IVersionedSerializer;
import org.apache.cassandra.io.util.DataInputPlus;
import org.apache.cassandra.io.util.DataOutputPlus;
import org.apache.cassandra.locator.InetAddressAndPort;
import org.apache.cassandra.net.ResourceLimits.Concurrent;
import org.apache.cassandra.net.ResourceLimits.EndpointAndGlobal;
import org.apache.cassandra.utils.FBUtilities;

import static java.util.concurrent.TimeUnit.MINUTES;
import static java.util.concurrent.TimeUnit.SECONDS;
import static org.apache.cassandra.net.MessagingService.current_version;
import static org.apache.cassandra.utils.Clock.Global.nanoTime;

public class SendQueueCapacityProbeTest
{
    static final SocketFactory factory = new SocketFactory();
    static PrintWriter out;
    static int mismatches = 0;
    static final int P = 16384;
    static Supplier<? extends IVersionedAsymmetricSerializer<?, ?>> origSerializer;
    static Supplier<? extends IVerbHandler<?>> origHandler;

    static final IVersionedSerializer<byte[]> BYTES = new IVersionedSerializer<byte[]>()
    {
        public void serialize(byte[] b, DataOutputPlus o, int v) throws IOException { o.writeInt(b.length); o.write(b); }
        public byte[] deserialize(DataInputPlus in, int v) throws IOException { byte[] b = new byte[in.readInt()]; in.readFully(b); return b; }
        public long serializedSize(byte[] b, int v) { return 4 + b.length; }
    };

    @BeforeClass
    public static void up() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        CommitLog.instance.start();
        String f = System.getProperty("stage4.out");
        if (f != null)
            out = new PrintWriter(new FileWriter(f, true));
        origSerializer = Verb._TEST_1.unsafeSetSerializer(() -> BYTES);
        origHandler = Verb._TEST_1.unsafeSetHandler(() -> m -> {});
        line("STAGE4 info SendQueueCapacityProbeTest start; current_version=" + current_version
             + " maxMessage=" + DatabaseDescriptor.getInternodeMaxMessageSizeInBytes()
             + " maxHeap=" + Runtime.getRuntime().maxMemory()
             + " gc=" + ManagementFactory.getGarbageCollectorMXBeans().get(0).getName());
    }

    @AfterClass
    public static void down() throws Exception
    {
        Verb._TEST_1.unsafeSetSerializer(origSerializer);
        Verb._TEST_1.unsafeSetHandler(origHandler);
        line("STAGE4 info SendQueueCapacityProbeTest end; mismatches=" + mismatches);
        if (out != null)
            out.close();
        factory.shutdownNow();
    }

    static synchronized void line(String s)
    {
        System.out.println(s);
        if (out != null) { out.println(s); out.flush(); }
    }

    static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        if (!ok) mismatches++;
        line("STAGE4 check " + name.replace(' ', '_') + " " + expected + " " + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    static void checkTrue(String name, boolean cond, String detail)
    {
        if (!cond) mismatches++;
        line("STAGE4 check " + name.replace(' ', '_') + " true " + cond + " " + (cond ? "ok" : "MISMATCH") + " [" + detail + "]");
    }

    static OutboundConnection newOut(InetAddressAndPort to, int C, int Re, Concurrent g)
    {
        OutboundConnectionSettings t = new OutboundConnectionSettings(to)
                                       .withApplicationSendQueueCapacityInBytes(C)
                                       .withApplicationReserveSendQueueCapacityInBytes(Re, g)
                                       .withSocketFactory(factory)
                                       .withDefaults(ConnectionCategory.MESSAGING);
        return new OutboundConnection(ConnectionType.SMALL_MESSAGES, t, new EndpointAndGlobal(new Concurrent(Re), g));
    }

    static long usedAfterGc() throws InterruptedException
    {
        for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(200); }
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    /** Diagnostic only (added 2026-10-21 after run 1's unit readings; does not change any reading): with
     *  -Dstage4.histo=<dir>, a class histogram of this JVM (jcmd GC.class_histogram, which itself runs a full GC) is
     *  written at U2's heap reading. Off by default. */
    static void histo(String tag)
    {
        String dir = System.getProperty("stage4.histo");
        if (dir == null) return;
        try
        {
            long pid = ProcessHandle.current().pid();
            new ProcessBuilder("jcmd", Long.toString(pid), "GC.class_histogram")
                .redirectOutput(new java.io.File(dir, "histo-" + tag + ".txt")).redirectErrorStream(true).start().waitFor();
            line("STAGE4 info histogram " + tag + " written; heapUsedNow=" + ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed());
        }
        catch (Exception e) { line("STAGE4 info histogram failed " + e); }
    }

    static String st(OutboundConnection o, Concurrent g)
    {
        return "pending=" + o.pendingBytes() + " count=" + o.pendingCount() + " endpointUsing=" + o.unsafeGetEndpointReserveLimits().using()
               + " globalUsing=" + g.using() + " overloaded=" + o.overloadedCount() + " overloadedBytes=" + o.overloadedBytes();
    }

    static Message<byte[]> bulk()
    {
        return Message.out(Verb._TEST_1, new byte[P], nanoTime() + MINUTES.toNanos(10));
    }

    static InetAddressAndPort deadPort() throws IOException
    {
        int port;
        try (ServerSocket s = new ServerSocket(0, 1, InetAddress.getLoopbackAddress())) { port = s.getLocalPort(); }
        return InetAddressAndPort.getByAddressOverrideDefaults(InetAddress.getLoopbackAddress(), port);
    }

    /** U1 and U1-stress. The peer is a dead port: the link never connects, and no acquire beyond C is attempted before the
     *  first enqueue, so isFailingToConnect is false (state Disconnected: setDisconnected() in the constructor). */
    @Test
    public void u1Accounting() throws Throwable
    {
        final int S = 1000, Re = 262144, Rg = 1048576;
        int[] Cs = { 65536, 1048576, 4194304 };
        long[] expN = { 327, 1310, 4456 };
        for (int ci = 0; ci < Cs.length; ci++)
        {
            int C = Cs[ci];
            Concurrent g = new Concurrent(Rg);
            OutboundConnection o = newOut(deadPort(), C, Re, g);
            try
            {
                long n = 0;
                while (o.unsafeAcquireCapacity(S)) n++;
                long ep = o.unsafeGetEndpointReserveLimits().using();
                line("PROBE U1-full C=" + C + " successes=" + n + " " + st(o, g));
                check("U1 C=" + C + " successes", expN[ci], n);
                check("U1 C=" + C + " pending at first failure", expN[ci] * S, o.pendingBytes());
                check("U1 C=" + C + " endpointUsing", expN[ci] * S - C, ep);
                check("U1 C=" + C + " globalUsing", ep, g.using());
                int bad = 0; long zeroAt = -1;
                for (long i = 0; i < n; i++)
                {
                    o.unsafeReleaseCapacity(S);
                    long p = o.pendingBytes(), e = o.unsafeGetEndpointReserveLimits().using(), gu = g.using();
                    if (e != Math.max(0, p - C) || gu != e) { bad++; if (bad <= 5) line("PROBE U1-release-violation C=" + C + " pending=" + p + " endpoint=" + e + " global=" + gu); }
                    if (zeroAt < 0 && e == 0) zeroAt = p;
                }
                line("PROBE U1-released C=" + C + " violations=" + bad + " endpointFirstZeroAtPending=" + zeroAt + " " + st(o, g));
                check("U1 C=" + C + " release-step violations of endpoint==max(0,pending-C)==global", 0, bad);
                checkTrue("U1 C=" + C + " endpoint reaches 0 exactly when pending first drops to <= C", zeroAt >= 0 && zeroAt <= C && zeroAt > C - S, "pendingAtZero=" + zeroAt);
                check("U1 C=" + C + " final pending,endpoint,global", "0,0,0", o.pendingBytes() + "," + o.unsafeGetEndpointReserveLimits().using() + "," + g.using());

                stress(o, g, C, Re);
            }
            finally
            {
                o.close(false).get(30, SECONDS);
            }
        }
        Assert.assertTrue(true);
    }

    static void stress(OutboundConnection o, Concurrent g, int C, int Re) throws Throwable
    {
        final int T = 16, CYCLES = 200;
        CyclicBarrier b = new CyclicBarrier(T + 1);
        AtomicReference<Throwable> err = new AtomicReference<>();
        List<Thread> ts = new ArrayList<>();
        for (int t = 0; t < T; t++)
        {
            Thread th = new Thread(() -> {
                try
                {
                    for (int c = 0; c < CYCLES; c++)
                    {
                        List<Integer> got = new ArrayList<>();
                        while (true)
                        {
                            int sz = ThreadLocalRandom.current().nextInt(1, 4097);
                            if (!o.unsafeAcquireCapacity(sz)) break;
                            got.add(sz);
                        }
                        b.await();   // acquire phase over
                        b.await();   // main has checked
                        for (int sz : got) o.unsafeReleaseCapacity(sz);
                        b.await();   // release phase over
                        b.await();   // main has checked
                    }
                }
                catch (Throwable e) { err.compareAndSet(null, e); b.reset(); }
            }, "stage4-u1stress-" + t);
            th.start();
            ts.add(th);
        }
        int barrierBad = 0, bandBad = 0, zeroBad = 0;
        long minTotal = Long.MAX_VALUE, maxTotal = Long.MIN_VALUE, first = -1, last = -1;
        for (int c = 0; c < CYCLES; c++)
        {
            b.await();
            long p = o.pendingBytes(), e = o.unsafeGetEndpointReserveLimits().using(), gu = g.using();
            if (p > C + Re || e != Math.max(0, p - C) || gu != e) { barrierBad++; if (barrierBad <= 5) line("PROBE U1-stress-barrier-violation C=" + C + " cycle=" + c + " pending=" + p + " endpoint=" + e + " global=" + gu); }
            if (p < (long) C + Re - 4095 || p > (long) C + Re) { bandBad++; if (bandBad <= 5) line("PROBE U1-stress-band-violation C=" + C + " cycle=" + c + " total=" + p); }
            minTotal = Math.min(minTotal, p); maxTotal = Math.max(maxTotal, p);
            if (c == 0) first = p;
            last = p;
            b.await();
            b.await();
            long p2 = o.pendingBytes(), e2 = o.unsafeGetEndpointReserveLimits().using(), g2 = g.using();
            if (p2 != 0 || e2 != 0 || g2 != 0) { zeroBad++; if (zeroBad <= 5) line("PROBE U1-stress-zero-violation C=" + C + " cycle=" + c + " pending=" + p2 + " endpoint=" + e2 + " global=" + g2); }
            b.await();
        }
        for (Thread th : ts) th.join(60000);
        if (err.get() != null) throw err.get();
        line("PROBE U1-stress C=" + C + " cycles=" + CYCLES + " threads=" + T + " totalMin=" + minTotal + " totalMax=" + maxTotal
             + " totalFirst=" + first + " totalLast=" + last + " band=[" + (C + Re - 4095) + "," + (C + Re) + "]"
             + " barrierViolations=" + barrierBad + " bandViolations=" + bandBad + " nonZeroAfterRelease=" + zeroBad);
        check("U1-stress C=" + C + " barrier violations (pending<=C+Re, endpoint==max(0,pending-C)==global)", 0, barrierBad);
        check("U1-stress C=" + C + " cycles with total outside [C+Re-4095, C+Re]", 0, bandBad);
        check("U1-stress C=" + C + " cycles not back to 0,0,0 after release", 0, zeroBad);
    }

    /** U2 and the B2h M = 0 control. */
    @Test
    public void u2HeapConnected() throws Throwable
    {
        InetAddressAndPort ep = FBUtilities.getBroadcastAddressAndPort();
        int R = 1 << 20;
        int[] Cs = { 8 << 20, 8 << 20, 32 << 20, 128 << 20 };
        boolean[] control = { true, false, false, false };
        for (int ci = 0; ci < Cs.length; ci++)
        {
            int C = Cs[ci];
            InboundSockets in = new InboundSockets(Collections.singletonList(new InboundConnectionSettings().withBindAddress(ep).withSocketFactory(factory)));
            in.open().sync();
            Concurrent g = new Concurrent(R);
            OutboundConnection o = newOut(ep, C, R, g);
            String tag = control[ci] ? "U2-control-M0" : "U2";
            try
            {
                o.enqueue(Message.out(Verb._TEST_1, new byte[16]));
                long deadline = System.nanoTime() + SECONDS.toNanos(10);
                while (!(o.isConnected() && o.pendingCount() == 0) && System.nanoTime() < deadline) Thread.sleep(20);
                checkTrue(tag + " C=" + C + " connected and drained before the load", o.isConnected() && o.pendingCount() == 0, st(o, g));
                long s = bulk().serializedSize(current_version);
                int M = control[ci] ? 0 : (int) (2L * (C + R) / P + 100);
                long before = usedAfterGc();
                long after;
                long pend, cnt, epU, glU, ovl, ovlB;
                // Runbook defect 2 (2026-10-21): delivery is blocked by parking the link's event-loop thread, not by holding
                // the queue lock (which made EventLoopDelivery register millions of Locked callbacks during the hold).
                java.lang.reflect.Field fe = OutboundConnection.class.getDeclaredField("eventLoop");
                fe.setAccessible(true);
                io.netty.channel.EventLoop el = (io.netty.channel.EventLoop) fe.get(o);
                java.util.concurrent.CountDownLatch parked = new java.util.concurrent.CountDownLatch(1), lift = new java.util.concurrent.CountDownLatch(1);
                el.execute(() -> { parked.countDown(); try { lift.await(); } catch (InterruptedException e) { Thread.currentThread().interrupt(); } });
                checkTrue(tag + " C=" + C + " event loop parked", parked.await(10, SECONDS), "");
                try
                {
                    for (int i = 0; i < M; i++)
                        o.enqueue(bulk());
                    after = usedAfterGc();
                    histo(tag + "-C" + C);
                    pend = o.pendingBytes(); cnt = o.pendingCount(); epU = o.unsafeGetEndpointReserveLimits().using(); glU = g.using();
                    ovl = o.overloadedCount(); ovlB = o.overloadedBytes();
                    line("PROBE " + tag + " C=" + C + " s=" + s + " M=" + M + " " + st(o, g) + " heapBefore=" + before + " heapAfter=" + after
                         + " heapDelta=" + (after - before) + " ratio=" + (pend == 0 ? "na" : String.format("%.4f", (after - before) / (double) pend)));
                }
                finally
                {
                    lift.countDown();
                }
                if (!control[ci])
                {
                    checkTrue("U2 C=" + C + " pending in (C+R-s, C+R]", pend > C + R - s && pend <= C + R, "pending=" + pend + " s=" + s);
                    check("U2 C=" + C + " endpointUsing == pending - C", pend - C, epU);
                    check("U2 C=" + C + " globalUsing == endpointUsing", epU, glU);
                    check("U2 C=" + C + " overloadedCount == M - accepted", M - cnt, ovl);
                    double ratio = (after - before) / (double) pend;
                    checkTrue("U2 C=" + C + " heapDelta/pending in [1.0, 1.15]", ratio >= 1.0 && ratio <= 1.15, String.format("ratio=%.4f", ratio));
                }
                else
                {
                    checkTrue("U2-control-M0 heapDelta within +-2 MiB", Math.abs(after - before) <= (2 << 20), "heapDelta=" + (after - before));
                }
                o.close(false).get(30, SECONDS);
                line("PROBE " + tag + "-closed C=" + C + " " + st(o, g));
                check(tag + " C=" + C + " after close pending,endpoint,global", "0,0,0", o.pendingBytes() + "," + o.unsafeGetEndpointReserveLimits().using() + "," + g.using());
            }
            finally
            {
                o.close(false).get(30, SECONDS);
                in.close().get(30, SECONDS);
            }
        }
    }

    /** U3: failing-to-connect link, no reserve. */
    @Test
    public void u3FailingToConnect() throws Throwable
    {
        int R = 1 << 20;
        int[] Cs = { 8 << 20, 32 << 20 };
        for (int C : Cs)
        {
            Concurrent g = new Concurrent(R);
            OutboundConnection o = newOut(deadPort(), C, R, g);
            try
            {
                o.enqueue(Message.out(Verb._TEST_1, new byte[16], nanoTime() + MINUTES.toNanos(10)));
                Thread.sleep(3000);
                long deadline = System.nanoTime() + SECONDS.toNanos(30);
                while (o.connectionAttempts() < 2 && System.nanoTime() < deadline) Thread.sleep(50);
                checkTrue("U3 C=" + C + " validity: connectionAttempts >= 2 (failing to connect)", o.connectionAttempts() >= 2, "attempts=" + o.connectionAttempts());
                long s = bulk().serializedSize(current_version);
                int M = (int) (2L * C / P + 100);
                long before = usedAfterGc();
                for (int i = 0; i < M; i++)
                    o.enqueue(bulk());
                long after = usedAfterGc();
                long pend = o.pendingBytes();
                line("PROBE U3 C=" + C + " s=" + s + " M=" + M + " attempts=" + o.connectionAttempts() + " " + st(o, g) + " heapBefore=" + before + " heapAfter=" + after
                     + " heapDelta=" + (after - before) + " ratio=" + String.format("%.4f", (after - before) / (double) pend));
                checkTrue("U3 C=" + C + " pending in (C-s, C]", pend > C - s && pend <= C, "pending=" + pend);
                check("U3 C=" + C + " endpoint,global using", "0,0", o.unsafeGetEndpointReserveLimits().using() + "," + g.using());
                double ratio = (after - before) / (double) pend;
                checkTrue("U3 C=" + C + " heapDelta/pending in [1.0, 1.15]", ratio >= 1.0 && ratio <= 1.15, String.format("ratio=%.4f", ratio));
                check("U3 C=" + C + " overloadedCount == M - accepted bulk (pendingCount - 1 warm-up)", M - (o.pendingCount() - 1), o.overloadedCount());
                checkTrue("U3 C=" + C + " overloadedCount ~ M - C/s (+-2)", Math.abs(o.overloadedCount() - (M - C / s)) <= 2, "overloaded=" + o.overloadedCount() + " M-C/s=" + (M - C / s));
                o.close(false).get(30, SECONDS);
                line("PROBE U3-closed C=" + C + " " + st(o, g));
                check("U3 C=" + C + " after close pending,endpoint,global", "0,0,0", o.pendingBytes() + "," + o.unsafeGetEndpointReserveLimits().using() + "," + g.using());
            }
            finally
            {
                o.close(false).get(30, SECONDS);
            }
        }
    }
}
