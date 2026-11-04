/*
 * Stage-4 harness, internode_application_receive_queue_capacity-acquireCapacity-queueCapacity, unit tier (case 9e, unit
 * steps 1-5 as amended 2026-10-14). Not part of Cassandra: copy into test/unit/org/apache/cassandra/net/ of a clone at
 * cassandra-5.0.9 and run with `ant testsome -Dtest.name=org.apache.cassandra.net.AcquireCapacityTest`.
 *
 * A minimal AbstractMessageHandler (the five abstract methods unused, decoder null) on a Netty EmbeddedChannel, whose
 * event loop runs the wait queue's reactivation task when the test calls runPendingTasks(). processUpToOneMessage() is
 * overridden to retry the waiting request through the three-argument acquireCapacity() with the reserves the wait queue
 * hands over, so a reactivation is observable without a frame decoder.
 *
 * Every check prints "STAGE4 check <name> expected=<e> actual=<a> ok|MISMATCH" (stdout and -Dstage4.out); the test fails
 * at the end if any check mismatched.
 */
package org.apache.cassandra.net;

import java.io.FileOutputStream;
import java.io.PrintStream;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import io.netty.channel.embedded.EmbeddedChannel;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.net.AbstractMessageHandler.WaitQueue;
import org.apache.cassandra.net.FrameDecoder.CorruptFrame;
import org.apache.cassandra.net.FrameDecoder.IntactFrame;
import org.apache.cassandra.net.ResourceLimits.Limit;
import org.apache.cassandra.net.ResourceLimits.Outcome;

import static org.apache.cassandra.utils.MonotonicClock.Global.approxTime;

public class AcquireCapacityTest
{
    private static PrintStream out;
    private static int checks, mismatches;

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

    private static void say(String s)
    {
        System.out.println(s);
        if (out != null)
            out.println(s);
    }

    private static void check(String name, Object expected, Object actual)
    {
        checks++;
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        if (!ok)
            mismatches++;
        say("STAGE4 check " + name + " expected=" + expected + " actual=" + actual + (ok ? " ok" : " MISMATCH"));
    }

    /** The handler under test: only the capacity logic of AbstractMessageHandler is used. */
    static final class TestHandler extends AbstractMessageHandler
    {
        final List<String> retries = new ArrayList<>();
        final List<Throwable> fatal = new ArrayList<>();
        int retryBytes;
        Outcome lastRetry;

        TestHandler(EmbeddedChannel channel, long queueCapacity, Limit endpoint, Limit global, WaitQueue endpointQueue, WaitQueue globalQueue)
        {
            super(null, channel, 64 << 10, queueCapacity, endpoint, global, endpointQueue, globalQueue, h -> {});
        }

        protected boolean processOneContainedMessage(ShareableBytes bytes, Limit endpointReserve, Limit globalReserve)
        {
            throw new UnsupportedOperationException();
        }

        protected boolean processFirstFrameOfLargeMessage(IntactFrame frame, Limit endpointReserve, Limit globalReserve)
        {
            throw new UnsupportedOperationException();
        }

        protected void processCorruptFrame(CorruptFrame frame)
        {
            throw new UnsupportedOperationException();
        }

        protected void fatalExceptionCaught(Throwable t)
        {
            fatal.add(t);
        }

        protected String id()
        {
            return "stage4-test-handler";
        }

        /** Called by the wait queue's reactivation task: retry the waiting request with the reserves handed over. */
        @Override
        protected boolean processUpToOneMessage(Limit endpointReserve, Limit globalReserve)
        {
            lastRetry = acquireCapacity(endpointReserve, globalReserve, retryBytes);
            retries.add(lastRetry + " ep=" + endpointReserve.using() + "/" + endpointReserve.limit()
                        + " lease=" + globalReserve.using() + "/" + globalReserve.limit());
            return false; // no decoder to reactivate
        }
    }

    private static final class Setup
    {
        final EmbeddedChannel channel = new EmbeddedChannel();
        final Limit endpoint, global;
        final WaitQueue endpointQueue, globalQueue;
        final TestHandler handler;

        Setup(long capacity, long endpointLimit, long globalLimit)
        {
            endpoint = new ResourceLimits.Concurrent(endpointLimit);
            global = new ResourceLimits.Concurrent(globalLimit);
            endpointQueue = WaitQueue.endpoint(endpoint);
            globalQueue = WaitQueue.global(global);
            handler = new TestHandler(channel, capacity, endpoint, global, endpointQueue, globalQueue);
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
    }

    private static Object ticket(AbstractMessageHandler h) throws Exception
    {
        Field f = AbstractMessageHandler.class.getDeclaredField("ticket");
        f.setAccessible(true);
        return f.get(h);
    }

