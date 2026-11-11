/*
 * Stage-4 harness, unit tier of internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes
 * (case file section 9, 9e unit steps U1 to U9). Not part of upstream Cassandra.
 * Copy into test/unit/org/apache/cassandra/net/ of a local clone at cassandra-5.0.9 (package-private hooks are used).
 * System property stage4.out: a file that also receives the STAGE4 lines.
 *
 * It drives the check alone: it builds an OutboundConnection the way ConnectionTest.doTestManual() does, with an explicit capacity C and explicit
 * per-peer (E) and node-wide (G) reserves, and calls the private acquireCapacity(long count, long bytes) by reflection so that it sees the Outcome
 * (the package-private unsafeAcquireCapacity() returns only a boolean). U8 sends real messages through enqueue() to an inbound socket.
 * The reserve wiring (which config key reaches the per-peer limit) is SendQueueWiringTest, in its own JVM.
 */
package org.apache.cassandra.net;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.reflect.Method;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.util.Collections;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.commitlog.CommitLog;
import org.apache.cassandra.exceptions.RequestFailureReason;
import org.apache.cassandra.io.IVersionedSerializer;
import org.apache.cassandra.io.util.DataInputPlus;
import org.apache.cassandra.io.util.DataOutputPlus;
import org.apache.cassandra.locator.InetAddressAndPort;
import org.apache.cassandra.net.ResourceLimits.Concurrent;
import org.apache.cassandra.net.ResourceLimits.EndpointAndGlobal;
import org.apache.cassandra.net.ResourceLimits.Outcome;
import org.apache.cassandra.utils.FBUtilities;

import static java.util.concurrent.TimeUnit.SECONDS;
import static org.apache.cassandra.net.ConnectionType.LARGE_MESSAGES;
import static org.apache.cassandra.net.MessagingService.current_version;

public class SendQueueCapacityTest
{
    private static final SocketFactory factory = new SocketFactory();
    static PrintWriter out;
    static int mismatches = 0;
    static Method acquire;

