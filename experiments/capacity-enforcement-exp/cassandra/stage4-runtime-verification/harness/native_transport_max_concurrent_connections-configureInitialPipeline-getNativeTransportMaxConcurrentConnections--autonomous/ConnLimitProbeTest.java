/*
 * Stage-4 unit tier (B2, amendments U1-U4 of 2026-10-27) of
 * native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous.
 * Prints CH/PROBE/CLOSED/READBACK lines only; asserts nothing (rows are matched afterwards).
 * Values and channel count can be overridden for the shakedown with -Dntcc.values=a,b -Dntcc.m=n (passed via -Dtest.jvm.args).
 */
package org.apache.cassandra.transport;

import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;

import org.junit.BeforeClass;
import org.junit.Test;

import io.netty.channel.Channel;
import io.netty.channel.ChannelInitializer;
import io.netty.channel.embedded.EmbeddedChannel;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.config.EncryptionOptions;

public class ConnLimitProbeTest
{
    @BeforeClass
    public static void setUp()
    {
        DatabaseDescriptor.daemonInitialization();
    }

    private static long counter() throws Exception
    {
        Field hf = PipelineConfigurator.class.getDeclaredField("connectionLimitHandler");
        hf.setAccessible(true);
        Object handler = hf.get(null);
        Field cf = handler.getClass().getDeclaredField("counter");
        cf.setAccessible(true);
        return ((java.util.concurrent.atomic.AtomicLong) cf.get(handler)).get();
    }

    @Test
    public void probe() throws Exception
    {
        String vs = System.getProperty("ntcc.values", "-1,0,5,20");
        int m = Integer.getInteger("ntcc.m", 10);
        System.out.println("START,values=" + vs + ",m=" + m);
        final PipelineConfigurator pc = new PipelineConfigurator(false, false, false, EncryptionOptions.TlsEncryptionPolicy.UNENCRYPTED);
        for (String v : vs.split(","))
        {
            long limit = Long.parseLong(v.trim());
            DatabaseDescriptor.setNativeTransportMaxConcurrentConnectionsPerIp(-1);
            DatabaseDescriptor.setNativeTransportMaxConcurrentConnections(limit);
            System.out.println("READBACK," + DatabaseDescriptor.getNativeTransportMaxConcurrentConnections() + ","
                               + DatabaseDescriptor.getNativeTransportMaxConcurrentConnectionsPerIp());
            List<EmbeddedChannel> chans = new ArrayList<>();
            int open = 0, present = 0;
            for (int i = 1; i <= m; i++)
            {
                EmbeddedChannel ch = new EmbeddedChannel(false, false);
                final boolean[] seen = new boolean[1];
                ch.pipeline().addLast(new ChannelInitializer<Channel>()
                {
                    protected void initChannel(Channel c)
                    {
                        pc.configureInitialPipeline(c, null);
                        // presence is read here: a refused channel's pipeline is emptied when it is closed and deregistered
                        seen[0] = c.pipeline().get("connectionLimitHandler") != null;
                    }
                });
                ch.register();
                ch.runPendingTasks();
                boolean isOpen = ch.isOpen();
                boolean hp = seen[0];
                if (isOpen) open++;
                if (hp) present++;
                System.out.println("CH," + limit + "," + i + "," + isOpen + "," + hp + "," + counter());
                chans.add(ch);
            }
            System.out.println("PROBE," + limit + "," + open + "," + counter() + "," + present);
            for (EmbeddedChannel ch : chans)
            {
                ch.close();
                ch.runPendingTasks();
            }
            System.out.println("CLOSED," + limit + "," + counter());
        }
        System.out.println("END");
    }
}
