/*
 * Stage-4 harness, unit tier (B2) of internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous.
 * Not part of upstream Cassandra. Copy into test/unit/org/apache/cassandra/net/ of a local clone at cassandra-5.0.9
 * (package-private access to OutboundConnection); unit-run.sh does that and removes it after.
 * System property stage4.out: a file that also receives the STAGE4 lines.
 *
 * B2c/B2e: for L in {64 KiB, 1 MiB, 8 MiB} (DatabaseDescriptor.setInternodeMaxMessageSizeInBytes), one fresh
 * OutboundConnection of type LARGE_MESSAGES per L, with the default send-queue capacity (4 MiB) and the default reserves
 * (128 MiB per peer, 512 MiB node-wide), toward a loopback port that accepts TCP but never answers the handshake (a bound
 * ServerSocket that is never accept()ed), so that nothing is delivered and nothing drains pendingBytes while the case
 * runs; ConnectionTest's "not listening" peer would turn the link into "failing to connect" after the first refused
 * attempt, and such a link refuses every reserve (OutboundConnection.java:409-413), which is not the check under test.
 * Payload: a byte[] on Verb._TEST_1 with a byte-array serializer (serializedSize = length), so S =
 * message.serializedSize(current_version) is read from the object and P adjusted until S is exactly L-1, L, L+1, 2L.
 * Per case: enqueue's outcome, and the change of pendingBytes(), pendingCount(), submittedCount(), overloadedCount(),
 * plus heap used (sanity only). B2e step 4: the same cases at the largest settable limit (Integer.MAX_VALUE - 1; see the
 * results file, defect 1). B2h: the size at VERSION_40 and VERSION_50 and the link's messagingVersion().
 * One "STAGE4 case" line per enqueue and one "STAGE4 check ... ok|MISMATCH" line per prediction of B2f.
 */
package org.apache.cassandra.net;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.net.InetAddress;
import java.net.ServerSocket;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.commitlog.CommitLog;
import org.apache.cassandra.io.IVersionedSerializer;
import org.apache.cassandra.io.util.DataInputPlus;
import org.apache.cassandra.io.util.DataOutputPlus;
import org.apache.cassandra.locator.InetAddressAndPort;
import org.apache.cassandra.net.ResourceLimits.Concurrent;
import org.apache.cassandra.net.ResourceLimits.EndpointAndGlobal;

import static java.util.concurrent.TimeUnit.SECONDS;
import static org.apache.cassandra.net.ConnectionType.LARGE_MESSAGES;
import static org.apache.cassandra.net.MessagingService.VERSION_40;
import static org.apache.cassandra.net.MessagingService.VERSION_50;
import static org.apache.cassandra.net.MessagingService.current_version;

public class MaxMessageSizeProbeTest
{
    private static final SocketFactory factory = new SocketFactory();
    static PrintWriter out;
    static int mismatches = 0;
    static int checks = 0;
    static java.util.function.Supplier<? extends org.apache.cassandra.io.IVersionedAsymmetricSerializer<?, ?>> origSerializer;
    static ServerSocket silent;
    static int origLimit;

    static final int KIB = 1024, MIB = 1 << 20;
    static final int[] LIMITS = { 64 * KIB, MIB, 8 * MIB };
    static final int CONTROL_LIMIT = Integer.MAX_VALUE - 1;

