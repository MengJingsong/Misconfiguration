/*
 * Stage-4 unit probe for native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous (B2).
 * Copied by unit-run.sh into the run copy's test/unit/org/apache/cassandra/cql3/functions/types/. Output: "STAGE4 ..." lines to -Dstage4.out.
 * Cells: CodecUtils.pack(ByteBuffer[N] of S bytes, N, V2|V3); null element; payload-growth control.
 */
package org.apache.cassandra.cql3.functions.types;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;

import org.junit.AfterClass;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.transport.ProtocolVersion;

public class ElementSizeProbeTest
{
    static PrintWriter out;
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

    @BeforeClass
    public static void setup() throws Exception
    {
        out = new PrintWriter(new FileWriter(System.getProperty("stage4.out", "/tmp/stage4-elemsize.out")), true);
        out.println("STAGE4 info java=" + System.getProperty("java.version") + " maxHeap=" + Runtime.getRuntime().maxMemory());
    }

    @AfterClass
    public static void done() { out.println("STAGE4 info done"); out.close(); }

    static long alloc() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    static long expectedLen(ProtocolVersion v, long n, long s)
    {
        return v == ProtocolVersion.V2 ? 2 + n * (2 + s) : 4 + n * (4 + s);
    }

    void cell(String tag, ProtocolVersion v, int n, int s, int rep)
    {
        ByteBuffer elt = ByteBuffer.allocate(s);
        ByteBuffer[] bufs = new ByteBuffer[n];
        for (int i = 0; i < n; i++) bufs[i] = elt;
        long a0 = alloc();
        try
        {
            ByteBuffer r = CodecUtils.pack(bufs, n, v);
            long a1 = alloc();
            out.println("STAGE4 cell tag=" + tag + " ver=" + v + " N=" + n + " S=" + s + " rep=" + rep + " alloc=" + (a1 - a0) + " outcome=ok len=" + r.remaining()
                        + " expectedLen=" + expectedLen(v, n, s) + " msg=-");
        }
        catch (RuntimeException e)
        {
            long a1 = alloc();
            out.println("STAGE4 cell tag=" + tag + " ver=" + v + " N=" + n + " S=" + s + " rep=" + rep + " alloc=" + (a1 - a0) + " outcome=" + e.getClass().getSimpleName()
                        + " len=-1 expectedLen=" + expectedLen(v, n, s) + " msg=" + String.valueOf(e.getMessage()).replace(' ', '_'));
        }
    }

    @Test
    public void cells() throws Exception
    {
        for (ProtocolVersion v : new ProtocolVersion[]{ ProtocolVersion.V2, ProtocolVersion.V3 }) // warm-up
            CodecUtils.pack(new ByteBuffer[]{ ByteBuffer.allocate(10) }, 1, v);
        for (int rep = 1; rep <= 3; rep++)
            for (ProtocolVersion v : new ProtocolVersion[]{ ProtocolVersion.V2, ProtocolVersion.V3, ProtocolVersion.V4 })
            {
                cell("size", v, 1, 65535, rep);
                cell("size", v, 1, 65536, rep);
                cell("size", v, 1, 8 * 1024 * 1024, rep);
                cell("many", v, 100, 65535, rep);
                for (int n : new int[]{ 1, 2, 10, 100, 1000 })
                    cell("ctl", v, n, 65535, rep);
            }
        // null element
        for (ProtocolVersion v : new ProtocolVersion[]{ ProtocolVersion.V2, ProtocolVersion.V3 })
        {
            try
            {
                ByteBuffer r = CodecUtils.pack(new ByteBuffer[]{ null }, 1, v);
                out.println("STAGE4 null ver=" + v + " outcome=ok len=" + r.remaining());
            }
            catch (RuntimeException e)
            {
                out.println("STAGE4 null ver=" + v + " outcome=" + e.getClass().getSimpleName());
            }
        }
    }
}
