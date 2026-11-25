package org.apache.cassandra.transport;

import java.lang.reflect.Field;
import java.util.*;
import io.netty.buffer.ByteBuf;
import io.netty.channel.embedded.EmbeddedChannel;
import org.apache.cassandra.config.*;
import org.apache.cassandra.net.*;
import org.apache.cassandra.utils.memory.*;

public class FlusherProbe
{
    public static void main(String[] a) throws Exception
    {
        int n = Integer.parseInt(a[0]);                 // response body bytes
        String codec = a.length > 1 ? a[1] : "crc";      // crc | lz4
        int cacheMiB = Integer.getInteger("probe.cache_mib", 512);
        DatabaseDescriptor.clientInitialization(true, () -> {
            Config c = new Config();
            c.networking_cache_size = new DataStorageSpec.IntMebibytesBound(cacheMiB + "MiB");
            return c; });
        FrameEncoder enc;
        if (codec.equals("lz4")) {
            Field f = Class.forName("org.apache.cassandra.net.FrameEncoderLZ4").getField("fastInstance");
            f.setAccessible(true); enc = (FrameEncoder) f.get(null);
        } else enc = FrameEncoderCrc.instance;
        BufferPool pool = BufferPools.forNetworking();
        EmbeddedChannel ch = new EmbeddedChannel(enc);   // nothing reads outbound: a stalled client
        long u0 = pool.usedSizeInBytes(), o0 = pool.overflowMemoryInBytes(), s0 = pool.sizeInBytes();

        ByteBuf body = CBUtil.allocator.directBuffer(n, n);
        byte[] chunk = new byte[65536]; Random r = new Random(42);   // incompressible
        while (body.writableBytes() > 0) { r.nextBytes(chunk); body.writeBytes(chunk, 0, Math.min(chunk.length, body.writableBytes())); }
        EnumSet<Envelope.Header.Flag> none = EnumSet.noneOf(Envelope.Header.Flag.class);
        Envelope resp = Envelope.create(Message.Type.RESULT, 1, ProtocolVersion.V5, none, body);
        Envelope req  = Envelope.create(Message.Type.QUERY, 1, ProtocolVersion.V5, none, CBUtil.allocator.directBuffer(16, 16).writeZero(16));

        Flusher fl = Flusher.immediate(ch.eventLoop());
        fl.enqueue(new Flusher.FlushItem.Framed(ch, resp, req, enc.allocator(),
                   it -> { it.requestEnvelope.release(); it.responseEnvelope.release(); }));
        fl.start();
        ch.runPendingTasks();

        int frames = ch.outboundMessages().size(); long wire = 0; int maxFrame = 0;
        for (Object o : ch.outboundMessages()) { int b = ((ByteBuf) o).readableBytes(); wire += b; maxFrame = Math.max(maxFrame, b); }
        long du = pool.usedSizeInBytes() - u0, dov = pool.overflowMemoryInBytes() - o0, ds = pool.sizeInBytes() - s0;
        System.out.printf("RESULT,K=%d,codec=%s,n=%d,frames=%d,maxFrame=%d,wire=%d,dUsed=%d,dOverflow=%d,dSize=%d,cacheMiB=%d%n",
                          Flusher.MAX_FRAMED_PAYLOAD_SIZE, codec, n, frames, maxFrame, wire, du, dov, ds, cacheMiB);
        ch.finishAndReleaseAll();
        System.out.printf("AFTER_RELEASE,dUsed=%d%n", pool.usedSizeInBytes() - u0);
        System.exit(0);
    }
}
