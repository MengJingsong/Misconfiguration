package org.apache.cassandra.transport;

import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;

import org.junit.BeforeClass;
import org.junit.Test;

import io.netty.buffer.ByteBuf;
import io.netty.buffer.Unpooled;
import io.netty.channel.embedded.EmbeddedChannel;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.net.FrameEncoder;
import org.apache.cassandra.net.FrameEncoderCrc;
import org.apache.cassandra.utils.memory.BufferPool;
import org.apache.cassandra.utils.memory.BufferPools;

public class FrameMaxSizeProbeTest
{
    @BeforeClass
    public static void init() { DatabaseDescriptor.daemonInitialization(); }

    @Test
    public void probe()
    {
        System.out.printf("PROBE MAX_SIZE=%d MAX_FRAMED_PAYLOAD_SIZE=%d%n",
                          FrameEncoder.Payload.MAX_SIZE, Flusher.MAX_FRAMED_PAYLOAD_SIZE);
        for (int s : new int[]{ 4 << 20, 8 << 20, 8 << 20 })   // 8 MiB twice: repeatability
            runOnce(s);
        hardCheck(131071);
        hardCheck(131072);
    }

    private static void runOnce(int bodySize)
    {
        BufferPool pool = BufferPools.forNetworking();
        EmbeddedChannel ch = new EmbeddedChannel(FrameEncoderCrc.instance);
        long before = pool.usedSizeInBytes();
        Envelope env = Envelope.create(Message.Type.RESULT, 1, ProtocolVersion.V5,
                                       EnumSet.noneOf(Envelope.Header.Flag.class),
                                       Unpooled.wrappedBuffer(new byte[bodySize]));
        Flusher f = Flusher.immediate(ch.eventLoop());
        f.enqueue(new Flusher.FlushItem.Framed(ch, env, null, FrameEncoderCrc.instance.allocator(),
                                               item -> item.responseEnvelope.release()));
        f.start();
        ch.runPendingTasks();
        List<ByteBuf> frames = new ArrayList<>();
        ByteBuf b;
        while ((b = ch.readOutbound()) != null) frames.add(b);
        long held = pool.usedSizeInBytes() - before;
        int maxWire = 0; long sumWire = 0;
        for (ByteBuf fr : frames) { maxWire = Math.max(maxWire, fr.readableBytes()); sumWire += fr.readableBytes(); }
        frames.forEach(ByteBuf::release);
        ch.finishAndReleaseAll();
        long after = pool.usedSizeInBytes() - before;
        System.out.printf("PROBE body=%d envelope=%d frames=%d maxWire=%d maxData=%d sumWire=%d heldDelta=%d releasedDelta=%d%n",
                          bodySize, bodySize + 9, frames.size(), maxWire, maxWire - 10, sumWire, held, after);
    }

    private static void hardCheck(int dataLen)
    {
        EmbeddedChannel ch = new EmbeddedChannel(FrameEncoderCrc.instance);
        FrameEncoder.Payload p = FrameEncoderCrc.instance.allocator().allocate(true, dataLen);
        p.buffer.position(p.buffer.position() + dataLen);
        p.finish();
        try { ch.writeOutbound(p); System.out.printf("PROBE hardCheck data=%d accepted%n", dataLen); }
        catch (IllegalArgumentException e) { System.out.printf("PROBE hardCheck data=%d rejected: %s%n", dataLen, e.getMessage()); }
        ch.finishAndReleaseAll();
    }
}
