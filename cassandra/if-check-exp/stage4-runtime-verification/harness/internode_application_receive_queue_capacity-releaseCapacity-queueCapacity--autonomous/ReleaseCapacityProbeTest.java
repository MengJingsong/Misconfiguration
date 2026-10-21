/*
 * Stage-4 harness, internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous, unit tier
 * (case file B2, with audit amendment R1). Not part of Cassandra: copy into test/unit/org/apache/cassandra/net/ of a
 * clone at cassandra-5.0.9 and run with `ant testsome -Dtest.name=org.apache.cassandra.net.ReleaseCapacityProbeTest`
 * (optionally -Dtest.methods=<method>).
 *
 * B2c: a real InboundMessageHandler (package-private constructor, as in ConnectionBurnTest.java:592-602) with a no-op
 * message consumer on a Netty EmbeddedChannel (the frame decoder is null: the wire path is not used). acquireCapacity()
 * and releaseCapacity() are driven directly. processUpToOneMessage() is overridden (decoder null) to count reactivations
 * and retry the waiting request with the reserves the wait queue hands over (only the method "reactivation" uses it).
 *
 * Methods:
 *   script       B2c/B2f byte script (acquire 600, 600, 2000; release 600, 600; drain) at Q in {1024, 4096} x
 *                R in {2048, 8192}; the invariant E.using == G.using == max(0, q - Q) and q - Q <= R after every step;
 *                the exact (q, E) sequence for Q=1024/R=2048; Q=4096 borrows nothing.
 *   boundary     old == Q releases 0 to the reserves (another handler holds reserve, so a wrong release would show);
 *                old == Q+1 with bytes 5 releases exactly 1.
 *   throttled    throttledCount +1 per refused outer (5-argument) acquire, +0 for the inner (3-argument) one.
 *   reactivation (beyond B2f, B2d's "WaitQueue signals"): a release at old <= Q does not wake a waiting handler; a
 *                release at old > Q does, and the invariant holds after the woken handler's retry.
 *   concurrent   1 acquiring thread (the "event loop") + 4 releasing threads, 100,000 messages, 5 repetitions; final
 *                state (0, 0), no exception.
 *   defaults     the yaml-level default: DatabaseDescriptor.getInternodeApplicationReceiveQueueCapacityInBytes() ==
 *                4194304 under the test yaml (which does not set the key). The 8 MiB check is
 *                ReleaseCapacityConfigTest (its own JVM).
 *
 * Every check prints "STAGE4 check <name> expected=<e> actual=<a> ok|MISMATCH" (stdout and -Dstage4.out); each method
 * fails at its end if any of its checks mismatched.
 */
package org.apache.cassandra.net;

import java.io.FileOutputStream;
import java.io.PrintStream;
import java.net.UnknownHostException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import io.netty.channel.embedded.EmbeddedChannel;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.locator.InetAddressAndPort;
import org.apache.cassandra.net.AbstractMessageHandler.WaitQueue;
import org.apache.cassandra.net.ResourceLimits.Limit;
import org.apache.cassandra.net.ResourceLimits.Outcome;

import static org.apache.cassandra.utils.MonotonicClock.Global.approxTime;

public class ReleaseCapacityProbeTest
{
    private static PrintStream out;
    private static int checks, mismatches;
    private int methodMismatches;