    @BeforeClass
    public static void setup() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        CommitLog.instance.start();   // as SendQueueCapacityTest: Message.out() opens system keyspaces
        String f = System.getProperty("stage4.out");
        if (f != null)
            out = new PrintWriter(new FileWriter(f, true));
        origLimit = DatabaseDescriptor.getInternodeMaxMessageSizeInBytes();
        origSerializer = Verb._TEST_1.unsafeSetSerializer(() -> new IVersionedSerializer<byte[]>()
        {
            public void serialize(byte[] b, DataOutputPlus o, int version) throws java.io.IOException { o.write(b); }
            public byte[] deserialize(DataInputPlus in, int version) throws java.io.IOException { throw new UnsupportedOperationException(); }
            public long serializedSize(byte[] b, int version) { return b.length; }
        });
        silent = new ServerSocket(0, 50, InetAddress.getLoopbackAddress());   // bound, listening, never accept()ed
        Runtime r = Runtime.getRuntime();
        line("STAGE4 env maxMemory=" + r.maxMemory() + " current_version=" + current_version + " default_limit=" + origLimit
             + " send_queue_capacity=" + DatabaseDescriptor.getInternodeApplicationSendQueueCapacityInBytes()
             + " reserve_endpoint=" + DatabaseDescriptor.getInternodeApplicationSendQueueReserveEndpointCapacityInBytes()
             + " reserve_global=" + DatabaseDescriptor.getInternodeApplicationSendQueueReserveGlobalCapacityInBytes()
             + " silent_port=" + silent.getLocalPort());
    }

    @AfterClass
    public static void cleanup() throws Exception
    {
        if (origSerializer != null)
            Verb._TEST_1.unsafeSetSerializer(origSerializer);
        DatabaseDescriptor.setInternodeMaxMessageSizeInBytes(origLimit);
        if (silent != null)
            silent.close();
        try
        {
            MessagingService.instance().shutdown();   // B2e step 5
            line("STAGE4 info MessagingService.shutdown() returned");
        }
        catch (Throwable t)
        {
            line("STAGE4 info MessagingService.shutdown() threw " + t);
        }
        line("STAGE4 summary checks=" + checks + " mismatches=" + mismatches);
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
        checks++;
        if (!ok) mismatches++;
        line("STAGE4 check " + name + " expected=" + expected + " actual=" + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    /** a _TEST_1 message whose serializedSize(current_version) is exactly s (P adjusted for the header) */
    static Message<byte[]> messageOfSize(int s)
    {
        int p = s - 64;
        for (int i = 0; i < 20; i++)
        {
            Message<byte[]> m = Message.out(Verb._TEST_1, new byte[p]);
            int got = m.serializedSize(current_version);
            if (got == s)
                return m;
            p += s - got;
        }
        throw new IllegalStateException("could not build a message of size " + s);
    }

    static OutboundConnection connection()
    {
        InetAddressAndPort to = InetAddressAndPort.getByAddressOverrideDefaults(InetAddress.getLoopbackAddress(), silent.getLocalPort());
        OutboundConnectionSettings s = new OutboundConnectionSettings(to)
                                       .withApplicationSendQueueCapacityInBytes(DatabaseDescriptor.getInternodeApplicationSendQueueCapacityInBytes())
                                       .withSocketFactory(factory)
                                       .withDefaults(ConnectionCategory.MESSAGING);
        EndpointAndGlobal reserves = new EndpointAndGlobal(new Concurrent(DatabaseDescriptor.getInternodeApplicationSendQueueReserveEndpointCapacityInBytes()),
                                                           new Concurrent(DatabaseDescriptor.getInternodeApplicationSendQueueReserveGlobalCapacityInBytes()));
        return new OutboundConnection(LARGE_MESSAGES, s, reserves);
    }

    static long heapUsed()
    {
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    /** one L (or the control limit) against S = L-1, L, L+1, 2L of the given L; returns nothing, checks inline */
    static void runLimit(String tag, int limit, int l) throws Exception
    {
        DatabaseDescriptor.setInternodeMaxMessageSizeInBytes(limit);
        check(tag + " limit read back", limit, DatabaseDescriptor.getInternodeMaxMessageSizeInBytes());
        OutboundConnection c = connection();
        try
        {
            long[] sizes = { l - 1L, l, l + 1L, 2L * l };
            String[] names = { "L-1", "L", "L+1", "2L" };
            for (int i = 0; i < sizes.length; i++)
            {
                Message<byte[]> m = messageOfSize((int) sizes[i]);
                int s40 = m.serializedSize(VERSION_40), s50 = m.serializedSize(VERSION_50);
                long p0 = c.pendingBytes(), n0 = c.pendingCount(), sub0 = c.submittedCount(), ov0 = c.overloadedCount();
                long h0 = heapUsed();
                String outcome, msg = "";
                try
                {
                    c.enqueue(m);
                    outcome = "accepted";
                }
                catch (Message.OversizedMessageException e)
                {
                    outcome = "OversizedMessageException";
                    msg = e.getMessage();
                }
                long dp = c.pendingBytes() - p0, dn = c.pendingCount() - n0, dsub = c.submittedCount() - sub0, dov = c.overloadedCount() - ov0;
                long dh = heapUsed() - h0;
                line("STAGE4 case " + tag + " limit=" + limit + " S=" + names[i] + " size=" + sizes[i] + " payload=" + m.payload.length
                     + " size40=" + s40 + " size50=" + s50 + " linkVersion=" + c.messagingVersion() + " outcome=" + outcome
                     + " dPendingBytes=" + dp + " dPendingCount=" + dn + " dSubmitted=" + dsub + " dOverloaded=" + dov
                     + " pendingBytes=" + c.pendingBytes() + " attempts=" + c.connectionAttempts() + " dHeapUsed=" + dh
                     + (msg.isEmpty() ? "" : " msg=\"" + msg + "\""));
                check(tag + " " + names[i] + " size at current_version", sizes[i], m.serializedSize(current_version));
                check(tag + " " + names[i] + " size40 == size50 (B2h)", s40, s50);
                boolean over = sizes[i] > limit;
                if (over)
                {
                    check(tag + " " + names[i] + " outcome", "OversizedMessageException", outcome);
                    check(tag + " " + names[i] + " message", "Message of size " + sizes[i] + " bytes exceeds allowed maximum of " + limit + " bytes", msg);
                    check(tag + " " + names[i] + " dPendingBytes,dPendingCount,dSubmitted,dOverloaded", "0,0,0,0", dp + "," + dn + "," + dsub + "," + dov);
                }
                else
                {
                    check(tag + " " + names[i] + " outcome", "accepted", outcome);
                    check(tag + " " + names[i] + " dPendingBytes,dPendingCount,dSubmitted,dOverloaded", sizes[i] + ",1,1,0", dp + "," + dn + "," + dsub + "," + dov);
                }
            }
        }
        finally
        {
            // the link is still handshaking with the silent listener, so close() completes only when that attempt
            // ends; it is not waited for (each L has its own link and its own reserves)
            io.netty.util.concurrent.Future<Void> f = c.close(false);
            boolean done = f.await(2L, SECONDS);
            line("STAGE4 info " + tag + " close requested (completed within 2 s: " + done + "); pendingBytes now=" + c.pendingBytes());
        }
    }

    @Test
    public void testEnqueueLimit() throws Exception
    {
        for (int l : LIMITS)
            runLimit("L=" + l, l, l);
        // B2e step 4: the same S values with no effective limit (Integer.MAX_VALUE is not settable)
        for (int l : LIMITS)
            runLimit("control(L=" + l + ")", CONTROL_LIMIT, l);
        Assert.assertEquals("mismatches", 0, mismatches);
    }
}