    @Test
    public void steps() throws Exception
    {
        // Step 1: the boundary. q + b == C succeeds with no reserve; one byte more borrows exactly the one byte.
        Setup s1 = new Setup(1000, 800, 800);
        check("u1.exact.outcome", Outcome.SUCCESS, s1.acquire3(1000));
        check("u1.exact.q", 1000, s1.handler.queueSize);
        check("u1.exact.endpoint", 0, s1.endpoint.using());
        check("u1.exact.global", 0, s1.global.using());
        check("u1.plus1.outcome", Outcome.SUCCESS, s1.acquire3(1));
        check("u1.plus1.q", 1001, s1.handler.queueSize);
        check("u1.plus1.endpoint", 1, s1.endpoint.using());
        check("u1.plus1.global", 1, s1.global.using());

        // Step 2: allow, then borrow only the excess.
        Setup s2 = new Setup(1000, 800, 800);
        check("u2.first.outcome", Outcome.SUCCESS, s2.acquire3(600));
        check("u2.first.q", 600, s2.handler.queueSize);
        check("u2.first.endpoint", 0, s2.endpoint.using());
        check("u2.first.global", 0, s2.global.using());
        check("u2.first.throttled", 0, s2.handler.throttledCount);
        check("u2.second.outcome", Outcome.SUCCESS, s2.acquire3(600));
        check("u2.second.q", 1200, s2.handler.queueSize);
        check("u2.second.endpoint", 200, s2.endpoint.using());
        check("u2.second.global", 200, s2.global.using());

        // Step 3: the excess (700) is above the room left (600): INSUFFICIENT_GLOBAL, nothing taken, a ticket registered,
        // and no reactivation scheduled (the global reserve cannot lend the whole 700 yet: 200 + 700 > 800).
        s2.handler.retryBytes = 700;
        check("u3.outcome3", Outcome.INSUFFICIENT_GLOBAL, s2.acquire3(700));   // the verdict alone
        check("u3.outcome3.q", 1200, s2.handler.queueSize);
        check("u3.outcome3.throttled", 0, s2.handler.throttledCount);         // the 3-arg method does not count
        check("u3.acquire5", false, s2.acquire5(700));                          // the decision point's call
        check("u3.q", 1200, s2.handler.queueSize);
        check("u3.endpoint", 200, s2.endpoint.using());
        check("u3.global", 200, s2.global.using());
        check("u3.throttled", 1, s2.handler.throttledCount);
        check("u3.ticket", true, ticket(s2.handler) != null);
        s2.channel.runPendingTasks();
        check("u3.noReactivation", 0, s2.handler.retries.size());

        // Step 4: global large, endpoint small: INSUFFICIENT_ENDPOINT, the global borrow rolled back.
        Setup s4 = new Setup(1000, 300, 10_000);
        check("u4.a", Outcome.SUCCESS, s4.acquire3(600));
        check("u4.b", Outcome.SUCCESS, s4.acquire3(600));
        check("u4.b.endpoint", 200, s4.endpoint.using());
        check("u4.b.global", 200, s4.global.using());
        check("u4.acquire5", false, s4.acquire5(600));
        check("u4.q", 1200, s4.handler.queueSize);
        check("u4.endpoint", 200, s4.endpoint.using());
        check("u4.global.rolledBack", 200, s4.global.using());
        check("u4.throttled", 1, s4.handler.throttledCount);
        check("u4.ticket", true, ticket(s4.handler) != null);
        check("u4.outcome3", Outcome.INSUFFICIENT_ENDPOINT, s4.acquire3(600));
        check("u4.outcome3.global", 200, s4.global.using());

        // Step 5: a release on the step-3 handler gives the global reserve room for the whole 700; the wait queue
        // schedules a reactivation on the channel's event loop, which retries the 700 with a 700-byte lease.
        Thread.sleep(50); // so the throttled time is measurable on the approximate clock
        s2.handler.releaseCapacity(600);
        check("u5.release.q", 600, s2.handler.queueSize);
        check("u5.release.endpoint", 0, s2.endpoint.using());
        check("u5.leased.global", 700, s2.global.using());                     // the lease is taken in schedule()
        check("u5.beforeRun.retries", 0, s2.handler.retries.size());
        s2.channel.runPendingTasks();
        check("u5.retries", 1, s2.handler.retries.size());
        check("u5.retry.outcome", Outcome.SUCCESS, s2.handler.lastRetry);
        check("u5.q", 1300, s2.handler.queueSize);
        check("u5.endpoint", 300, s2.endpoint.using());
        check("u5.global", 300, s2.global.using());                             // 700 leased, 400 returned
        check("u5.throttledNanos.positive", true, s2.handler.throttledNanos > 0);
        check("u5.ticket.cleared", true, ticket(s2.handler) == null);
        check("u5.fatal", 0, s2.handler.fatal.size());
        say("STAGE4 note u5.retry " + s2.handler.retries + " throttledNanos=" + s2.handler.throttledNanos);

        // Release everything: the reserves return to zero.
        s2.handler.releaseCapacity(700);
        s2.handler.releaseCapacity(600);
        check("u5.drain.q", 0, s2.handler.queueSize);
        check("u5.drain.endpoint", 0, s2.endpoint.using());
        check("u5.drain.global", 0, s2.global.using());

        Assert.assertEquals("STAGE4 mismatches", 0, mismatches);
    }
}
