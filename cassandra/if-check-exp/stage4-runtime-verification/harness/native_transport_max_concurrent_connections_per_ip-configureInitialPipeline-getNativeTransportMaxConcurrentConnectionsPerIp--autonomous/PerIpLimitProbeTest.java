/*
 * Stage-4 unit tier (B2, amendments U1-U4 of 2026-10-27) of
 * native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous.
 * Prints READBACK/CH/PROBE/CLOSED/END lines only; asserts nothing (rows are matched afterwards).
 * Shakedown overrides (via -Dtest.jvm.args): -Dntpip.values=a,b
 */
package org.apache.cassandra.transport;

import java.lang.reflect.Field;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.BeforeClass;
import org.junit.Test;

import io.netty.channel.Channel;
import io.netty.channel.ChannelInitializer;
import io.netty.channel.embedded.EmbeddedChannel;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.config.EncryptionOptions;

public class PerIpLimitProbeTest
{
    @BeforeClass
    public static void setUp()
    {
        DatabaseDescriptor.daemonInitialization();
    }

    @SuppressWarnings("unchecked")
    private static Map<InetAddress, AtomicLong> map() throws Exception
    {
        Field hf = PipelineConfigurator.class.getDeclaredField("connectionLimitHandler");
        hf.setAccessible(true);
        Object handler = hf.get(null);
        Field mf = handler.getClass().getDeclaredField("connectionsPerClient");
        mf.setAccessible(true);
        return (Map<InetAddress, AtomicLong>) mf.get(handler);
    }

    private static long count(InetAddress a) throws Exception
    {
        AtomicLong v = map().get(a);
        return v == null ? 0 : v.get();
    }

    @Test
    public void probe() throws Exception
    {
        String vs = System.getProperty("ntpip.values", "-1,0,3,5");
        System.out.println("START,values=" + vs);
        final PipelineConfigurator pc = new PipelineConfigurator(false, false, false, EncryptionOptions.TlsEncryptionPolicy.UNENCRYPTED);
        final InetAddress ip1 = InetAddress.getByName("10.0.0.1");
        final InetAddress ip2 = InetAddress.getByName("10.0.0.2");
        for (String v : vs.split(","))
        {
            long limit = Long.parseLong(v.trim());
            DatabaseDescriptor.setNativeTransportMaxConcurrentConnections(-1);
            DatabaseDescriptor.setNativeTransportMaxConcurrentConnectionsPerIp(limit);
            System.out.println("READBACK," + DatabaseDescriptor.getNativeTransportMaxConcurrentConnections() + ","
                               + DatabaseDescriptor.getNativeTransportMaxConcurrentConnectionsPerIp());
            List<EmbeddedChannel> chans = new ArrayList<>();
            int open1 = 0, open2 = 0;
            for (int i = 1; i <= 8; i++)
            {
                final InetAddress ipa = i <= 6 ? ip1 : ip2;
                final InetSocketAddress ra = new InetSocketAddress(ipa, 40000 + i);
                EmbeddedChannel ch = new EmbeddedChannel(false, false)
                {
                    @Override
                    protected SocketAddress remoteAddress0() { return ra; }
                };
                final boolean[] seen = new boolean[1];
                ch.pipeline().addLast(new ChannelInitializer<Channel>()
                {
                    protected void initChannel(Channel c)
                    {
                        pc.configureInitialPipeline(c, null);
                        // read here: a refused channel's pipeline is emptied when it is closed and deregistered
                        seen[0] = c.pipeline().get("connectionLimitHandler") != null;
                    }
                });
                ch.register();
                ch.runPendingTasks();
                boolean isOpen = ch.isOpen();
                if (isOpen) { if (ipa == ip1) open1++; else open2++; }
                System.out.println("CH," + limit + "," + i + "," + ipa.getHostAddress() + "," + isOpen + "," + seen[0] + "," + count(ipa));
                chans.add(ch);
            }
            System.out.println("PROBE," + limit + ",10.0.0.1," + open1 + "," + count(ip1));
            System.out.println("PROBE," + limit + ",10.0.0.2," + open2 + "," + count(ip2));
            for (EmbeddedChannel ch : chans)
            {
                ch.close();
                ch.runPendingTasks();
            }
            System.out.println("CLOSED," + limit + "," + map().size());
        }
        System.out.println("END");
    }
}
