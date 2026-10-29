/*
 * Stage-4 unit tier for no_constraint-hascomponent-i_nextsize--autonomous (case file B2 as amended 2026-10-29).
 * Package org.apache.cassandra.db. Drives ClusteringPrefix.Deserializer.prepare + compareNextTo on a serialized bound of nextSize
 * components against a probe bound of S components, and reads the calling thread's allocated bytes around compareNextTo only.
 * Observation only: raw rows go to $stage4.out/raw.csv; the only assertion is the instrument known-answer check.
 */
package org.apache.cassandra.db;

import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.Arrays;

import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.db.rows.UnfilteredSerializer;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.io.util.DataInputBuffer;
import org.apache.cassandra.io.util.DataOutputBuffer;
import org.apache.cassandra.net.MessagingService;
import org.apache.cassandra.schema.TableMetadata;

public class ClusteringHasComponentTest
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static final int WARM = 3, REPS = 7, COLS = 16;
    static PrintWriter raw;
    static TableMetadata md;
    static ClusteringComparator comparator;
    static SerializationHeader header;
    static Field deserializedSizeF;
    static volatile Object sink;

    @BeforeClass
    public static void init() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        raw = new PrintWriter(new java.io.FileWriter(System.getProperty("stage4.out", ".") + "/raw.csv", true), true);
        TableMetadata.Builder b = TableMetadata.builder("ks", "t").addPartitionKeyColumn("pk", Int32Type.instance);
        for (int i = 0; i < COLS; i++)
            b.addClusteringColumn("c" + i, BytesType.instance);
        md = b.addRegularColumn("v", BytesType.instance).partitioner(Murmur3Partitioner.instance).build();
        comparator = md.comparator;
        header = SerializationHeader.makeWithoutStats(md);
        deserializedSizeF = ClusteringPrefix.Deserializer.class.getDeclaredField("deserializedSize");
        deserializedSizeF.setAccessible(true);
    }

    static long now() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    static ByteBuffer[] comps(int count, int size)
    {
        ByteBuffer[] v = new ByteBuffer[count];
        for (int j = 0; j < count; j++)
        {
            byte[] x = new byte[size];
            Arrays.fill(x, (byte) j);
            v[j] = ByteBuffer.wrap(x);
        }
        return v;
    }

    /** returns the thrown exception class name or "-". */
    static void point(String block, String label, int nextSize, int s, int compSize) throws Exception
    {
        ClusteringBound<ByteBuffer> stored = BufferClusteringBound.create(ClusteringPrefix.Kind.INCL_START_BOUND, comps(nextSize, compSize));
        ClusteringBound<ByteBuffer> probe = BufferClusteringBound.create(ClusteringPrefix.Kind.INCL_START_BOUND, comps(s, compSize));
        DataOutputBuffer out = new DataOutputBuffer();
        ClusteringBoundOrBoundary.serializer.serialize(stored, out, MessagingService.current_version, comparator.subtypes());
        byte[] bytes = out.toByteArray();
        for (int rep = -WARM; rep < REPS; rep++)
        {
            ClusteringPrefix.Deserializer d = new ClusteringPrefix.Deserializer(comparator, new DataInputBuffer(bytes), header);
            d.prepare(0x02, 0);
            String thrown = "-";
            int cmp = 0;
            long a0 = now();
            try { cmp = d.compareNextTo(probe); }
            catch (Throwable t) { thrown = t.getClass().getSimpleName(); }
            long a1 = now();
            sink = d;
            if (rep < 0)
                continue;
            raw.println(String.join(",", block, label, "" + nextSize, "" + s, "" + compSize, "" + rep, "" + (a1 - a0),
                                    "" + deserializedSizeF.getInt(d), "" + cmp, thrown, "" + bytes.length, "" + DatabaseDescriptor.getMaxValueSize()));
        }
    }

    @Test
    public void run() throws Exception
    {
        raw.println("block,label,nextSize,S,compSize,rep,bytes,deserializedSize,cmp,thrown,streamLen,maxValueSize");
        int mv0 = DatabaseDescriptor.getMaxValueSize();
        System.out.println("STAGE4 info comparator_size=" + comparator.size() + " max_value_size=" + mv0 + " heap_max=" + Runtime.getRuntime().maxMemory()
                           + " agent=" + (System.getProperty("stage4.trace") != null ? "byteman" : "none"));
        Assert.assertEquals(org.apache.cassandra.db.rows.Unfiltered.Kind.RANGE_TOMBSTONE_MARKER, UnfilteredSerializer.kind(0x02));
        long e0 = now(); long e1 = now();
        long k0 = now(); byte[] big = new byte[8 << 20]; long k1 = now(); sink = big;
        System.out.println("STAGE4 check empty-window-bytes=" + (e1 - e0));
        boolean ok = (k1 - k0) >= (8 << 20) && (k1 - k0) <= (8 << 20) + 65536;
        System.out.println("STAGE4 check alloc-known-answer expected=[8388608,8454144] actual=" + (k1 - k0) + (ok ? " ok" : " MISMATCH"));
        Assert.assertTrue("known-answer", ok);
        if (System.getProperty("stage4.checkonly") != null)
            return;
        point("noise1", "N", 4, 4, 1024);
        int[][] sweep = { {1,1}, {2,1}, {2,2}, {2,4}, {4,2}, {4,4}, {4,8}, {8,8}, {8,16}, {16,16} };
        for (int[] p : sweep)
            point("main", "S", p[0], p[1], 1024);
        point("noise2", "N", 4, 4, 1024);
        point("control", "A-64k", 4, 4, 65536);
        DatabaseDescriptor.setMaxValueSize(512);
        try { point("control", "B-maxvalue512", 4, 4, 1024); }
        finally { DatabaseDescriptor.setMaxValueSize(mv0); }
        System.out.println("STAGE4 done");
    }
}
