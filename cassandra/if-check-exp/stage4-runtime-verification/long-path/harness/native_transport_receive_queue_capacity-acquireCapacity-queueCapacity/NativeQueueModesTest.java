/*
 * Stage-4 harness, unit tier, for native_transport_receive_queue_capacity-acquireCapacity-queueCapacity
 * (case 9e, steps u0-u6, amended 2026-10-15). Copy into test/unit/org/apache/cassandra/transport/ of a
 * cassandra-5.0.9 clone and run with the Byteman agent and unit-hold.btm (unit-run.sh does both).
 *
 * One in-process server (CQLTester). Each step opens fresh protocol-v5 connections after setting the capacity, fills
 * both reserves with emulateInFlightConcurrentMessage (so that a request past the connection's capacity is refused),
 * and holds its requests at a gate (unit-hold.btm calls awaitGate() at the entry of Dispatcher.processRequest, i.e.
 * after the request was decoded). The server's own CQLMessageHandler for a client connection is found through
 * CQLTester.server's ConnectionTracker and read on its event loop. Every assertion prints
 *   STAGE4 check <name> expected=<x> actual=<y> ok|MISMATCH
 * to stdout and to -Dstage4.out, and the test goes on; it fails at the end if any check mismatched.
 */
package org.apache.cassandra.transport;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.net.SocketAddress;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.LongSupplier;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import com.codahale.metrics.Meter;
import io.netty.channel.Channel;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.cql3.QueryProcessor;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.metrics.ClientMetrics;
import org.apache.cassandra.net.AbstractMessageHandler;
import org.apache.cassandra.transport.messages.ErrorMessage;
import org.apache.cassandra.transport.messages.QueryMessage;
import org.apache.cassandra.utils.FBUtilities;

public class NativeQueueModesTest extends NativeProtocolLimitsTestBase
{
    private static final int BLOB = 4096;
    private static final String TABLE = "ntq_unit";

    // ---------------------------------------------------------------- the gate (called by unit-hold.btm)

    private static final Object GATE = new Object();
    private static volatile boolean gateOpen = true;
    private static final AtomicInteger arrivals = new AtomicInteger();   // requests decoded and dispatched

    public static void awaitGate()
    {
        arrivals.incrementAndGet();
        synchronized (GATE)
        {
            while (!gateOpen)
            {
                try { GATE.wait(); }
                catch (InterruptedException e) { Thread.currentThread().interrupt(); return; }
            }
        }
    }

    private static void closeGate() { gateOpen = false; }

    private static void openGate()
    {
        synchronized (GATE) { gateOpen = true; GATE.notifyAll(); }
    }

    // ---------------------------------------------------------------- output

    private static PrintWriter out;
    private static int checks, mismatches;

    private static void say(String s)
    {
        System.out.println(s);
        if (out != null) { out.println(s); out.flush(); }
    }

