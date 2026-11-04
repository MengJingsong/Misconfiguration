/*
 * Stage-4 unit tier for none-addall-size--autonomous (case file B2 as amended 2026-10-29). Package org.apache.cassandra.db.
 * Observation only: it writes raw rows to $stage4.out/raw.csv and "STAGE4 ..." lines to stdout, asserts nothing but the
 * instrument known-answer check (analyze.py judges the rows against the frozen predictions).
 * Arms: P = A built with capacity n+m (no growth), G = A built with capacity n (growth in both branches).
 * Run by unit-run.sh with the plain java launcher (-javaagent:jamm for ObjectSizes.measureDeep); with BM=1 the Byteman agent
 * traces the branch taken (rules.btm) and the allocation columns of that run are not used.
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
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.utils.ByteBufferUtil;
import org.apache.cassandra.utils.ObjectSizes;

public class AddAllBranchTest
{
    static final ClusteringComparator cmp = new ClusteringComparator(Int32Type.instance);
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static final int WARM = 3, REPS = 7;
    static PrintWriter raw;
    static Field startsF;
    static volatile Object sink;

    @BeforeClass
    public static void init() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        raw = new PrintWriter(new java.io.FileWriter(System.getProperty("stage4.out", ".") + "/raw.csv", true), true);
        startsF = RangeTombstoneList.class.getDeclaredField("starts");
        startsF.setAccessible(true);
    }

    static long now() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    static int capacity(RangeTombstoneList l) throws Exception { return ((Object[]) startsF.get(l)).length; }

    static RangeTombstone rt(int s, int e)
    {
        return new RangeTombstone(Slice.make(BufferClusteringBound.inclusiveStartOf(ByteBufferUtil.bytes(s)),
                                              BufferClusteringBound.inclusiveEndOf(ByteBufferUtil.bytes(e))),
                                  DeletionTime.build(1000L, 0));
    }

    /** n tombstones [4i, 4i+1]. */
    static RangeTombstoneList buildA(int n, int cap)
    {
        RangeTombstoneList l = new RangeTombstoneList(cmp, cap);
        for (int i = 0; i < n; i++)
            l.add(rt(4 * i, 4 * i + 1));
        return l;
    }

    static RangeTombstone[] bTombs(int m)
    {
        RangeTombstone[] b = new RangeTombstone[m];
        for (int k = 0; k < m; k++)
            b[k] = rt(4 * k + 2, 4 * k + 3);
        return b;
    }

    static RangeTombstoneList listOf(RangeTombstone[] ts, int from, int to)
    {
        RangeTombstoneList l = new RangeTombstoneList(cmp, Math.max(1, to - from));
        for (int k = from; k < to; k++)
            l.add(ts[k]);
        return l;
    }

    /** reference content: all n + m tombstones in sorted order. */
    static RangeTombstoneList reference(int n, int m, RangeTombstone[] b)
    {
        RangeTombstoneList l = new RangeTombstoneList(cmp, n + m);
        for (int i = 0; i < n; i++)
        {
            l.add(rt(4 * i, 4 * i + 1));
            if (i < m)
                l.add(b[i]);
        }
        return l;
    }

    static long median(long[] a) { long[] c = a.clone(); Arrays.sort(c); return c[c.length / 2]; }

    /** one point: call (sweep, arm, n, m); writes REPS rows. kind = "one" (A.addAll(B)) or "twinadd" (m calls with one-tombstone lists). */
    static void point(String block, String sweep, String arm, int n, int m, String kind) throws Exception
    {
        RangeTombstone[] bt = bTombs(m);
        RangeTombstoneList B = listOf(bt, 0, m);
        RangeTombstoneList[] singles = null;
        if (kind.equals("twinadd"))
        {
            singles = new RangeTombstoneList[m];
            for (int k = 0; k < m; k++)
                singles[k] = listOf(bt, k, k + 1);
        }
        RangeTombstoneList ref = reference(n, m, bt);
        long bsz = bt[0].deletedSlice().start().unsharedHeapSize() + bt[0].deletedSlice().end().unsharedHeapSize();
        for (int rep = -WARM; rep < REPS; rep++)
        {
            RangeTombstoneList A = buildA(n, arm.equals("P") ? n + m : n);
            int cap0 = capacity(A);
            long a0, a1;
            if (kind.equals("one"))
            {
                a0 = now();
                A.addAll(B);
                a1 = now();
            }
            else
            {
                a0 = now();
                for (int k = 0; k < singles.length; k++)
                    A.addAll(singles[k]);
                a1 = now();
            }
            sink = A;
            if (rep < 0)
                continue;
            boolean last = rep == REPS - 1;
            raw.println(String.join(",", block, sweep, arm, kind, "" + n, "" + m, "" + cap0, "" + rep, "" + (a1 - a0), "" + A.size(),
                                    "" + capacity(A), "" + A.unsharedHeapSize(), "" + ObjectSizes.measureDeep(A), "" + bsz,
                                    last ? (A.equals(ref) ? "1" : "0") : "-1", "" + DatabaseDescriptor.getRangeTombstoneListGrowthFactor()));
        }
    }

    @Test
    public void run() throws Exception
    {
        raw.println("block,sweep,arm,kind,n,m,cap0,rep,bytes,size,cap,unshared,deep,bsz,eq,gf");
        double gf0 = DatabaseDescriptor.getRangeTombstoneListGrowthFactor();
        System.out.println("STAGE4 info growth_factor=" + gf0 + " initial_alloc=" + DatabaseDescriptor.getInitialRangeTombstoneListAllocationSize()
                           + " heap_max=" + Runtime.getRuntime().maxMemory() + " agent=" + (System.getProperty("stage4.trace") != null ? "byteman" : "none"));
        // instrument checks
        long e0 = now(); long e1 = now();
        long k0 = now(); byte[] big = new byte[8 << 20]; long k1 = now(); sink = big;
        System.out.println("STAGE4 check empty-window-bytes=" + (e1 - e0));
        boolean ok = (k1 - k0) >= (8 << 20) && (k1 - k0) <= (8 << 20) + 65536;
        System.out.println("STAGE4 check alloc-known-answer expected=[8388608,8454144] actual=" + (k1 - k0) + (ok ? " ok" : " MISMATCH"));
        Assert.assertTrue("known-answer", ok);
        Assert.assertEquals(1.5, gf0, 0.0);
        if (System.getProperty("stage4.checkonly") != null)
            return;
        point("noise1", "N", "P", 10000, 1000, "one");
        point("noise1", "N", "G", 10000, 1000, "one");
        for (String arm : new String[]{ "P", "G" })
        {
            for (int m : new int[]{ 500, 999, 1000, 1001, 2000, 10000 })
                point("main", "S1", arm, 10000, m, "one");
            for (int n : new int[]{ 9999, 10000, 10001, 10010 })
                point("main", "S2", arm, n, 1000, "one");
            point("main", "T", arm, 10000, 1000, "one");
            point("main", "T", arm, 10000, 1000, "twinadd");
        }
        // control: growth factor 3.0, arm G, the (10000,1000) point
        DatabaseDescriptor.setRangeTombstoneListGrowthFactor(3.0);
        try { point("control", "C", "G", 10000, 1000, "one"); }
        finally { DatabaseDescriptor.setRangeTombstoneListGrowthFactor(gf0); }
        point("noise2", "N", "P", 10000, 1000, "one");
        point("noise2", "N", "G", 10000, 1000, "one");
        System.out.println("STAGE4 done");
    }
}
