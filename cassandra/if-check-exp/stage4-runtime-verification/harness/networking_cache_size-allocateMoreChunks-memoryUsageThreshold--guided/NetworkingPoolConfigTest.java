/*
 * Stage 4, unit tier U4 of networking_cache_size-allocateMoreChunks-memoryUsageThreshold (case 9e). Not upstream.
 * Copy into test/unit/org/apache/cassandra/net/ of a clone at cassandra-5.0.9 and run in its own JVM (BufferPools is static):
 *   ant testsome -Dtest.name=org.apache.cassandra.net.NetworkingPoolConfigTest -Dtest.jvm.args=-Dstage4.out=<file>
 * The real networking instance through the config path: raw networking_cache_size = 16 MiB before BufferPools loads (as upstream
 * BufferPoolAllocatorTest), then CRC frame payloads of Flusher.MAX_FRAMED_PAYLOAD_SIZE from FrameEncoderCrc's allocator, held:
 * payloads 1-128 pooled (capacity 131,072), payload 129 overflow (capacity 131,070); filled as Flusher fills them, finish(),
 * release(): OverflowSize ends at -6 (one overflowed full frame), pooled stays 16 MiB.
 */
package org.apache.cassandra.net;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.utils.memory.BufferPool;
import org.apache.cassandra.utils.memory.BufferPools;

import static org.junit.Assert.assertEquals;

public class NetworkingPoolConfigTest
{
    static final long MIB = 1024L * 1024L;
    static PrintWriter out;
    int mismatches = 0;

    @BeforeClass
    public static void beforeClass()
    {
        DatabaseDescriptor.clientInitialization();
        DatabaseDescriptor.getRawConfig().networking_cache_size = new DataStorageSpec.IntMebibytesBound(16);
    }

    static synchronized void line(String s)
    {
        System.out.println(s);
        try
        {
            if (out == null && System.getProperty("stage4.out") != null)
                out = new PrintWriter(new FileWriter(System.getProperty("stage4.out"), true), true);
        }
        catch (IOException e)
        {
            throw new RuntimeException(e);
        }
        if (out != null)
            out.println(s);
    }

    void check(String name, long expected, long got)
    {
        boolean ok = expected == got;
        if (!ok)
            mismatches++;
        line("STAGE4 check U4 " + name + " expected=" + expected + " got=" + got + (ok ? " OK" : " MISMATCH"));
    }

    static long pooled(BufferPool p)
    {
        return p.sizeInBytes() - p.overflowMemoryInBytes();
    }

    /** As Flusher.flushLargeMessage(): limit to MAX_FRAMED_PAYLOAD_SIZE, write the body up to it. */
    static void fill(FrameEncoder.Payload payload, int maxFramed)
    {
        payload.buffer.limit(maxFramed);
        while (payload.buffer.hasRemaining())
            payload.buffer.put((byte) 7);
    }

    @Test
    public void u4_realInstance() throws Exception
    {
        Field f = Class.forName("org.apache.cassandra.transport.Flusher").getDeclaredField("MAX_FRAMED_PAYLOAD_SIZE");
        f.setAccessible(true);
        int maxFramed = f.getInt(null);
        BufferPool net = BufferPools.forNetworking();
        line("STAGE4 info U4 MAX_FRAMED_PAYLOAD_SIZE " + maxFramed + "; networking threshold " + net.memoryUsageThreshold());
        check("networking memoryUsageThreshold = 16 MiB", 16 * MIB, net.memoryUsageThreshold());
        check("MAX_FRAMED_PAYLOAD_SIZE = 131,060", 131060, maxFramed);
        List<FrameEncoder.Payload> held = new ArrayList<>();
        int wrongPooled = 0;
        for (int i = 1; i <= 128; i++)
        {
            FrameEncoder.Payload p = FrameEncoderCrc.instance.allocator().allocate(false, maxFramed);
            if (p.buffer.capacity() != 131072)
                wrongPooled++;
            held.add(p);
        }
        line("STAGE4 info U4 after 128 payloads: size " + net.sizeInBytes() + " overflow " + net.overflowMemoryInBytes() + " pooled " + pooled(net));
        check("payloads 1-128 have capacity 131,072", 0, wrongPooled);
        check("pooled reaches 16 MiB", 16 * MIB, pooled(net));
        check("overflow 0 after 128", 0, net.overflowMemoryInBytes());
        FrameEncoder.Payload p129 = FrameEncoderCrc.instance.allocator().allocate(false, maxFramed);
        held.add(p129);
        check("payload 129 capacity 131,070", 131070, p129.buffer.capacity());
        check("OverflowSize 131,070 after 129", 131070, net.overflowMemoryInBytes());
        for (FrameEncoder.Payload p : held)
        {
            fill(p, maxFramed);
            p.finish();
            p.release();
        }
        line("STAGE4 info U4 after finish and release: size " + net.sizeInBytes() + " overflow " + net.overflowMemoryInBytes() + " pooled " + pooled(net)
             + " used " + net.usedSizeInBytes());
        check("OverflowSize -6 (one overflowed full frame)", -6, net.overflowMemoryInBytes());
        check("pooled stays 16 MiB", 16 * MIB, pooled(net));
        line("STAGE4 info u4 done, mismatches " + mismatches);
        assertEquals(0, mismatches);
    }
}
