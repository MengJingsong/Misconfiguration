/*
 * Stage-4 harness, unit tier, for native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided
 * (case 9a Procedure step 1, amended 9f R2-R4, 2026-10-20). Copy into test/unit/org/apache/cassandra/transport/ of a
 * cassandra-5.0.9 clone together with QueueAgeWriter.java (and NqaHold.java into test/unit/stage4/), and run with the
 * Byteman agent and nqa.btm (unit-run.sh does all of it).
 *
 * CQLTester's in-process server (protocol v5); the native request executor (Dispatcher.requestExecutor) resized to 4
 * workers (native_transport_max_threads 4, 9b); in-flight limits 1 GiB (9b); requests are the cluster tier's EXECUTE of
 * a 64 KiB blob (QueueAgeWriter). The stall is the cluster tier's rule (nqa.btm, "nqa hold"): EXECUTE requests wait at
 * RequestProcessor.run entry while the file -Dstage4.release.file is absent. Steps:
 *   u0  4 requests held running, none queued: oldestTaskQueueTime() = 0 and hasQueueCapacity() true even at a 12 ns limit
 *       (R2: the operand reads the queue head only).
 *   u1  one request queued and aged >= 600 ms: hasQueueCapacity() at threshold 0, -1, Double.MAX_VALUE (off: true), with
 *       the limit 2 s above the age (true), equal to an age read just before (false: the comparison is strict "<"),
 *       300 ms below the age (false); the age is the head's (a second, newer queued request does not lower it); the
 *       queued bytes (pending x M, RequestsSize) do not change across the calls.
 *   u2  throwing connection, limit 100 ms below the head's age: one request is refused with the queue-age
 *       OverloadedException, RequestDiscarded + 1, pending and RequestsSize unchanged; at threshold off the next is queued.
 *   u3  default-mode connection, same limit: the request is queued anyway (pending + 1) and the connection is paused
 *       (ConnectionPaused + 1); after the release its response carries the "spent over" warning.
 *   u4  the claim at unit scale (throwing, a fresh connection per arm): 50 requests/s for 4 s with the workers stalled at
 *       threshold off, 0.2, 0.05, 0.01 (limits 2.4 s, 0.6 s, 0.12 s): peak queued requests, queued bytes (pending + active)
 *       x M, RequestsSize, refusals by class. (The source predicts about 4 + 1 + 50 x limit admitted in throwing mode.)
 *   u5  positive control: threshold off, global in-flight limit 2 MiB: RequestsSize stops at <= 2 MiB, the rest refused
 *       "bytes in flight".
 * Every reading goes to -Dstage4.out as "STAGE4 ..." lines; checks print "STAGE4 check <name> expected=... actual=... ok|MISMATCH".
 * The test fails only on an instrument or set-up error (the stall did not hold, a set-up value did not take).
 */
package org.apache.cassandra.transport;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.PrintStream;
import java.lang.reflect.Field;
import java.util.concurrent.TimeUnit;

import com.codahale.metrics.Meter;
import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.metrics.ClientMessageSizeMetrics;
import org.apache.cassandra.metrics.ClientMetrics;
import org.apache.cassandra.transport.messages.ResultMessage;

public class NqaQueueAgeTest extends CQLTester
{
    static final long KiB = 1024, MiB = 1024 * KiB, GiB = 1024 * MiB;
    static final int VALUE = 65536;
    static PrintStream out;
    static File release;
    static int mismatches = 0;
    static int nextK = 0;
    static String table;
    static long M = -1;   // the request's body size (bytes counted against the in-flight limits)

    static class Tee extends PrintStream
    {
        Tee(PrintStream a) { super(a, true); }
        @Override public void println(String s) { System.out.println(s); super.println(s); }
    }

    @BeforeClass
    public static void setUp() throws IOException
    {
        out = new Tee(new PrintStream(new FileOutputStream(System.getProperty("stage4.out", "build/test/nqa.out"), true), true));
        release = new File(System.getProperty("stage4.release.file", "build/test/nqa.release"));
        release.createNewFile();
        requireNetwork();
    }

    @AfterClass
    public static void tearDown() throws IOException
    {
        release.createNewFile();
        DatabaseDescriptor.setNativeTransportMaxQueueItemAgeThreshold(Double.MAX_VALUE);
        if (out != null) out.close();
    }

