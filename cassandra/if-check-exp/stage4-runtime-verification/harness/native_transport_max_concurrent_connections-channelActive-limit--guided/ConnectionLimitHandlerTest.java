/*
 * Stage-4 harness, unit tier, for native_transport_max_concurrent_connections-channelActive-limit--guided
 * (case 9a Procedure 1; frozen §9 hash 52393486…). Written 2026-10-20 before any reading.
 *
 * Package org.apache.cassandra.transport (ConnectionLimitHandler is package-private); copy into
 * test/unit/org/apache/cassandra/transport/. ConnectionLimitHandler sits in an EmbeddedChannel pipeline ahead of a stub
 * handler that counts the channelActive events it receives. Every channel's remote address is an InetSocketAddress
 * (EmbeddedChannel's own is not), so all come "from one remote address" unless a step says otherwise. After each
 * channel registers, the embedded loop's pending tasks run, as a real event loop would run the close's inactive event.
 *
 *   u1  global limit L in {k-1, k, k+1, k/2, -1} for k = 100 channels (per-IP -1): open channels, downstream
 *       channelActive count and the handler's counter (reflection) all equal min(k, L) (k for -1, which the handler
 *       treats as no limit), refused = k - min(k, L); after closing all channels the counter is 0.
 *  u2  per-IP limit 10 (global -1), 15 channels from each of two addresses: 10 open per address.
 *   u3  the limit is read at channelActive only: 3 channels open under limit 500, the limit set to 2: the 3 stay open,
 *       a 4th is refused.
 *   u4  installation (§4 step 3): PipelineConfigurator.configureInitialPipeline puts "connectionLimitHandler" first in
 *       the pipeline iff one of the two limits is > 0 when the channel is configured.
 *
 * Output: "STAGE4 check <name> expected=<e> actual=<a> ok|MISMATCH" lines to -Dstage4.out; the test fails at the end on
 * any mismatch (all checks run first).
 */
package org.apache.cassandra.transport;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import io.netty.channel.ChannelHandler;
import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.ChannelInboundHandlerAdapter;
import io.netty.channel.DefaultChannelId;
import io.netty.channel.embedded.EmbeddedChannel;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.config.EncryptionOptions;

public class ConnectionLimitHandlerTest
{
    static PrintWriter out;
    static int mismatches = 0;