    @BeforeClass
    public static void setUp() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        String f = System.getProperty("stage4.out");
        out = f == null ? null : new PrintStream(new FileOutputStream(f, true), true);
    }

    @AfterClass
    public static void tearDown()
    {
        say("STAGE4 summary checks=" + checks + " mismatches=" + mismatches);
        if (out != null)
            out.close();
    }

    private static synchronized void say(String s)
    {
        System.out.println(s);
        if (out != null)
            out.println(s);
    }

    private void check(String name, Object expected, Object actual)
    {
        checks++;
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        if (!ok)
        {
            mismatches++;
            methodMismatches++;
        }
        say("STAGE4 check " + name + " expected=" + expected + " actual=" + actual + (ok ? " ok" : " MISMATCH"));
    }

    private void end(String method)
    {
        say("STAGE4 method " + method + " mismatches=" + methodMismatches);
        Assert.assertEquals("STAGE4 mismatches in " + method, 0, methodMismatches);
    }

    /** One InboundMessageHandler with its own reserves (or shared ones) on an EmbeddedChannel. */
    static final class Setup
    {
        final EmbeddedChannel channel = new EmbeddedChannel();
        final long Q;
        final Limit endpoint, global;
        final WaitQueue endpointQueue, globalQueue;
        final InboundMessageHandler handler;
        final List<String> reactivations = new ArrayList<>();
        int waitingBytes;

        Setup(long Q, long R) throws UnknownHostException
        {
            this(Q, new ResourceLimits.Concurrent(R), new ResourceLimits.Concurrent(R), null, null);
        }

        Setup(long Q, Limit endpoint, Limit global, WaitQueue eq, WaitQueue gq) throws UnknownHostException
        {
            this.Q = Q;
            this.endpoint = endpoint;
            this.global = global;
            this.endpointQueue = eq != null ? eq : WaitQueue.endpoint(endpoint);
            this.globalQueue = gq != null ? gq : WaitQueue.global(global);
            InetAddressAndPort self = InetAddressAndPort.getByName("127.0.0.3:7000");
            InetAddressAndPort peer = InetAddressAndPort.getByName("127.0.0.2:7000");
            handler = new InboundMessageHandler(null, ConnectionType.LARGE_MESSAGES, channel, self, peer,
                                                MessagingService.current_version, OutboundConnections.LARGE_MESSAGE_THRESHOLD,
                                                Q, endpoint, global, endpointQueue, globalQueue,
                                                h -> {}, null, m -> {})
            {
                @Override
                protected boolean processUpToOneMessage(Limit endpointReserve, Limit globalReserve)
                {
                    Outcome o = acquireCapacity(endpointReserve, globalReserve, waitingBytes);
                    reactivations.add(o + " q=" + queueSize + " lease=" + globalReserve.using() + "/" + globalReserve.limit());
                    return false; // no decoder to reactivate
                }
            };
        }

        Outcome acquire3(int bytes)
        {
            return handler.acquireCapacity(endpoint, global, bytes);
        }

        boolean acquire5(int bytes)
        {
            long now = approxTime.now();
            return handler.acquireCapacity(endpoint, global, bytes, now, now + TimeUnit.MINUTES.toNanos(5));
        }

        String state()
        {
            return "(" + handler.queueSize + "," + endpoint.using() + "," + global.using() + ")";
        }
    }

    /** the B2f invariant for a handler that owns its reserves: E == G == max(0, q - Q), and q - Q <= R */
    private void invariant(String name, Setup s, long R)
    {
        long q = s.handler.queueSize;
        long want = Math.max(0, q - s.Q);
        check(name + ".inv", "E=" + want + " G=" + want, "E=" + s.endpoint.using() + " G=" + s.global.using());
        check(name + ".withinR", true, q - s.Q <= R);
    }

    @Test
    public void script() throws Exception
    {
        long[][] cells = { { 1024, 2048 }, { 1024, 8192 }, { 4096, 2048 }, { 4096, 8192 } };
        for (long[] c : cells)
        {
            long Q = c[0], R = c[1];
            String p = "script.Q" + Q + ".R" + R;
            Setup s = new Setup(Q, R);
            List<String> seq = new ArrayList<>();
            List<Outcome> outs = new ArrayList<>();
            long maxReserve = 0;
            int[] acq = { 600, 600, 2000 };
            List<Integer> admitted = new ArrayList<>();
            for (int i = 0; i < acq.length; i++)
            {
                Outcome o = s.acquire3(acq[i]);
                outs.add(o);
                if (o == Outcome.SUCCESS)
                    admitted.add(acq[i]);
                seq.add(s.handler.queueSize + "/" + s.endpoint.using());
                maxReserve = Math.max(maxReserve, s.endpoint.using());
                invariant(p + ".acq" + (i + 1) + "_" + acq[i], s, R);
            }
            // release 600, 600, then whatever else was admitted (the 2000 if it was)
            int[] rel = admitted.size() == 3 ? new int[]{ 600, 600, 2000 } : new int[]{ 600, 600 };
            for (int i = 0; i < rel.length; i++)
            {
                s.handler.releaseCapacity(rel[i]);
                seq.add(s.handler.queueSize + "/" + s.endpoint.using());
                invariant(p + ".rel" + (i + 1) + "_" + rel[i], s, R);
            }
            check(p + ".final", "(0,0,0)", s.state());
            say("STAGE4 note " + p + " outcomes=" + outs + " (q/E) sequence=" + seq);
            if (Q == 1024 && R == 2048)
            {
                check(p + ".outcomes", "[SUCCESS, SUCCESS, INSUFFICIENT_GLOBAL]", outs.toString());
                check(p + ".sequence", "[600/0, 1200/176, 1200/176, 600/0, 0/0]", seq.toString());
            }
            if (Q == 4096)
                check(p + ".borrowsNothing", 0L, maxReserve);
        }
        end("script");
    }

    @Test
    public void boundary() throws Exception
    {
        long Q = 1024, R = 2048;
        Limit E = new ResourceLimits.Concurrent(R), G = new ResourceLimits.Concurrent(R);
        WaitQueue eq = WaitQueue.endpoint(E), gq = WaitQueue.global(G);
        Setup other = new Setup(Q, E, G, eq, gq);       // holds 100 B of reserve throughout
        Setup h1 = new Setup(Q, E, G, eq, gq);
        Setup h3 = new Setup(Q, E, G, eq, gq);
        check("boundary.other.acq", Outcome.SUCCESS, other.acquire3((int) Q + 100));
        check("boundary.other.reserve", "E=100 G=100", "E=" + E.using() + " G=" + G.using());
        // old == Q exactly: nothing goes back to the reserves
        check("boundary.eq.acq", Outcome.SUCCESS, h1.acquire3((int) Q));
        check("boundary.eq.acq.reserve", "E=100 G=100", "E=" + E.using() + " G=" + G.using());
        h1.handler.releaseCapacity(24);   // oldQueueSize == Q
        check("boundary.eq.rel.q", Q - 24, h1.handler.queueSize);
        check("boundary.eq.rel.released", "E=100 G=100", "E=" + E.using() + " G=" + G.using());
        // old == Q + 1, bytes 5: exactly 1 goes back
        check("boundary.plus1.acq", Outcome.SUCCESS, h3.acquire3((int) Q + 1));
        check("boundary.plus1.acq.reserve", "E=101 G=101", "E=" + E.using() + " G=" + G.using());
        h3.handler.releaseCapacity(5);    // oldQueueSize == Q + 1
        check("boundary.plus1.rel.q", Q - 4, h3.handler.queueSize);
        check("boundary.plus1.rel.released1", "E=100 G=100", "E=" + E.using() + " G=" + G.using());
        // drain everything: both reserves back to 0
        h1.handler.releaseCapacity((int) (Q - 24));
        h3.handler.releaseCapacity((int) (Q - 4));
        other.handler.releaseCapacity((int) Q + 100);
        check("boundary.drain", "q=0,0,0 E=0 G=0", "q=" + h1.handler.queueSize + "," + h3.handler.queueSize + ","
                                                   + other.handler.queueSize + " E=" + E.using() + " G=" + G.using());
        end("boundary");
    }

    @Test
    public void throttled() throws Exception
    {
        Setup s = new Setup(1024, 2048);
        check("throttled.a1", true, s.acquire5(600));
        check("throttled.a2", true, s.acquire5(600));
        check("throttled.before", 0L, s.handler.throttledCount);
        check("throttled.inner.outcome", Outcome.INSUFFICIENT_GLOBAL, s.acquire3(2000));
        check("throttled.inner.count", 0L, s.handler.throttledCount);
        check("throttled.inner.state", "(1200,176,176)", s.state());
        check("throttled.outer.result", false, s.acquire5(2000));
        check("throttled.outer.count", 1L, s.handler.throttledCount);
        check("throttled.outer.state", "(1200,176,176)", s.state());
        end("throttled");
    }

    @Test
    public void reactivation() throws Exception
    {
        // h waits for 2000 on the global queue; a second handler w on the same reserves does the releases
        long Q = 1024, R = 2048;
        Limit E = new ResourceLimits.Concurrent(R), G = new ResourceLimits.Concurrent(R);
        WaitQueue eq = WaitQueue.endpoint(E), gq = WaitQueue.global(G);
        Setup h = new Setup(Q, E, G, eq, gq);
        Setup w = new Setup(Q, E, G, eq, gq);
        check("x.react.h.acq", true, h.acquire5(600));
        check("x.react.w.acq1", true, w.acquire5(1000));
        check("x.react.w.acq2", true, w.acquire5(1000));   // w: q 2000, borrows 976
        h.waitingBytes = 2000;
        check("x.react.h.refused", false, h.acquire5(2000)); // excess min(600+2000-1024, 2000) = 1576 > 2048 - 976
        h.channel.runPendingTasks();
        check("x.react.none.yet", 0, h.reactivations.size());
        // a release at old > Q of 976 returns 976: global now has room for the whole 2000 -> lease + reactivation
        w.handler.releaseCapacity(976);                      // old 2000 > Q: excess min(976, 976) = 976
        check("x.react.w.rel1.reserve", "E=0", "E=" + E.using());
        h.channel.runPendingTasks();
        check("x.react.after.rel_aboveQ", 1, h.reactivations.size());
        check("x.react.retry.state.q", 2600L, h.handler.queueSize);
        check("x.react.retry.inv", "E=1576 G=1576", "E=" + E.using() + " G=" + G.using());
        say("STAGE4 note x.react " + h.reactivations);
        // h now waits again for 2000 more; a release at old <= Q (w: 1024 -> 0) returns nothing and wakes nobody
        check("x.react.h.refused2", false, h.acquire5(2000));
        h.channel.runPendingTasks();
        int before = h.reactivations.size();
        w.handler.releaseCapacity(1024);                     // old 1024 == Q: no reserve release, no signal
        h.channel.runPendingTasks();
        check("x.react.after.rel_atQ", before, h.reactivations.size());
        check("x.react.after.rel_atQ.reserve", "E=1576 G=1576", "E=" + E.using() + " G=" + G.using());
        // drain h: its release at old 2600 > Q returns 1576; a (lease) reactivation may follow, then release that too
        h.handler.releaseCapacity(2600);
        h.channel.runPendingTasks();
        if (h.reactivations.size() > before)
            h.handler.releaseCapacity(2000);
        h.channel.runPendingTasks();
        check("x.react.drain", "q=0,0 E=0 G=0", "q=" + h.handler.queueSize + "," + w.handler.queueSize
                                              + " E=" + E.using() + " G=" + G.using());
        end("reactivation");
    }

    @Test
    public void concurrent() throws Exception
    {
        for (int rep = 1; rep <= 5; rep++)
        {
            final Setup s = new Setup(1024, 2048);
            final int N = 100_000;
            final ArrayBlockingQueue<Integer> admitted = new ArrayBlockingQueue<>(64);
            final AtomicLong released = new AtomicLong();
            final AtomicLong refusals = new AtomicLong();
            final List<Throwable> errors = new java.util.concurrent.CopyOnWriteArrayList<>();
            final AtomicBoolean done = new AtomicBoolean();
            Thread[] releasers = new Thread[4];
            for (int i = 0; i < releasers.length; i++)
            {
                releasers[i] = new Thread(() -> {
                    try
                    {
                        while (true)
                        {
                            Integer b = admitted.poll(10, TimeUnit.MILLISECONDS);
                            if (b == null)
                            {
                                if (done.get() && admitted.isEmpty())
                                    return;
                                continue;
                            }
                            s.handler.releaseCapacity(b);
                            released.incrementAndGet();
                        }
                    }
                    catch (Throwable t)
                    {
                        errors.add(t);
                    }
                }, "stage4-release-" + i);
                releasers[i].start();
            }
            long maxE = 0, maxG = 0;
            Thread acquirer = Thread.currentThread();
            try
            {
                for (int i = 0; i < N; i++)
                {
                    int b = 1 + ThreadLocalRandom.current().nextInt(600);
                    while (true)
                    {
                        Outcome o = s.acquire3(b);
                        if (o == Outcome.SUCCESS)
                            break;
                        refusals.incrementAndGet();
                        Thread.yield();
                    }
                    maxE = Math.max(maxE, s.endpoint.using());
                    maxG = Math.max(maxG, s.global.using());
                    while (!admitted.offer(b, 10, TimeUnit.MILLISECONDS))
                        if (!errors.isEmpty())
                            break;
                    if (!errors.isEmpty())
                        break;
                }
            }
            catch (Throwable t)
            {
                errors.add(t);
            }
            done.set(true);
            for (Thread t : releasers)
                t.join(60_000);
            String p = "concurrent.rep" + rep;
            check(p + ".errors", "[]", errors.toString());
            check(p + ".released", (long) N, released.get());
            check(p + ".final", "(0,0,0)", s.state());
            check(p + ".maxReserve.withinR", true, maxE <= 2048 && maxG <= 2048);
            say("STAGE4 note " + p + " refusals=" + refusals.get() + " maxE=" + maxE + " maxG=" + maxG + " thread=" + acquirer.getName());
        }
        end("concurrent");
    }

    @Test
    public void defaults()
    {
        check("defaults.queueCapacity", 4194304, DatabaseDescriptor.getInternodeApplicationReceiveQueueCapacityInBytes());
        end("defaults");
    }
}