    static void check(String name, Object expected, Object actual, boolean ok)
    {
        if (!ok) mismatches++;
        out.println("STAGE4 check " + name + " expected=" + expected + " actual=" + actual + (ok ? " ok" : " MISMATCH"));
    }

    static long timeoutNs() { return DatabaseDescriptor.getNativeTransportTimeout(TimeUnit.NANOSECONDS); }
    static int pending() { return Dispatcher.requestExecutor.getPendingTaskCount(); }
    static int active() { return Dispatcher.requestExecutor.getActiveTaskCount(); }
    static long age() { return Dispatcher.requestExecutor.oldestTaskQueueTime(); }
    static long usage() { return ClientResourceLimits.getCurrentGlobalUsage(); }
    static boolean has() { return new Dispatcher(false).hasQueueCapacity(); }
    static void thr(double t) { DatabaseDescriptor.setNativeTransportMaxQueueItemAgeThreshold(t); }
    static double thrForNs(long ns) { return ns / (double) timeoutNs(); }

    static long meter(String field) throws Exception
    {
        Field f = ClientMetrics.class.getDeclaredField(field);
        f.setAccessible(true);
        return ((Meter) f.get(ClientMetrics.instance)).getCount();
    }

    static void waitFor(String what, java.util.function.BooleanSupplier cond, long ms) throws InterruptedException
    {
        long deadline = System.currentTimeMillis() + ms;
        while (!cond.getAsBoolean())
        {
            if (System.currentTimeMillis() > deadline)
                throw new AssertionError("timed out waiting for " + what + " (pending=" + pending() + " active=" + active() + ")");
            Thread.sleep(5);
        }
    }

    static void stall() { Assert.assertTrue("release file delete", !release.exists() || release.delete()); }

    static void releaseAll() throws Exception
    {
        release.createNewFile();
        waitFor("executor idle", () -> pending() == 0 && active() == 0, 60_000);
    }

    static void state(String tag)
    {
        out.println("STAGE4 state " + tag + " pending=" + pending() + " active=" + active() + " age_ns=" + age() + " requests_size=" + usage()
                    + " thr=" + DatabaseDescriptor.getNativeTransportQueueMaxItemAgeThreshold() + " ms=" + System.currentTimeMillis());
    }

    static SimpleClient connect(Boolean throwOnOverload) throws IOException
    {
        SimpleClient c = SimpleClient.builder(nativeAddr.getHostAddress(), nativePort).protocolVersion(ProtocolVersion.V5).build();
        return throwOnOverload == null ? c.connect(false, false) : c.connect(false, throwOnOverload);
    }

    static QueueAgeWriter writer(SimpleClient c, int n)
    {
        ResultMessage.Prepared p = QueueAgeWriter.prepare(c, KEYSPACE, table);
        QueueAgeWriter w = new QueueAgeWriter(c, p, VALUE, n);
        w.startReader();
        return w;
    }