    private static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        checks++;
        if (!ok) mismatches++;
        say("STAGE4 check " + name + " expected=" + expected + " actual=" + actual + (ok ? " ok" : " MISMATCH"));
    }

    private static void checkTrue(String name, boolean cond, String detail)
    {
        checks++;
        if (!cond) mismatches++;
        say("STAGE4 check " + name + " " + detail + (cond ? " ok" : " MISMATCH"));
    }

    @BeforeClass
    public static void setUp() throws IOException
    {
        String f = System.getProperty("stage4.out");
        if (f != null)
            out = new PrintWriter(new FileWriter(f, true));
        requireNetwork();
    }

    @AfterClass
    public static void tearDown()
    {
        openGate();
        DatabaseDescriptor.setNativeTransportReceiveQueueCapacityInBytes(1 << 20);
        DatabaseDescriptor.setNativeTransportThrowOnOverload(false);
        say("STAGE4 summary checks=" + checks + " mismatches=" + mismatches);
        if (out != null) out.close();
    }

    // ---------------------------------------------------------------- helpers

    private QueryMessage request()
    {
        ByteBuffer v = ByteBuffer.allocate(BLOB);
        QueryOptions options = QueryOptions.create(ConsistencyLevel.ONE, Collections.singletonList(v), false, -1, null,
                                                   null, version, null);
        return new QueryMessage("SELECT pk FROM " + KEYSPACE + '.' + TABLE + " WHERE pk = 0 AND v = ? ALLOW FILTERING", options);
    }

    private static int streamIds = 1;

    /** Sends without waiting for the response (as SimpleClient.execute(List) frames a request). */
    private static void send(SimpleClient client, Message.Request request)
    {
        request.setSource(new Envelope(Envelope.Header.dummy(streamIds++, request.type), null));
        request.attach(client.connection);
        client.channel.writeAndFlush(Collections.singletonList(request));
    }

    private static Message.Response next(SimpleClient client) throws InterruptedException
    {
        Message.Response r = client.responseHandler.responses.poll(20, TimeUnit.SECONDS);
        if (r == null)
            throw new AssertionError("no response within 20 s");
        return r;
    }

    private static List<Message.Response> next(SimpleClient client, int n) throws InterruptedException
    {
        List<Message.Response> l = new ArrayList<>();
        for (int i = 0; i < n; i++)
            l.add(next(client));
        return l;
    }

    private static boolean noResponseFor(SimpleClient client, long ms) throws InterruptedException
    {
        Message.Response r = client.responseHandler.responses.poll(ms, TimeUnit.MILLISECONDS);
        return r == null;
    }

    @SuppressWarnings("unchecked")
    private static CQLMessageHandler<Message.Request> serverHandler(SimpleClient client) throws Exception
    {
        Field fs = CQLTester.class.getDeclaredField("server");
        fs.setAccessible(true);
        Server server = (Server) fs.get(null);
        Field ft = Server.class.getDeclaredField("connectionTracker");
        ft.setAccessible(true);
        Server.ConnectionTracker tracker = (Server.ConnectionTracker) ft.get(server);
        SocketAddress local = client.channel.localAddress();
        for (int attempt = 0; attempt < 100; attempt++)
        {
            for (Channel ch : tracker.allChannels)
                if (local.equals(ch.remoteAddress()) && ch.pipeline().get("cqlProcessor") != null)
                    return (CQLMessageHandler<Message.Request>) ch.pipeline().get("cqlProcessor");
            Thread.sleep(50);
        }
        throw new AssertionError("no server handler for " + local);
    }

    private static Field field(Class<?> c, String name) throws NoSuchFieldException
    {
        Field f = c.getDeclaredField(name);
        f.setAccessible(true);
        return f;
    }

    /** Reads on the handler's event loop, where the handler itself updates these fields. */
    private static long onLoop(CQLMessageHandler<?> h, LongSupplier s) throws Exception
    {
        Channel ch = (Channel) field(AbstractMessageHandler.class, "channel").get(h);
        return ch.eventLoop().submit(s::getAsLong).get(10, TimeUnit.SECONDS);
    }

    private static long queueSize(CQLMessageHandler<?> h) throws Exception
    {
        Field f = field(AbstractMessageHandler.class, "queueSize");
        return onLoop(h, () -> { try { return f.getLong(h); } catch (IllegalAccessException e) { throw new RuntimeException(e); } });
    }

    private static long queueCapacity(CQLMessageHandler<?> h) throws Exception
    {
        return field(AbstractMessageHandler.class, "queueCapacity").getLong(h);
    }

    private static boolean throwOnOverload(CQLMessageHandler<?> h) throws Exception
    {
        return field(CQLMessageHandler.class, "throwOnOverload").getBoolean(h);
    }

    private static long inflight(CQLMessageHandler<?> h) throws Exception
    {
        return onLoop(h, () -> h.channelPayloadBytesInFlight);
    }

    private static long discarded() throws Exception
    {
        return ((Meter) field(ClientMetrics.class, "requestDiscarded").get(ClientMetrics.instance)).getCount();
    }

    /** Waits until the supplier reaches the value (or 10 s), then returns its last reading. */
    private static long await(LongSupplierEx s, long value) throws Exception
    {
        long v = s.get();
        for (int i = 0; i < 200 && v != value; i++)
        {
            Thread.sleep(50);
            v = s.get();
        }
        return v;
    }

    interface LongSupplierEx { long get() throws Exception; }

    private void reservesFull(long m)
    {
        ClientResourceLimits.setGlobalLimit(2 * m);
        ClientResourceLimits.setEndpointLimit(2 * m);
        emulateInFlightConcurrentMessage(2 * m);
    }

    /** Frees the emulated reserve use and signals both wait queues (a Limit's release alone signals nobody). */
    private void reservesFree(long m)
    {
        releaseEmulatedCapacity(2 * m);
        emulatedUsedCapacity -= 2 * m;
        ClientResourceLimits.ResourceProvider p =
            new ClientResourceLimits.ResourceProvider.Default(ClientResourceLimits.getAllocatorForEndpoint(FBUtilities.getJustLocalAddress()));
        p.globalWaitQueue().signal();
        p.endpointWaitQueue().signal();
    }

    private static String warnings(Message.Response r)
    {
        return r.getWarnings() == null ? "" : String.join("|", r.getWarnings());
    }

    private static boolean isOverloadBytes(Message.Response r)
    {
        return r instanceof ErrorMessage && ((ErrorMessage) r).error.getMessage().contains("bytes in flight");
    }

    // ---------------------------------------------------------------- the steps

    @Test
    public void steps() throws Throwable
    {
        QueryProcessor.executeOnceInternal("CREATE TABLE IF NOT EXISTS " + KEYSPACE + '.' + TABLE + " (pk int PRIMARY KEY, v blob)");

        // u0: M, the request's body size, at a capacity that admits it
        DatabaseDescriptor.setNativeTransportReceiveQueueCapacityInBytes(1 << 20);
        ClientResourceLimits.setGlobalLimit(1 << 24);
        ClientResourceLimits.setEndpointLimit(1 << 24);
        long m;
        try (SimpleClient c = client(false))
        {
            CQLMessageHandler<?> h = serverHandler(c);
            check("u0.cap", 1 << 20, queueCapacity(h));
            closeGate();
            arrivals.set(0);
            send(c, request());
            await(() -> arrivals.get(), 1);
            m = inflight(h);
            check("u0.queueSize_eq_inflight", m, queueSize(h));
            checkTrue("u0.M", m > BLOB && m < BLOB + 200, "M=" + m);
            openGate();
            check("u0.response_ok", false, next(c) instanceof ErrorMessage);
            check("u0.queueSize_end", 0, await(() -> queueSize(h), 0));
        }
        long cap = 3 * m;
        say("STAGE4 note M=" + m + " C=" + cap + " reserves=" + 2 * m);

        // u1: throwing mode, small request
        DatabaseDescriptor.setNativeTransportReceiveQueueCapacityInBytes((int) cap);
        try (SimpleClient c = client(true))
        {
            CQLMessageHandler<?> h = serverHandler(c);
            check("u1.throw", true, throwOnOverload(h));
            reservesFull(m);
            closeGate();
            arrivals.set(0);
            long d0 = discarded();
            for (int i = 0; i < 3; i++)
                send(c, request());
            check("u1.accepted_queueSize_at_C", cap, await(() -> queueSize(h), cap));
            check("u1.decoded3", 3, await(() -> arrivals.get(), 3));
            send(c, request());
            Message.Response r4 = next(c);
            checkTrue("u1.fourth_overloaded_bytes", isOverloadBytes(r4), "response=" + r4);
            check("u1.discarded_delta", 1, discarded() - d0);
            check("u1.queueSize_after_refusal", cap, queueSize(h));
            check("u1.inflight_after_refusal", cap, inflight(h));
            check("u1.not_decoded", 3, arrivals.get());
            openGate();
            List<Message.Response> rs = next(c, 3);
            check("u1.three_ok", 0, rs.stream().filter(x -> x instanceof ErrorMessage).count());
            check("u1.queueSize_end", 0, await(() -> queueSize(h), 0));
            reservesFree(m);
        }

        // u2 + u3: default mode, small request; the refused request is decoded and the release drifts
        DatabaseDescriptor.setNativeTransportReceiveQueueCapacityInBytes((int) cap);
        try (SimpleClient c = client(false))
        {
            CQLMessageHandler<?> h = serverHandler(c);
            check("u2.throw", false, throwOnOverload(h));
            reservesFull(m);
            closeGate();
            arrivals.set(0);
            long d0 = discarded();
            for (int i = 0; i < 3; i++)
                send(c, request());
            check("u2.accepted_queueSize_at_C", cap, await(() -> queueSize(h), cap));
            send(c, request());
            check("u2.fourth_decoded", 4, await(() -> arrivals.get(), 4));
            check("u2.inflight_4M", 4 * m, inflight(h));
            check("u2.queueSize_stays_C", cap, queueSize(h));
            send(c, request());   // the fifth: the connection is paused
            checkTrue("u2.fifth_not_decoded", noResponseFor(c, 500) && arrivals.get() == 4, "arrivals=" + arrivals.get());
            check("u2.inflight_still_4M", 4 * m, inflight(h));
            openGate();
            List<Message.Response> rs = next(c, 4);
            check("u2.four_ok", 0, rs.stream().filter(x -> x instanceof ErrorMessage).count());
            check("u2.warned", 1, rs.stream().filter(x -> warnings(x).contains("bytes in flight")).count());
            check("u2.discarded_delta", 0, discarded() - d0);
            check("u2.queueSize_after_releases", -m, await(() -> queueSize(h), -m));
            checkTrue("u2.fifth_still_waiting", noResponseFor(c, 500) && arrivals.get() == 4, "arrivals=" + arrivals.get());
            reservesFree(m);
            Message.Response r5 = next(c);
            check("u2.fifth_ok_after_reserve", false, r5 instanceof ErrorMessage);
            check("u2.fifth_no_warning", "", warnings(r5));
            check("u2.queueSize_end", -m, await(() -> queueSize(h), -m));
            check("u2.inflight_end", 0, inflight(h));

            // u3: the same connection now admits C + M of its own
            reservesFull(m);
            closeGate();
            arrivals.set(0);
            for (int i = 0; i < 4; i++)
                send(c, request());
            check("u3.four_decoded", 4, await(() -> arrivals.get(), 4));
            check("u3.queueSize", cap, await(() -> queueSize(h), cap));
            check("u3.inflight_4M", 4 * m, inflight(h));
            openGate();
            rs = next(c, 4);
            check("u3.no_warning", 0, rs.stream().filter(x -> warnings(x).contains("bytes in flight")).count());
            check("u3.queueSize_end", -m, await(() -> queueSize(h), -m));
            reservesFree(m);
        }

        // u4: default mode, multi-frame request: the refused request waits, undecoded, for the reserve
        DatabaseDescriptor.setNativeTransportReceiveQueueCapacityInBytes((int) cap);
        try (SimpleClient c = client(false, 1024))
        {
            CQLMessageHandler<?> h = serverHandler(c);
            reservesFull(m);
            closeGate();
            arrivals.set(0);
            long d0 = discarded();
            for (int i = 0; i < 3; i++)
                send(c, request());
            check("u4.decoded3", 3, await(() -> arrivals.get(), 3));
            check("u4.queueSize_C", cap, await(() -> queueSize(h), cap));
            send(c, request());
            checkTrue("u4.fourth_not_decoded", noResponseFor(c, 500) && arrivals.get() == 3, "arrivals=" + arrivals.get());
            check("u4.inflight_not_raised_large_path", 0, inflight(h));
            openGate();
            List<Message.Response> rs = next(c, 3);
            check("u4.three_ok", 0, rs.stream().filter(x -> x instanceof ErrorMessage).count());
            check("u4.queueSize_0_after_releases", 0, await(() -> queueSize(h), 0));
            checkTrue("u4.fourth_waits_for_reserve", noResponseFor(c, 500) && arrivals.get() == 3, "arrivals=" + arrivals.get());
            reservesFree(m);
            Message.Response r4 = next(c);
            check("u4.fourth_ok", false, r4 instanceof ErrorMessage);
            check("u4.fourth_no_warning", "", warnings(r4));
            check("u4.decoded4", 4, arrivals.get());
            check("u4.discarded_delta", 0, discarded() - d0);
            check("u4.queueSize_end", 0, await(() -> queueSize(h), 0));
        }

        // u5: throwing mode, multi-frame request
        DatabaseDescriptor.setNativeTransportReceiveQueueCapacityInBytes((int) cap);
        try (SimpleClient c = client(true, 1024))
        {
            CQLMessageHandler<?> h = serverHandler(c);
            reservesFull(m);
            closeGate();
            arrivals.set(0);
            long d0 = discarded();
            for (int i = 0; i < 3; i++)
                send(c, request());
            check("u5.decoded3", 3, await(() -> arrivals.get(), 3));
            send(c, request());
            Message.Response r4 = next(c);
            checkTrue("u5.fourth_overloaded_bytes", isOverloadBytes(r4), "response=" + r4);
            check("u5.discarded_delta", 1, discarded() - d0);
            check("u5.not_decoded", 3, arrivals.get());
            check("u5.queueSize_C", cap, queueSize(h));
            openGate();
            next(c, 3);
            check("u5.queueSize_end", 0, await(() -> queueSize(h), 0));
            reservesFree(m);
        }

        // u6: wiring, the capacity per new connection, the mode per connection
        DatabaseDescriptor.setNativeTransportReceiveQueueCapacityInBytes(123456);
        try (SimpleClient c1 = client(false))
        {
            CQLMessageHandler<?> h1 = serverHandler(c1);
            check("u6.cap1", 123456, queueCapacity(h1));
            DatabaseDescriptor.setNativeTransportReceiveQueueCapacityInBytes(654321);
            try (SimpleClient c2 = client(true))
            {
                CQLMessageHandler<?> h2 = serverHandler(c2);
                check("u6.cap2", 654321, queueCapacity(h2));
                check("u6.cap1_unchanged", 123456, queueCapacity(h1));
                check("u6.throw_option", true, throwOnOverload(h2));
                check("u6.no_option_takes_config_false", false, throwOnOverload(h1));
            }
            DatabaseDescriptor.setNativeTransportThrowOnOverload(true);
            try (SimpleClient c3 = client(false))
            {
                check("u6.no_option_takes_config_true", true, throwOnOverload(serverHandler(c3)));
            }
            DatabaseDescriptor.setNativeTransportThrowOnOverload(false);
        }

        Assert.assertEquals("STAGE4 mismatches", 0, mismatches);
    }
}
