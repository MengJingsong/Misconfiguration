/*
 * Stage-4 harness, internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous,
 * unit tier (case file B2 with audit amendments R1-R3). Not part of Cassandra: copy into
 * test/unit/org/apache/cassandra/net/ of a clone at cassandra-5.0.9 and run with
 * `ant testsome -Dtest.name=org.apache.cassandra.net.AcquireExcessProbeTest` (-Dtest.methods=<m> optional).
 *
 * A real InboundMessageHandler (package-private constructor, as in the closed sibling ReleaseCapacityProbeTest) on a Netty
 * EmbeddedChannel, driven through acquireCapacity(Limit, Limit, int) / releaseCapacity(int). The two limits PASSED to
 * acquireCapacity may be wrappers (Counting, HookGlobal); the handler's own reserve fields (used by releaseCapacity) are the
 * raw ResourceLimits.Concurrent objects.
 *
 * Methods:
 *   sequential  R1: S = 16 KiB, E = 256 KiB, Q in {1 KiB, 64 KiB} x G in {128 KiB, 512 KiB, 2 MiB}: successes =
 *               floor((Q + min(E,G)) / S), then GLOBAL if G < E else ENDPOINT; E.using == G.using, <= limits after every call;
 *               the 5-arg refusal adds throttledCount 1; no branch entry (single thread).
 *   control     B2h: Q = 1 MiB >= the offered 640 KiB: the reserves are never touched.
 *   hook        R1 H1, H2 (deterministic :447 branch), H1b (release drops the queue below Q), the E-refusal rollback
 *               (GLOBAL succeeds, ENDPOINT refuses: global permits come back, :432) and the drain to (0,0).
 *   single      B2h: 100,000 single-thread acquire/release steps, branch entries must be 0, final (0,0).
 *   concurrent  B2e step 3: 1,000,000 acquires (1..600 B) by one thread, 4 releasing threads, Q 1024, E = G = 2048; using
 *               <= limit at every acquirer sample and by a sampler thread; branch entries counted; final (0,0).
 *   defaults    B2b: 4 MiB / 128 MiB / 512 MiB from the test yaml's defaults.
 * Every check prints "STAGE4 check <name> expected=<e> actual=<a> ok|MISMATCH" (stdout and -Dstage4.out); a method fails at
 * its end if any of its checks mismatched. "STAGE4 note ..." lines carry numbers that are not checks (branch counts).
 */
package org.apache.cassandra.net;

import java.io.FileOutputStream;
import java.io.PrintStream;
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