    @Test
    public void queueAge() throws Exception
    {
        table = createTable("CREATE TABLE %s (pk int PRIMARY KEY, v blob)");
        Dispatcher.requestExecutor.setMaximumPoolSize(4);
        ClientResourceLimits.setGlobalLimit(GiB);
        ClientResourceLimits.setEndpointLimit(GiB);
        thr(Double.MAX_VALUE);
        out.println("STAGE4 info max_pool=" + Dispatcher.requestExecutor.getMaximumPoolSize() + " timeout_ns=" + timeoutNs()
                    + " global=" + ClientResourceLimits.getGlobalLimit() + " endpoint=" + ClientResourceLimits.getEndpointLimit()
                    + " recv_queue_capacity=" + DatabaseDescriptor.getNativeTransportReceiveQueueCapacityInBytes()
                    + " throw_default=" + DatabaseDescriptor.getNativeTransportThrowOnOverload() + " heap_max=" + Runtime.getRuntime().maxMemory());
        Assert.assertEquals(4, Dispatcher.requestExecutor.getMaximumPoolSize());

        // M: one unheld request on a fresh connection, from the BytesReceived counter (body + 9-byte header)
        try (SimpleClient c = connect(true))
        {
            QueueAgeWriter w = writer(c, 1);
            long b0 = ClientMessageSizeMetrics.bytesReceived.getCount();
            w.send(0);
            Assert.assertTrue(w.awaitAll(10_000));
            M = ClientMessageSizeMetrics.bytesReceived.getCount() - b0 - Envelope.Header.LENGTH;
            w.stopReader();
            out.println("STAGE4 info M=" + M + " outcome=" + w.outcome[0]);
        }

        try (SimpleClient a = connect(true); SimpleClient b = connect(true); SimpleClient d = connect(false))
        {
            QueueAgeWriter wa = writer(a, 8), wb = writer(b, 2), wd = writer(d, 1);

            // u0: four held running, none queued
            stall();
            for (int k = 0; k < 4; k++) wa.send(k);
            waitFor("4 active", () -> active() == 4, 10_000);
            Thread.sleep(300);
            state("u0");
            check("u0 active", 4, active(), active() == 4);
            check("u0 pending", 0, pending(), pending() == 0);
            check("u0 age with nothing queued", 0, age(), age() == 0);
            thr(1e-9);
            boolean h0 = has();
            check("u0 hasQueueCapacity at a 12 ns limit, nothing queued", true, h0, h0);

            // u1: one queued, aged >= 600 ms
            thr(Double.MAX_VALUE);
            long usage0 = usage();
            wa.send(4);
            waitFor("1 pending", () -> pending() == 1, 10_000);
            Thread.sleep(600);
            state("u1");
            long a0 = age();
            check("u1 head age >= 600 ms", ">=600000000", a0, a0 >= 600_000_000L && a0 < 5_000_000_000L);
            thr(0);  boolean t0 = has();  check("u1 threshold 0 (off)", true, t0, t0);
            thr(-1); boolean tm = has();  check("u1 threshold -1 (off)", true, tm, tm);
            thr(Double.MAX_VALUE); boolean tx = has(); check("u1 threshold Double.MAX_VALUE (default, off)", true, tx, tx);
            thr(thrForNs(age() + 2_000_000_000L)); boolean above = has();
            check("u1 limit 2 s above the age", true, above, above);
            long aEq = age();
            double tEq = thrForNs(aEq);
            while ((double) timeoutNs() * tEq > aEq) tEq = Math.nextDown(tEq);   // limit <= aEq, within one ulp of it
            thr(tEq); boolean at = has(); long aAfter = age();
            out.println("STAGE4 info u1 at-limit limit_ns=" + ((double) timeoutNs() * tEq) + " age_before=" + aEq);
            check("u1 limit = an age read just before the call (strict <)", false, at + " age_before=" + aEq + " age_after=" + aAfter, !at);
            thr(thrForNs(age() - 300_000_000L)); boolean below = has();
            check("u1 limit 300 ms below the age", false, below, !below);
            int p1 = pending(); long u1 = usage();
            check("u1 queued requests unchanged by the calls", 1, p1, p1 == 1);
            check("u1 RequestsSize unchanged by the calls", usage0 + "+(<=M)", u1, u1 >= usage0 && u1 <= usage0 + M);
            thr(Double.MAX_VALUE);
            wa.send(5);
            waitFor("2 pending", () -> pending() == 2, 10_000);
            long aHead = age();
            check("u1 age is the head's (older than the 2nd queued request)", ">=" + a0, aHead, aHead >= a0);

            // u2: throwing refusal
            long disc0 = meter("requestDiscarded"); long u2a = usage(); int p2a = pending();
            thr(thrForNs(age() - 100_000_000L));
            check("u2 hasQueueCapacity false before the send", false, has(), !has());
            wb.send(0);
            waitFor("u2 response", () -> wb.respMs[0] > 0, 10_000);
            state("u2");
            check("u2 refused with the queue-age OverloadedException", "ovl_queue", wb.outcome[0], "ovl_queue".equals(wb.outcome[0]));
            out.println("STAGE4 info u2 text=" + wb.firstText[2]);
            check("u2 RequestDiscarded +1", disc0 + 1, meter("requestDiscarded"), meter("requestDiscarded") == disc0 + 1);
            check("u2 pending unchanged", p2a, pending(), pending() == p2a);
            check("u2 RequestsSize unchanged", u2a, usage(), usage() == u2a);
            thr(Double.MAX_VALUE);
            wb.send(1);
            waitFor("u2 allowed queued", () -> pending() == p2a + 1, 10_000);
            check("u2 at threshold off the next request is queued", p2a + 1, pending(), pending() == p2a + 1);

            // u3: default mode
            long paused0 = ClientMetrics.instance.getNumberOfPausedConnections(); int p3a = pending();
            thr(thrForNs(age() - 100_000_000L));
            wd.send(0);
            waitFor("u3 queued", () -> pending() == p3a + 1, 10_000);
            Thread.sleep(100);
            state("u3");
            check("u3 default mode: queued despite the overload", p3a + 1, pending(), pending() == p3a + 1);
            check("u3 default mode: no response before the release", -1L, wd.respMs[0], wd.respMs[0] < 0);
            long paused1 = ClientMetrics.instance.getNumberOfPausedConnections();
            check("u3 ConnectionPaused +1", paused0 + 1, paused1, paused1 == paused0 + 1);
            thr(Double.MAX_VALUE);
            releaseAll();
            Assert.assertTrue(wa.awaitAll(30_000) && wb.awaitAll(30_000) && wd.awaitAll(30_000));
            check("u3 default mode: the request ran, with the 'spent over' warning", "warned", wd.outcome[0], "warned".equals(wd.outcome[0]));
            StringBuilder s = new StringBuilder();
            for (int k = 0; k < 6; k++) s.append(wa.outcome[k]).append(',');
            out.println("STAGE4 info u0-u2 outcomes after release conn_a=" + s + " conn_b=" + wb.outcome[0] + "," + wb.outcome[1]);
            wa.stopReader(); wb.stopReader(); wd.stopReader();
        }

        // u4: the claim at unit scale
        double rate = 50, secs = 4;
        for (double t : new double[]{ Double.MAX_VALUE, 0.2, 0.05, 0.01 })
            sweepArm("u4", t, rate, secs, GiB);
        // u5: positive control
        ClientResourceLimits.setGlobalLimit(2 * MiB);
        sweepArm("u5", Double.MAX_VALUE, rate, secs, 2 * MiB);
        ClientResourceLimits.setGlobalLimit(GiB);

        out.println("STAGE4 summary mismatches=" + mismatches);
        Assert.assertEquals("instrument/set-up", 4, Dispatcher.requestExecutor.getMaximumPoolSize());
    }

