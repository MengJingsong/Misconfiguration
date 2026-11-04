/*
 * Stage-4 unit tier (B2, amendments U1-U4 of 2026-10-27) of
 * native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous.
 * Copied into test/unit/org/apache/cassandra/transport/ of the run clone only for the run.
 * Runbook fix D1 (2026-10-27): the "before" values equal "after" (EmbeddedChannel runs pending tasks inside register()).
 * Prints one "PROBE <run> <step> k=v ..." line per step; asserts the U3 table only after every run has printed.
 */
package org.apache.cassandra.transport;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.Assert;
import org.junit.Test;

import io.netty.buffer.ByteBuf;
import io.netty.buffer.Unpooled;
import io.netty.channel.ChannelHandler;
import io.netty.channel.embedded.EmbeddedChannel;
import io.netty.handler.codec.ByteToMessageDecoder;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.config.EncryptionOptions;

public class ConnectionLimitPerIpProbeTest
{
    static final int S = 1_048_576;
    static final int BODY_DECLARED = 16_000_000;

    static class IpChannel extends EmbeddedChannel
    {
        private final InetSocketAddress r;
        IpChannel(InetSocketAddress r) { super(false, false); this.r = r; }
        @Override protected SocketAddress remoteAddress0() { return r; }
    }

    static Object handler;
    static ConcurrentMap<InetAddress, AtomicLong> map;
    static AtomicLong counter;
    static Method internalBuffer;
    static final List<String> lines = new ArrayList<>();

    static void out(String s)
    {
        System.out.println(s);
        lines.add(s);
    }

    @SuppressWarnings("unchecked")
    static void reflect() throws Exception
    {
        Field f = PipelineConfigurator.class.getDeclaredField("connectionLimitHandler");
        f.setAccessible(true);
        handler = f.get(null);
        Field m = handler.getClass().getDeclaredField("connectionsPerClient");
        m.setAccessible(true);
        map = (ConcurrentMap<InetAddress, AtomicLong>) m.get(handler);
        Field c = handler.getClass().getDeclaredField("counter");
        c.setAccessible(true);
        counter = (AtomicLong) c.get(handler);
        internalBuffer = ByteToMessageDecoder.class.getDeclaredMethod("internalBuffer");
        internalBuffer.setAccessible(true);
    }

    static String mapString()
    {
        TreeMap<String, Long> t = new TreeMap<>();
        for (Map.Entry<InetAddress, AtomicLong> e : map.entrySet())
            t.put(e.getKey().getHostAddress(), e.getValue().get());
        StringBuilder sb = new StringBuilder("{");
        for (Map.Entry<String, Long> e : t.entrySet())
            sb.append(sb.length() > 1 ? "," : "").append(e.getKey()).append('=').append(e.getValue());
        return sb.append('}').toString();
    }

    static String openPerIp(List<IpChannel> chs)
    {
        TreeMap<String, Integer> t = new TreeMap<>();
        for (IpChannel ch : chs)
        {
            String ip = ((InetSocketAddress) ch.remoteAddress()).getAddress().getHostAddress();
            t.merge(ip, ch.isOpen() ? 1 : 0, Integer::sum);
        }
        StringBuilder sb = new StringBuilder("{");
        for (Map.Entry<String, Integer> e : t.entrySet())
            sb.append(sb.length() > 1 ? "," : "").append(e.getKey()).append('=').append(e.getValue());
        return sb.append('}').toString();
    }

    static int openTotal(List<IpChannel> chs)
    {
        int n = 0;
        for (IpChannel ch : chs) if (ch.isOpen()) n++;
        return n;
    }

    static ByteBuf envelope()
    {
        ByteBuf b = Unpooled.buffer(9 + S, 9 + S);
        b.writeByte(0x04);           // v4, request direction
        b.writeByte(0x00);           // flags
        b.writeShort(0);             // stream id
        b.writeByte(0x01);           // opcode STARTUP
        b.writeInt(BODY_DECLARED);   // body length 16,000,000
        b.writeZero(S);
        return b;
    }

