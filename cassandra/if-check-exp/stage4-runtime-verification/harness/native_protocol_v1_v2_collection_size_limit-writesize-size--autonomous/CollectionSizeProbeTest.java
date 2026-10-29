/*
 * Stage-4 unit probe for native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous (B2).
 * Copied by unit-run.sh into the run copy's test/unit/org/apache/cassandra/cql3/functions/types/. Output: "STAGE4 ..." lines to -Dstage4.out.
 * Cells: TypeCodec.list(TypeCodec.blob()).serialize(list, V2|V3|V4) for N in {65535, 65536, 200000}, payload S in {1, 100}, 3 repetitions.
 */
package org.apache.cassandra.cql3.functions.types;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

import org.junit.AfterClass;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.transport.ProtocolVersion;

public class CollectionSizeProbeTest
{
    static PrintWriter out;
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

    @BeforeClass
    public static void setup() throws Exception
    {
        out = new PrintWriter(new FileWriter(System.getProperty("stage4.out", "/tmp/stage4-collsize.out")), true);
        out.println("STAGE4 info java=" + System.getProperty("java.version") + " maxHeap=" + Runtime.getRuntime().maxMemory());
    }

    @AfterClass
    public static void done() { out.println("STAGE4 info done"); out.close(); }

    static long alloc() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    static long heapUsed()
    {
        System.gc(); System.gc();
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    static long expectedLen(ProtocolVersion v, long n, int s)
    {
        return v == ProtocolVersion.V2 ? 2 + n * (2 + s) : 4 + n * (4 + s);
    }

    @Test
    public void cells() throws Exception
    {
        TypeCodec<List<ByteBuffer>> codec = TypeCodec.list(TypeCodec.blob());
        ProtocolVersion[] vs = { ProtocolVersion.V2, ProtocolVersion.V3, ProtocolVersion.V4 };
        int[] ns = { 65535, 65536, 200000 };
        int[] ss = { 1, 100 };
        // warm-up (not recorded)
        List<ByteBuffer> w = new ArrayList<>(); for (int i = 0; i < 1000; i++) w.add(ByteBuffer.allocate(1));
        for (ProtocolVersion v : vs) codec.serialize(w, v);
        for (int s : ss)
        {
            ByteBuffer elt = ByteBuffer.allocate(s);
            for (int n : ns)
            {
                List<ByteBuffer> list = new ArrayList<>(n);
                for (int i = 0; i < n; i++) list.add(elt);
                for (ProtocolVersion v : vs)
                    for (int rep = 1; rep <= 3; rep++)
                    {
                        long h0 = heapUsed();
                        long a0 = alloc();
                        String outcome; long len = -1; long count = -1; String msg = "-";
                        ByteBuffer res = null;
                        try
                        {
                            res = codec.serialize(list, v);
                            long a1 = alloc();
                            len = res.remaining();
                            count = v == ProtocolVersion.V2 ? (res.getShort(0) & 0xFFFF) : res.getInt(0);
                            outcome = "ok";
                            out.println("STAGE4 cell ver=" + v + " N=" + n + " S=" + s + " rep=" + rep + " alloc=" + (a1 - a0) + " outcome=" + outcome
                                        + " len=" + len + " expectedLen=" + expectedLen(v, n, s) + " count=" + count + " heapDelta=" + (heapUsed() - h0) + " msg=-");
                        }
                        catch (IllegalArgumentException e)
                        {
                            long a1 = alloc();
                            outcome = "IllegalArgumentException"; msg = e.getMessage().replace(' ', '_');
                            out.println("STAGE4 cell ver=" + v + " N=" + n + " S=" + s + " rep=" + rep + " alloc=" + (a1 - a0) + " outcome=" + outcome
                                        + " len=-1 expectedLen=" + expectedLen(v, n, s) + " count=-1 heapDelta=0 msg=" + msg);
                        }
                        res = null;
                    }
            }
        }
    }
}