    void sweepArm(String step, double t, double rate, double secs, long global) throws Exception
    {
        String name = step + " thr=" + (t == Double.MAX_VALUE ? "off" : String.valueOf(t));
        thr(t);
        int n = (int) Math.round(rate * secs);
        try (SimpleClient c = connect(true))
        {
            QueueAgeWriter w = writer(c, n);
            long disc0 = meter("requestDiscarded");
            stall();
            long peakPending = 0, peakActive = 0, peakUsage = 0;
            long t0 = System.currentTimeMillis();
            Thread sender = new Thread(() -> w.sendAtRate(0, rate, secs, null));
            sender.start();
            while (sender.isAlive())
            {
                peakPending = Math.max(peakPending, pending());
                peakActive = Math.max(peakActive, active());
                peakUsage = Math.max(peakUsage, usage());
                Thread.sleep(5);
            }
            Thread.sleep(300);
            peakPending = Math.max(peakPending, pending()); peakActive = Math.max(peakActive, active()); peakUsage = Math.max(peakUsage, usage());
            long refusedDuring = w.count("ovl_queue") + w.count("ovl_bytes");
            state(name + " end-of-send");
            long admitted = pending() + active();
            out.println("STAGE4 arm " + name + " limit_ms=" + (t == Double.MAX_VALUE ? "inf" : String.format("%.0f", t * timeoutNs() / 1e6))
                        + " global=" + global + " sent=" + w.sent() + " peak_pending=" + peakPending + " peak_active=" + peakActive
                        + " admitted=" + admitted + " queued_bytes=" + admitted * M + " peak_requests_size=" + peakUsage
                        + " refused_queue=" + w.count("ovl_queue") + " refused_bytes=" + w.count("ovl_bytes")
                        + " discarded=" + (meter("requestDiscarded") - disc0) + " send_ms=" + (System.currentTimeMillis() - t0));
            thr(Double.MAX_VALUE);
            releaseAll();
            boolean all = w.awaitAll(60_000);
            w.stopReader();
            out.println("STAGE4 arm " + name + " after-release " + w.line("counts") + " all_answered=" + all);
            check(name + " sent", n, w.sent(), w.sent() == n);
            check(name + " admitted + refused during the stall = sent", n, admitted + refusedDuring, admitted + refusedDuring == n);
            if (t == Double.MAX_VALUE && global == GiB)
                check(name + " check off: every request admitted", n, admitted, admitted == n);
            if (global < GiB)
                check(name + " control: RequestsSize <= the global limit", "<=" + global, peakUsage, peakUsage <= global && w.count("ovl_bytes") > 0);
        }
    }
}
