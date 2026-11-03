/*
 * Stage-4 unit tier (B2, amendments U1-U4 of 2026-10-27) of
 * native_transport_max_concurrent_connections-channelActive-limit--autonomous.
 * Copied into test/unit/org/apache/cassandra/transport/ of the run clone only for the run (unit-run.sh).
 * Runs L-1, L0, L8, L32 (S written) and S0 (L = 8, nothing written), per-IP limit -1 throughout.
 * Prints one "PROBE <run> L=.. open=.. counter=.. written=.. held=.. capacity=.. closeCounter=.." line per run,
 * then asserts B2f as amended by U3 (computed from N and S; with the frozen N = 64, S = 1,048,576 these are B2f's numbers).
 * N and S default to the frozen values; a shakedown passes -Dprobe.n / -Dprobe.s through -Dtest.jvm.args.
 */
package org.apache.cassandra.transport;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
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

public class ConnectionLimitProbeTest
{
    static final int N = Integer.getInteger("probe.n", 64);
    static final int S = Integer.getInteger("probe.s", 1_048_576);
    static final int BODY_DECLARED = 16_000_000;

    static AtomicLong counter;
    static Method internalBuffer;
    static final List<String> lines = new ArrayList<>();

    static void out(String s)
    {
        System.out.println(s);
        lines.add(s);
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

    static long[] run(String name, long limit, boolean write, PipelineConfigurator pc) throws Exception
    {
        DatabaseDescriptor.setNativeTransportMaxConcurrentConnections(limit);
        DatabaseDescriptor.setNativeTransportMaxConcurrentConnectionsPerIp(-1);
        List<EmbeddedChannel> chs = new ArrayList<>();
        for (int i = 0; i < N; i++)
        {
            EmbeddedChannel ch = new EmbeddedChannel(false, false);
            pc.configureInitialPipeline(ch, null);
            ch.register();
            chs.add(ch);
        }
        for (EmbeddedChannel ch : chs) ch.runPendingTasks();
        int open = 0;
        for (EmbeddedChannel ch : chs) if (ch.isOpen()) open++;
        long cnt = counter.get();
        long held = 0, cap = 0;
        int written = 0;
        for (EmbeddedChannel ch : chs)
        {
            if (!ch.isOpen()) continue;
            if (write)
            {
                ch.writeInbound(envelope());
                written++;
            }
            ChannelHandler h = ch.pipeline().get(InitialConnectionHandler.class);
            ByteBuf ib = (ByteBuf) internalBuffer.invoke(h);
            held += ib.readableBytes();
            cap += ib.capacity();
        }
        for (EmbeddedChannel ch : chs)
        {
            ch.finishAndReleaseAll();
            ch.runPendingTasks();
        }
        long closeCnt = counter.get();
        out(String.format("PROBE %s L=%d open=%d counter=%d written=%d held=%d capacity=%d closeCounter=%d",
                          name, limit, open, cnt, written, held, cap, closeCnt));
        DatabaseDescriptor.setNativeTransportMaxConcurrentConnections(-1);
        return new long[]{ open, cnt, held, cap, closeCnt };
    }

    @Test
    public void probe() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        Field f = PipelineConfigurator.class.getDeclaredField("connectionLimitHandler");
        f.setAccessible(true);
        Object handler = f.get(null);
        Field c = handler.getClass().getDeclaredField("counter");
        c.setAccessible(true);
        counter = (AtomicLong) c.get(handler);
        internalBuffer = ByteToMessageDecoder.class.getDeclaredMethod("internalBuffer");
        internalBuffer.setAccessible(true);
        out(String.format("PROBE init N=%d S=%d maxFrame=%d idleTimeout=%d perIp=%d counter=%d", N, S,
                          DatabaseDescriptor.getNativeTransportMaxFrameSize(), DatabaseDescriptor.nativeTransportIdleTimeout(),
                          DatabaseDescriptor.getNativeTransportMaxConcurrentConnectionsPerIp(), counter.get()));
        PipelineConfigurator pc = new PipelineConfigurator(false, false, false, EncryptionOptions.TlsEncryptionPolicy.UNENCRYPTED);
        long[] m1 = run("L-1", -1, true, pc);
        long[] z0 = run("L0", 0, true, pc);
        long[] l8 = run("L8", 8, true, pc);
        long[] l32 = run("L32", 32, true, pc);
        long[] s0 = run("S0", 8, false, pc);
        out("PROBE end");

        long per = 9L + S;
        // {open, counter, held} expected per run (B2f as amended by U3)
        Object[][] want = {
            { "L-1", m1, (long) N, 0L, N * per },
            { "L0", z0, (long) N, 0L, N * per },
            { "L8", l8, (long) Math.min(N, 8), (long) Math.min(N, 8), Math.min(N, 8) * per },
            { "L32", l32, (long) Math.min(N, 32), (long) Math.min(N, 32), Math.min(N, 32) * per },
            { "S0", s0, (long) Math.min(N, 8), (long) Math.min(N, 8), 0L },
        };
        for (Object[] w : want)
        {
            long[] r = (long[]) w[1];
            Assert.assertEquals(w[0] + " open", (long) (Long) w[2], r[0]);
            Assert.assertEquals(w[0] + " counter", (long) (Long) w[3], r[1]);
            Assert.assertEquals(w[0] + " held", (long) (Long) w[4], r[2]);
            Assert.assertTrue(w[0] + " capacity band", r[3] >= r[2] && r[3] <= 2 * r[2]);
            Assert.assertEquals(w[0] + " closeCounter", 0L, r[4]);
        }
    }
}