public class AcquireExcessProbeTest
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

    private synchronized void check(String name, Object expected, Object actual)
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
        methodMismatches = 0;
    }

    /** Wraps a limit passed to acquireCapacity; counts release(>0) calls (the :449-452 branch for the endpoint wrapper). */
    static class Counting implements Limit
    {
        final Limit d;
        final AtomicLong releases = new AtomicLong();
        final AtomicLong releasedBytes = new AtomicLong();
        Counting(Limit d) { this.d = d; }
        public long limit() { return d.limit(); }
        public long setLimit(long n) { return d.setLimit(n); }
        public long remaining() { return d.remaining(); }
        public long using() { return d.using(); }
        public boolean tryAllocate(long a) { return d.tryAllocate(a); }
        public void allocate(long a) { d.allocate(a); }
        public Outcome release(long a)
        {
            if (a > 0) { releases.incrementAndGet(); releasedBytes.addAndGet(a); }
            return d.release(a);
        }
    }

    /** The global-reserve wrapper whose tryAllocate first runs a hook (a release on the same handler): the :413-:438 race. */
    static class HookGlobal extends Counting
    {
        Runnable hook;
        HookGlobal(Limit d) { super(d); }
        @Override public boolean tryAllocate(long a)
        {
            Runnable h = hook;
            hook = null;
            if (h != null)
                h.run();
            return d.tryAllocate(a);
        }
    }

    static final class Setup
    {
        final EmbeddedChannel channel = new EmbeddedChannel();
        final long Q;
        final Limit endpoint, global;          // raw: the handler's own fields
        final Counting epW;                     // passed to acquireCapacity as the endpoint reserve
        final Limit glW;                        // passed as the global reserve (Counting or HookGlobal)
        final InboundMessageHandler handler;

        Setup(long Q, long E, long G, boolean hookGlobal) throws Exception
        {
            this.Q = Q;
            endpoint = new ResourceLimits.Concurrent(E);
            global = new ResourceLimits.Concurrent(G);
            epW = new Counting(endpoint);
            glW = hookGlobal ? new HookGlobal(global) : new Counting(global);
            WaitQueue eq = WaitQueue.endpoint(endpoint), gq = WaitQueue.global(global);
            InetAddressAndPort self = InetAddressAndPort.getByName("127.0.0.3:7000");
            InetAddressAndPort peer = InetAddressAndPort.getByName("127.0.0.2:7000");
            handler = new InboundMessageHandler(null, ConnectionType.LARGE_MESSAGES, channel, self, peer,
                                                MessagingService.current_version, OutboundConnections.LARGE_MESSAGE_THRESHOLD,
                                                Q, endpoint, global, eq, gq, h -> {}, null, m -> {})
            {
                @Override
                protected boolean processUpToOneMessage(Limit endpointReserve, Limit globalReserve)
                {
                    return false;
                }
            };
        }

        Outcome acquire3(int bytes) { return handler.acquireCapacity(epW, glW, bytes); }

        boolean acquire5(int bytes)
        {
            long now = approxTime.now();
            return handler.acquireCapacity(epW, glW, bytes, now, now + TimeUnit.MINUTES.toNanos(5));
        }

        long branch() { return epW.releases.get(); }

        String state() { return "(" + handler.queueSize + "," + endpoint.using() + "," + global.using() + ")"; }
    }

    @Test
    public void sequential() throws Exception
    {
        final int S = 16 * 1024;
        final long E = 256 * 1024;
        long[] Qs = { 1024, 64 * 1024 };
        long[] Gs = { 128 * 1024, 512 * 1024, 2048 * 1024 };
        for (long Q : Qs)
            for (long G : Gs)
            {
                String p = "seq.Q" + (Q / 1024) + "K.G" + (G / 1024) + "K";
                Setup s = new Setup(Q, E, G, false);
                long min = Math.min(E, G);
                int want = (int) ((Q + min) / S);
                Outcome wantRefusal = G < E ? Outcome.INSUFFICIENT_GLOBAL : Outcome.INSUFFICIENT_ENDPOINT;
                int ok = 0;
                Outcome refusal = null;
                boolean within = true, equal = true;
                long maxG = 0;
                for (int i = 0; i < 100 && refusal == null; i++)
                {
                    Outcome o = s.acquire3(S);
                    if (o == Outcome.SUCCESS)
                        ok++;
                    else
                        refusal = o;
                    within &= s.global.using() <= G && s.endpoint.using() <= E;
                    equal &= s.global.using() == s.endpoint.using();
                    maxG = Math.max(maxG, s.global.using());
                }
                check(p + ".successes", want, ok);
                check(p + ".refusal", wantRefusal, refusal);
                check(p + ".usingWithinLimits", true, within);
                check(p + ".E==G", true, equal);
                check(p + ".reserveAtExhaustion", Math.max(0, (long) ok * S - Q), s.global.using());
                check(p + ".queueSize", (long) ok * S, s.handler.queueSize);
                check(p + ".branchEntries", 0L, s.branch());
                // drain first (a refused 5-arg acquire registers a wait-queue ticket that would take reserve on a later release)
                for (int i = 0; i < ok; i++)
                    s.handler.releaseCapacity(S);
                check(p + ".drain", "(0,0,0)", s.state());
                // then the outer form on a second, identically exhausted handler: refused, throttledCount +1, state unchanged
                Setup t = new Setup(Q, E, G, false);
                for (int i = 0; i < ok; i++)
                    t.acquire3(S);
                String before = t.state();
                check(p + ".outer.result", false, t.acquire5(S));
                check(p + ".outer.throttledCount", 1L, t.handler.throttledCount);
                check(p + ".outer.stateUnchanged", before, t.state());
                say("STAGE4 note " + p + " successes=" + ok + " reserveAtExhaustion=" + maxG + " maxGlobal=" + maxG);
            }
        end("sequential");
    }

    @Test
    public void control() throws Exception
    {
        Setup s = new Setup(1024 * 1024, 256 * 1024, 128 * 1024, false);
        long maxG = 0;
        for (int i = 0; i < 40; i++)
        {
            check("control.acq" + i, Outcome.SUCCESS, s.acquire3(16 * 1024));
            maxG = Math.max(maxG, s.global.using());
        }
        check("control.reserveTouched", 0L, maxG);
        check("control.state", "(655360,0,0)", s.state());
        for (int i = 0; i < 40; i++)
            s.handler.releaseCapacity(16 * 1024);
        check("control.drain", "(0,0,0)", s.state());
        end("control");
    }

    @Test
    public void hook() throws Exception
    {
        final long Q = 1024, R = 2048;
        // H1: q0 = 1624 (reserve 600); acquire 600; during G.tryAllocate the handler releases 1624 (queue -> 0, 600 back)
        {
            Setup s = new Setup(Q, R, R, true);
            check("H1.pre.acq", Outcome.SUCCESS, s.acquire3(1624));
            check("H1.pre.state", "(1624,600,600)", s.state());
            final Setup sf = s;
            ((HookGlobal) s.glW).hook = () -> sf.handler.releaseCapacity(1624);
            Outcome o = s.acquire3(600);
            check("H1.outcome", Outcome.SUCCESS, o);
            check("H1.after.state", "(600,0,0)", s.state());
            check("H1.branchEntries", 1L, s.branch());
            check("H1.branchReleased", 600L, s.epW.releasedBytes.get());
            check("H1.globalReleasedInBranch", 600L, ((Counting) s.glW).releasedBytes.get());
            s.handler.releaseCapacity(600);
            check("H1.drain", "(0,0,0)", s.state());
        }
        // H2: q0 = 1124 (reserve 100); acquire 600; hook releases 500 (100 back, queue 624); branch returns 400
        {
            Setup s = new Setup(Q, R, R, true);
            check("H2.pre.acq", Outcome.SUCCESS, s.acquire3(1124));
            check("H2.pre.state", "(1124,100,100)", s.state());
            final Setup sf = s;
            ((HookGlobal) s.glW).hook = () -> sf.handler.releaseCapacity(500);
            Outcome o = s.acquire3(600);
            check("H2.outcome", Outcome.SUCCESS, o);
            check("H2.after.state", "(1224,200,200)", s.state());
            check("H2.branchEntries", 1L, s.branch());
            check("H2.branchReleased", 400L, s.epW.releasedBytes.get());
            check("H2.globalReleasedInBranch", 400L, ((Counting) s.glW).releasedBytes.get());
            check("H2.reserve==q-Q", 1224L - Q, s.global.using());
            s.handler.releaseCapacity(1224);
            check("H2.drain", "(0,0,0)", s.state());
        }
        // H1b: as H1 but the message is acquired by the 5-argument form (throttledCount unchanged on success)
        {
            Setup s = new Setup(Q, R, R, true);
            check("H1b.pre.acq", true, s.acquire5(1624));
            final Setup sf = s;
            ((HookGlobal) s.glW).hook = () -> sf.handler.releaseCapacity(1624);
            check("H1b.result", true, s.acquire5(600));
            check("H1b.state", "(600,0,0)", s.state());
            check("H1b.throttledCount", 0L, s.handler.throttledCount);
            s.handler.releaseCapacity(600);
            check("H1b.drain", "(0,0,0)", s.state());
        }
        // E-refusal rollback (:431-:435): G has room, E does not: the global permits come back
        {
            Setup s = new Setup(Q, 1000, R, false);
            check("ER.acq1", Outcome.SUCCESS, s.acquire3(1624));    // reserve 600 of E = 1000
            check("ER.state1", "(1624,600,600)", s.state());
            check("ER.acq2", Outcome.INSUFFICIENT_ENDPOINT, s.acquire3(600));   // needs 600 more: E would be 1200 > 1000
            check("ER.rolledBack", "(1624,600,600)", s.state());
            check("ER.branchEntries", 0L, s.branch());
            s.handler.releaseCapacity(1624);
            check("ER.drain", "(0,0,0)", s.state());
        }
        end("hook");
    }

    @Test
    public void single() throws Exception
    {
        Setup s = new Setup(1024, 2048, 2048, false);
        List<Integer> held = new ArrayList<>();
        long maxG = 0;
        boolean within = true;
        for (int i = 0; i < 100_000; i++)
        {
            ThreadLocalRandom r = ThreadLocalRandom.current();
            if (!held.isEmpty() && r.nextInt(100) < 45)
                s.handler.releaseCapacity(held.remove(r.nextInt(held.size())));
            else
            {
                int b = 1 + r.nextInt(600);
                if (s.acquire3(b) == Outcome.SUCCESS)
                    held.add(b);
            }
            maxG = Math.max(maxG, s.global.using());
            within &= s.global.using() <= 2048 && s.endpoint.using() <= 2048 && s.global.using() == s.endpoint.using()
                      && s.global.using() == Math.max(0, s.handler.queueSize - 1024);
        }
        check("single.invariantEveryStep", true, within);
        check("single.branchEntries", 0L, s.branch());
        for (int b : held)
            s.handler.releaseCapacity(b);
        check("single.drain", "(0,0,0)", s.state());
        say("STAGE4 note single maxGlobal=" + maxG);
        end("single");
    }

    @Test
    public void concurrent() throws Exception
    {
        final Setup s = new Setup(1024, 2048, 2048, false);
        final int N = 1_000_000;
        final ArrayBlockingQueue<Integer> admitted = new ArrayBlockingQueue<>(64);
        final AtomicLong released = new AtomicLong(), refusals = new AtomicLong(), samplerMax = new AtomicLong();
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
        Thread sampler = new Thread(() -> {
            while (!done.get())
                samplerMax.accumulateAndGet(Math.max(s.global.using(), s.endpoint.using()), Math::max);
        }, "stage4-sampler");
        sampler.start();
        long maxE = 0, maxG = 0;
        boolean within = true;
        try
        {
            for (int i = 0; i < N; i++)
            {
                int b = 1 + ThreadLocalRandom.current().nextInt(600);
                long spins = 0;
                while (true)
                {
                    if (++spins > 20_000_000L)
                    {
                        errors.add(new IllegalStateException("stuck: acquire refused 20,000,000 times in a row (leaked permits)"));
                        break;
                    }
                    Outcome o = s.acquire3(b);
                    long g = s.global.using(), e = s.endpoint.using();
                    maxE = Math.max(maxE, e);
                    maxG = Math.max(maxG, g);
                    within &= g <= 2048 && e <= 2048;
                    if (o == Outcome.SUCCESS)
                        break;
                    refusals.incrementAndGet();
                    Thread.yield();
                }
                if (!errors.isEmpty())
                    break;
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
        sampler.join(10_000);
        check("concurrent.errors", "[]", errors.toString());
        check("concurrent.released", (long) N, released.get());
        check("concurrent.final", "(0,0,0)", s.state());
        check("concurrent.usingWithinLimitEverySample", true, within && samplerMax.get() <= 2048);
        say("STAGE4 note concurrent branchEntries=" + s.branch() + " branchReleasedBytes=" + s.epW.releasedBytes.get()
            + " globalReleases=" + ((Counting) s.glW).releases.get() + " refusals=" + refusals.get() + " maxE=" + maxE
            + " maxG=" + maxG + " samplerMax=" + samplerMax.get());
        check("concurrent.branchEntered", true, s.branch() > 0);
        end("concurrent");
    }

    @Test
    public void defaults()
    {
        check("defaults.queueCapacity", 4 * 1024 * 1024, DatabaseDescriptor.getInternodeApplicationReceiveQueueCapacityInBytes());
        check("defaults.endpointReserve", 128 * 1024 * 1024, DatabaseDescriptor.getInternodeApplicationReceiveQueueReserveEndpointCapacityInBytes());
        check("defaults.globalReserve", 512 * 1024 * 1024, DatabaseDescriptor.getInternodeApplicationReceiveQueueReserveGlobalCapacityInBytes());
        end("defaults");
    }
}