    @BeforeClass
    public static void setup() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        CommitLog.instance.start();
        String f = System.getProperty("stage4.out");
        if (f != null)
            out = new PrintWriter(new FileWriter(f, true));
        acquire = OutboundConnection.class.getDeclaredMethod("acquireCapacity", long.class, long.class);
        acquire.setAccessible(true);
        line("STAGE4 info SendQueueCapacityTest start; default capacity=" + DatabaseDescriptor.getInternodeApplicationSendQueueCapacityInBytes()
             + " current_version=" + current_version);
    }

    @AfterClass
    public static void cleanup() throws Exception
    {
        if (origSerializer != null)
            Verb._TEST_1.unsafeSetSerializer(origSerializer);
        if (origHandler != null)
            Verb._TEST_1.unsafeSetHandler(origHandler);
        line("STAGE4 info SendQueueCapacityTest end; mismatches=" + mismatches);
        if (out != null)
            out.close();
        factory.shutdownNow();
    }

    static void line(String s)
    {
        System.out.println(s);
        if (out != null) { out.println(s); out.flush(); }
    }

    static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        if (!ok) mismatches++;
        line("STAGE4 check " + name + " " + expected + " " + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    static void checkTrue(String name, boolean cond, String detail)
    {
        if (!cond) mismatches++;
        line("STAGE4 check " + name + " true " + cond + " " + (cond ? "ok" : "MISMATCH") + " [" + detail + "]");
    }

    /** One connection under test with its own reserves, kept so that the node-wide reserve can be read. */
    static class Conn
    {
        final OutboundConnection c;
        final ResourceLimits.Limit endpoint;
        final ResourceLimits.Limit global;

        Conn(ConnectionType type, int capacity, long e, long g, InetAddressAndPort to)
        {
            endpoint = new Concurrent(e);
            global = new Concurrent(g);
            OutboundConnectionSettings s = new OutboundConnectionSettings(to)
                                           .withApplicationSendQueueCapacityInBytes(capacity)
                                           .withApplicationReserveSendQueueCapacityInBytes((int) e, global)
                                           .withSocketFactory(factory)
                                           .withDefaults(ConnectionCategory.MESSAGING);
            c = new OutboundConnection(type, s, new EndpointAndGlobal(endpoint, global));
        }

        Outcome acq(long count, long bytes) throws Exception
        {
            return (Outcome) acquire.invoke(c, count, bytes);
        }

        void rel(long count, long bytes)
        {
            c.unsafeReleaseCapacity(count, bytes);
        }

        /** "pending,count,endpoint,global" for one check line */
        String state()
        {
            return c.pendingBytes() + "," + c.pendingCount() + "," + endpoint.using() + "," + global.using();
        }

        void close() throws Exception
        {
            c.close(false).get(30L, SECONDS);
        }
    }

    static InetAddressAndPort self()
    {
        return FBUtilities.getBroadcastAddressAndPort();
    }

    /** U1 to U6: C = 4096, E = 1500, G = 1000, a large-type connection that is never connected. */
    @Test
    public void testBoundaryBorrowRefusalRelease() throws Exception
    {
        Conn k = new Conn(LARGE_MESSAGES, 4096, 1500, 1000, self());
        try
        {
            // U1: the compare is <=, so a message that exactly fills C borrows nothing
            check("U1 outcome", Outcome.SUCCESS, k.acq(1, 4096));
            check("U1 state pending,count,endpoint,global", "4096,1,0,0", k.state());
            // U2: one byte over
            check("U2 outcome", Outcome.SUCCESS, k.acq(1, 1));
            check("U2 state pending,count,endpoint,global", "4097,2,1,1", k.state());
            // U3: to the reserve's edge (G = 1000)
            check("U3 outcome", Outcome.SUCCESS, k.acq(1, 999));
            check("U3 state pending,count,endpoint,global", "5096,3,1000,1000", k.state());
            // U4: the first refusal; the node-wide reserve is tried first
            check("U4 outcome", Outcome.INSUFFICIENT_GLOBAL, k.acq(1, 1));
            check("U4 state pending,count,endpoint,global", "5096,3,1000,1000", k.state());
            // U5: release returns the reserve first (only min(pending - C, bytes) goes back)
            k.rel(1, 1000);
            check("U5a state after release 1000", "4096,2,0,0", k.state());
            k.rel(2, 4096);
            check("U5b state after release 4096", "0,0,0,0", k.state());
        }
        finally { k.close(); }

        // U6: only the excess is borrowed, not the whole message
        Conn j = new Conn(LARGE_MESSAGES, 4096, 1500, 1000, self());
        try
        {
            check("U6a outcome acquire 3000", Outcome.SUCCESS, j.acq(1, 3000));
            check("U6a state pending,count,endpoint,global", "3000,1,0,0", j.state());
            check("U6b outcome acquire 2000", Outcome.SUCCESS, j.acq(1, 2000));
            check("U6b state pending,count,endpoint,global (904 = 3000 + 2000 - 4096)", "5000,2,904,904", j.state());
        }
        finally { j.close(); }
        Assert.assertEquals("mismatches so far", 0, mismatches);
    }

    /** U7: the other refusal; a fresh connection with E = 1000 and G = 1500. */
    @Test
    public void testEndpointRefusalRollsBackGlobal() throws Exception
    {
        Conn k = new Conn(LARGE_MESSAGES, 4096, 1000, 1500, self());
        try
        {
            check("U7 fill outcome 4096", Outcome.SUCCESS, k.acq(1, 4096));
            check("U7 fill outcome 1", Outcome.SUCCESS, k.acq(1, 1));
            check("U7 fill outcome 999", Outcome.SUCCESS, k.acq(1, 999));
            check("U7 filled state pending,count,endpoint,global", "5096,3,1000,1000", k.state());
            long globalBefore = k.global.using();
            check("U7 outcome", Outcome.INSUFFICIENT_ENDPOINT, k.acq(1, 1));
            check("U7 global using back at its value before the attempt", globalBefore, k.global.using());
            check("U7 state pending,count,endpoint,global", "5096,3,1000,1000", k.state());
        }
        finally { k.close(); }
        Assert.assertEquals("mismatches so far", 0, mismatches);
    }

    static java.util.function.Supplier<? extends org.apache.cassandra.io.IVersionedAsymmetricSerializer<?, ?>> origSerializer;
    static java.util.function.Supplier<? extends IVerbHandler<?>> origHandler;

    static void setTest1Serializer(int size) throws Exception
    {
        java.util.function.Supplier<? extends org.apache.cassandra.io.IVersionedAsymmetricSerializer<?, ?>> prev = Verb._TEST_1.unsafeSetSerializer(() -> new IVersionedSerializer<Object>()
        {
            public void serialize(Object o, DataOutputPlus out, int version) throws java.io.IOException
            {
                for (int i = 0; i < size; i += 8)
                    out.writeLong(1L);
            }

            public Object deserialize(DataInputPlus in, int version) throws java.io.IOException
            {
                in.skipBytesFully(size);
                return null;
            }

            public long serializedSize(Object o, int version)
            {
                return size;
            }
        });
        if (origSerializer == null)
            origSerializer = prev;
    }

    /** U8: enqueue() accepts a message that borrows and drops one that cannot. C = 64 KiB, E = 32 KiB, G = 64 KiB, an inbound socket on this host. */
    @Test
    public void testEnqueueAcceptsAndDrops() throws Throwable
    {
        InetAddressAndPort endpoint = self();
        InboundConnectionSettings inboundSettings = new InboundConnectionSettings().withBindAddress(endpoint).withSocketFactory(factory);
        InboundSockets inbound = new InboundSockets(Collections.singletonList(inboundSettings));
        Conn k = new Conn(LARGE_MESSAGES, 1 << 16, 1 << 15, 1 << 16, endpoint);
        AtomicInteger delivered = new AtomicInteger();
        try
        {
            inbound.open().sync();
            java.util.function.Supplier<? extends IVerbHandler<?>> prevHandler = Verb._TEST_1.unsafeSetHandler(() -> msg -> delivered.incrementAndGet());
            if (origHandler == null)
                origHandler = prevHandler;

            // an 80 KiB message: 16 KiB (plus its header) beyond C, below C + F = 96 KiB -> accepted and delivered
            setTest1Serializer(80 << 10);
            Message<?> accepted = Message.out(Verb._TEST_1, new Object());
            long acceptedSize = accepted.serializedSize(current_version);
            checkTrue("U8a message size is above C and below C + F", acceptedSize > (1 << 16) && acceptedSize <= (1 << 16) + (1 << 15), "size=" + acceptedSize);
            k.c.enqueue(accepted);
            long deadline = System.nanoTime() + SECONDS.toNanos(10);
            while (delivered.get() < 1 && System.nanoTime() < deadline)
                Thread.sleep(20);
            check("U8a delivered", 1, delivered.get());
            check("U8a overloadedCount", 0, k.c.overloadedCount());
            deadline = System.nanoTime() + SECONDS.toNanos(10);
            while ((k.c.pendingBytes() != 0 || k.endpoint.using() != 0 || k.global.using() != 0) && System.nanoTime() < deadline)
                Thread.sleep(20);
            check("U8a drained state pending,count,endpoint,global", "0,0,0,0", k.state());

            // a 256 KiB message (upstream's case): beyond C + F -> dropped, counted, callback failed, nothing delivered
            setTest1Serializer(4 << 16);
            Message<?> dropped = Message.out(Verb._TEST_1, new Object());
            long droppedSize = dropped.serializedSize(current_version);
            CountDownLatch failed = new CountDownLatch(1);
            MessagingService.instance().callbacks.addWithExpiration(new RequestCallback()
            {
                public void onFailure(InetAddressAndPort from, RequestFailureReason failureReason) { failed.countDown(); }
                public boolean invokeOnFailure() { return true; }
                public void onResponse(Message msg) { throw new IllegalStateException(); }
            }, dropped, endpoint);
            k.c.enqueue(dropped);
            checkTrue("U8b callback failed within 10 s", failed.await(10, SECONDS), "");
            Thread.sleep(500);
            check("U8b delivered stays", 1, delivered.get());
            check("U8b overloadedCount", 1, k.c.overloadedCount());
            check("U8b overloadedBytes", droppedSize, k.c.overloadedBytes());
            check("U8b state pending,count,endpoint,global", "0,0,0,0", k.state());
        }
        finally
        {
            k.close();
            inbound.close().get(30L, SECONDS);
            MessagingService.instance().messageHandlers.clear();
        }
        Assert.assertEquals("mismatches so far", 0, mismatches);
    }

    /** U9: a connection to an unreachable peer borrows nothing; the same acquire on a not-connecting connection does. */
    @Test
    public void testUnreachablePeerBorrowsNothing() throws Throwable
    {
        int port;
        try (ServerSocket s = new ServerSocket(0, 1, InetAddress.getLoopbackAddress()))
        {
            port = s.getLocalPort();
        }
        // nothing listens on `port` any more
        InetAddressAndPort dead = InetAddressAndPort.getByAddressOverrideDefaults(InetAddress.getLoopbackAddress(), port);
        int capacity = 1 << 12;
        Conn k = new Conn(LARGE_MESSAGES, capacity, 1 << 20, 1 << 20, dead);
        try
        {
            setTest1Serializer(100);
            Message<?> m = Message.out(Verb._TEST_1, new Object());
            long size = m.serializedSize(current_version);
            k.c.enqueue(m);
            long deadline = System.nanoTime() + SECONDS.toNanos(30);
            while (k.c.connectionAttempts() < 2 && System.nanoTime() < deadline)
                Thread.sleep(50);
            checkTrue("U9 connection attempts >= 2 (the link is failing to connect)", k.c.connectionAttempts() >= 2, "attempts=" + k.c.connectionAttempts());
            check("U9 pending after the one small enqueue", size, k.c.pendingBytes());
            long ask = capacity - k.c.pendingBytes() + 1;
            check("U9 outcome acquire C - pending + 1 (unreachable peer)", Outcome.INSUFFICIENT_ENDPOINT, k.acq(1, ask));
            check("U9 reserves in use endpoint,global", "0,0", k.endpoint.using() + "," + k.global.using());
        }
        finally { k.close(); }

        // the control: the same acquire on a connection that is not failing to connect (never connected) borrows
        Conn j = new Conn(LARGE_MESSAGES, capacity, 1 << 20, 1 << 20, self());
        try
        {
            check("U9 control fill", Outcome.SUCCESS, j.acq(1, capacity));
            check("U9 control outcome acquire 1 over C", Outcome.SUCCESS, j.acq(1, 1));
            check("U9 control reserves in use endpoint,global", "1,1", j.endpoint.using() + "," + j.global.using());
        }
        finally { j.close(); }
        Assert.assertEquals("mismatches so far", 0, mismatches);
    }
}