    static void run(String name, long global, long perIp, int ips, int perIpChannels, boolean oneIp, PipelineConfigurator pc) throws Exception
    {
        DatabaseDescriptor.setNativeTransportMaxConcurrentConnections(global);
        DatabaseDescriptor.setNativeTransportMaxConcurrentConnectionsPerIp(perIp);
        out(String.format("PROBE %s pre global=%d perIp=%d mapSize=%d counter=%d", name,
                          DatabaseDescriptor.getNativeTransportMaxConcurrentConnections(),
                          DatabaseDescriptor.getNativeTransportMaxConcurrentConnectionsPerIp(), map.size(), counter.get()));
        List<IpChannel> chs = new ArrayList<>();
        int idx = 0;
        for (int i = 1; i <= ips; i++)
        {
            for (int j = 0; j < perIpChannels; j++)
            {
                InetAddress a = InetAddress.getByName(oneIp ? "127.0.0.1" : "127.0.0." + i);
                IpChannel ch = new IpChannel(new InetSocketAddress(a, 10000 + idx++));
                pc.configureInitialPipeline(ch, null);
                ch.register();
                chs.add(ch);
            }
        }
        out(String.format("PROBE %s before channels=%d openTotal=%d openPerIp=%s map=%s mapSize=%d counter=%d handler=%b", name, chs.size(),
                          openTotal(chs), openPerIp(chs), mapString(), map.size(), counter.get(), chs.get(0).pipeline().get("connectionLimitHandler") != null));
        for (IpChannel ch : chs) ch.runPendingTasks();
        out(String.format("PROBE %s after openTotal=%d openPerIp=%s map=%s mapSize=%d counter=%d", name,
                          openTotal(chs), openPerIp(chs), mapString(), map.size(), counter.get()));
        long held = 0, cap = 0;
        int written = 0;
        for (IpChannel ch : chs)
        {
            if (!ch.isOpen()) continue;
            ch.writeInbound(envelope());
            written++;
            ChannelHandler h = ch.pipeline().get("initialHandler");
            ByteBuf ib = (ByteBuf) internalBuffer.invoke(h);
            held += ib.readableBytes();
            cap += ib.capacity();
        }
        out(String.format("PROBE %s held written=%d held=%d capacity=%d inbound=%d", name, written, held, cap,
                          chs.stream().mapToInt(c -> c.inboundMessages().size()).sum()));
        for (IpChannel ch : chs)
        {
            ch.finishAndReleaseAll();
            ch.runPendingTasks();
        }
        out(String.format("PROBE %s close openTotal=%d mapSize=%d map=%s counter=%d", name, openTotal(chs), map.size(), mapString(), counter.get()));
        DatabaseDescriptor.setNativeTransportMaxConcurrentConnections(-1);
        DatabaseDescriptor.setNativeTransportMaxConcurrentConnectionsPerIp(-1);
    }

    @Test
    public void probe() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        reflect();
        out(String.format("PROBE init maxFrame=%d allowOlder=%b idleTimeout=%d", DatabaseDescriptor.getNativeTransportMaxFrameSize(),
                          DatabaseDescriptor.getNativeTransportAllowOlderProtocols(), DatabaseDescriptor.nativeTransportIdleTimeout()));
        PipelineConfigurator pc = new PipelineConfigurator(false, false, false, EncryptionOptions.TlsEncryptionPolicy.UNENCRYPTED);
        run("P-1", -1, -1, 8, 8, false, pc);
        run("P2", -1, 2, 8, 8, false, pc);
        run("P4", -1, 4, 8, 8, false, pc);
        run("ONEIP", -1, 4, 1, 64, true, pc);
        run("EDGE", 0, 4, 1, 8, true, pc);
        out("PROBE end");

        // U3 table, asserted only after every line is printed
        String[][] want = {
            {"P-1 before", "openTotal=64 ", "map={} ", "counter=0 "},
            {"P-1 after", "openTotal=64 ", "map={} ", "counter=0"},
            {"P-1 held", "held=67109440 "},
            {"P2 before", "openTotal=16 ", "counter=16 "},
            {"P2 after", "openTotal=16 ", "counter=16"},
            {"P2 held", "held=16777360 "},
            {"P4 before", "openTotal=32 ", "counter=32 "},
            {"P4 after", "openTotal=32 ", "counter=32"},
            {"P4 held", "held=33554720 "},
            {"ONEIP before", "openTotal=4 ", "map={127.0.0.1=4} ", "counter=4 "},
            {"ONEIP after", "openTotal=4 ", "map={127.0.0.1=4} ", "counter=4"},
            {"ONEIP held", "held=4194340 "},
            {"EDGE before", "openTotal=0 ", "map={} ", "counter=0 "},
            {"EDGE after", "openTotal=0 ", "map={} ", "counter=0"},
            {"EDGE held", "held=0 "},
        };
        for (String[] w : want)
        {
            String l = lines.stream().filter(x -> x.startsWith("PROBE " + w[0] + " ")).findFirst().orElse("");
            for (int i = 1; i < w.length; i++)
                Assert.assertTrue(w[0] + " expects " + w[i] + " in [" + l + "]", (l + " ").contains(w[i]));
        }
        for (String r : new String[]{"P-1", "P2", "P4", "ONEIP", "EDGE"})
        {
            String l = lines.stream().filter(x -> x.startsWith("PROBE " + r + " close ")).findFirst().orElse("");
            Assert.assertTrue(r + " close " + l, l.contains("mapSize=0 ") && l.endsWith("counter=0"));
        }
        for (String r : new String[]{"P2", "P4"})
        {
            String b = lines.stream().filter(x -> x.startsWith("PROBE " + r + " before ")).findFirst().orElse("");
            String a = lines.stream().filter(x -> x.startsWith("PROBE " + r + " after ")).findFirst().orElse("");
            String lim = r.substring(1);
            for (int i = 1; i <= 8; i++)
            {
                Assert.assertTrue(r + " before ip " + i, b.contains("map={") && b.substring(b.indexOf("map={")).contains("127.0.0." + i + "=" + lim));
                Assert.assertTrue(r + " after ip " + i, a.contains("127.0.0." + i + "=" + lim));
            }
        }
    }
}