    @BeforeClass
    public static void setUp() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        out = new PrintWriter(new FileWriter(System.getProperty("stage4.out", "build/stage4-ncc-unit.out")), true);
        out.println("STAGE4 info protocol unit tier, DatabaseDescriptor defaults: global "
                    + DatabaseDescriptor.getNativeTransportMaxConcurrentConnections() + " per-ip "
                    + DatabaseDescriptor.getNativeTransportMaxConcurrentConnectionsPerIp() + " idle timeout "
                    + DatabaseDescriptor.nativeTransportIdleTimeout());
    }

    @AfterClass
    public static void tearDown()
    {
        DatabaseDescriptor.setNativeTransportMaxConcurrentConnections(-1);
        DatabaseDescriptor.setNativeTransportMaxConcurrentConnectionsPerIp(-1);
        if (out != null)
            out.close();
    }

    static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        if (!ok)
            mismatches++;
        out.println("STAGE4 check " + name + " expected=" + expected + " actual=" + actual + (ok ? " ok" : " MISMATCH"));
    }

    /** An EmbeddedChannel whose remote address is an InetSocketAddress. */
    static final class RemoteChannel extends EmbeddedChannel
    {
        static volatile InetSocketAddress next;
        private InetSocketAddress remote;

        RemoteChannel(ChannelHandler... handlers)
        {
            super(DefaultChannelId.newInstance(), false, false, handlers);
        }

        @Override
        protected SocketAddress remoteAddress0()
        {
            if (remote == null)
                remote = next;
            return remote;
        }
    }

    @ChannelHandler.Sharable
    static final class Downstream extends ChannelInboundHandlerAdapter
    {
        final AtomicInteger active = new AtomicInteger();

        @Override
        public void channelActive(ChannelHandlerContext ctx) throws Exception
        {
            active.incrementAndGet();
            super.channelActive(ctx);
        }
    }

    static long counter(ConnectionLimitHandler h) throws Exception
    {
        Field f = ConnectionLimitHandler.class.getDeclaredField("counter");
        f.setAccessible(true);
        return ((AtomicLong) f.get(h)).get();
    }

    static RemoteChannel open(ConnectionLimitHandler h, Downstream d, String ip, int port) throws Exception
    {
        RemoteChannel.next = new InetSocketAddress(java.net.InetAddress.getByName(ip), port);
        RemoteChannel c = new RemoteChannel(h, d);
        c.register();
        c.runPendingTasks();
        return c;
    }

    static int countOpen(List<RemoteChannel> cs)
    {
        int n = 0;
        for (RemoteChannel c : cs)
            if (c.isOpen())
                n++;
        return n;
    }

    static void closeAll(List<RemoteChannel> cs)
    {
        for (RemoteChannel c : cs)
        {
            c.close();
            c.runPendingTasks();
        }
    }

    @Test
    public void connectionLimit() throws Exception
    {
        // u1: global limit around k
        int k = 100;
        for (long limit : new long[]{ k - 1, k, k + 1, k / 2, -1 })
        {
            DatabaseDescriptor.setNativeTransportMaxConcurrentConnections(limit);
            DatabaseDescriptor.setNativeTransportMaxConcurrentConnectionsPerIp(-1);
            ConnectionLimitHandler h = new ConnectionLimitHandler();
            Downstream d = new Downstream();
            List<RemoteChannel> cs = new ArrayList<>();
            for (int i = 0; i < k; i++)
                cs.add(open(h, d, "10.1.1.1", 40000 + i));
            long expectOpen = limit < 0 ? k : Math.min(k, limit);
            check("u1 L=" + limit + " open", expectOpen, countOpen(cs));
            check("u1 L=" + limit + " downstream-active", expectOpen, d.active.get());
            check("u1 L=" + limit + " counter", expectOpen, counter(h));
            check("u1 L=" + limit + " refused", k - expectOpen, k - countOpen(cs));
            // the k-th channel is the boundary: kept iff k <= L
            check("u1 L=" + limit + " last-channel-open", limit < 0 || k <= limit, cs.get(k - 1).isOpen());
            closeAll(cs);
            check("u1 L=" + limit + " counter-after-close", 0, counter(h));
        }

        // u2: per-IP limit
        DatabaseDescriptor.setNativeTransportMaxConcurrentConnections(-1);
        DatabaseDescriptor.setNativeTransportMaxConcurrentConnectionsPerIp(10);
        {
            ConnectionLimitHandler h = new ConnectionLimitHandler();
            Downstream d = new Downstream();
            List<RemoteChannel> a = new ArrayList<>(), b = new ArrayList<>();
            for (int i = 0; i < 15; i++)
            {
                a.add(open(h, d, "10.1.1.2", 41000 + i));
                b.add(open(h, d, "10.1.1.3", 42000 + i));
            }
            check("u2 per-ip=10 open from address A", 10, countOpen(a));
            check("u2 per-ip=10 open from address B", 10, countOpen(b));
            check("u2 per-ip=10 downstream-active", 20, d.active.get());
            closeAll(a);
            closeAll(b);
            check("u2 counter-after-close", 0, counter(h));
        }
        DatabaseDescriptor.setNativeTransportMaxConcurrentConnectionsPerIp(-1);

        // u3: the limit is read at channelActive only
        {
            DatabaseDescriptor.setNativeTransportMaxConcurrentConnections(500);
            ConnectionLimitHandler h = new ConnectionLimitHandler();
            Downstream d = new Downstream();
            List<RemoteChannel> cs = new ArrayList<>();
            for (int i = 0; i < 3; i++)
                cs.add(open(h, d, "10.1.1.4", 43000 + i));
            DatabaseDescriptor.setNativeTransportMaxConcurrentConnections(2);
            check("u3 three channels open under 500 stay open after the limit drops to 2", 3, countOpen(cs));
            RemoteChannel fourth = open(h, d, "10.1.1.4", 43003);
            check("u3 a fourth channel under limit 2 is refused", false, fourth.isOpen());
            check("u3 counter (3 open; the refused one decremented)", 3, counter(h));
            closeAll(cs);
            check("u3 counter-after-close", 0, counter(h));
        }

        // u4: the handler is installed only if a limit is positive when the channel is configured
        PipelineConfigurator pc = new PipelineConfigurator(false, false, false, EncryptionOptions.TlsEncryptionPolicy.UNENCRYPTED);
        long[][] cases = { { -1, -1 }, { 500, -1 }, { -1, 10 }, { 0, 0 } };
        for (long[] lim : cases)
        {
            DatabaseDescriptor.setNativeTransportMaxConcurrentConnections(lim[0]);
            DatabaseDescriptor.setNativeTransportMaxConcurrentConnectionsPerIp(lim[1]);
            RemoteChannel.next = new InetSocketAddress(java.net.InetAddress.getByName("10.1.1.5"), 44000);
            RemoteChannel c = new RemoteChannel();
            c.register();
            pc.configureInitialPipeline(c, null);
            boolean installed = c.pipeline().names().contains("connectionLimitHandler");
            boolean expected = lim[0] > 0 || lim[1] > 0;
            check("u4 global=" + lim[0] + " per-ip=" + lim[1] + " handler installed", expected, installed);
            if (installed)
                check("u4 global=" + lim[0] + " per-ip=" + lim[1] + " handler first", "connectionLimitHandler", c.pipeline().names().get(0));
            out.println("STAGE4 info u4 global=" + lim[0] + " per-ip=" + lim[1] + " pipeline " + c.pipeline().names());
            c.close();
            c.runPendingTasks();
        }
        DatabaseDescriptor.setNativeTransportMaxConcurrentConnections(-1);
        DatabaseDescriptor.setNativeTransportMaxConcurrentConnectionsPerIp(-1);

        out.println("STAGE4 info mismatches=" + mismatches);
        Assert.assertEquals("mismatching checks (see the STAGE4 check lines)", 0, mismatches);
    }
}
