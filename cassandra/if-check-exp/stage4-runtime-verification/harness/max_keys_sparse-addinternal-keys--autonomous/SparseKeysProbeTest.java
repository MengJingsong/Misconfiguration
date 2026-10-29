/*
 * Stage-4 unit probe for max_keys_sparse-addinternal-keys--autonomous (B2). Copied by unit-run.sh into the run copy's
 * test/unit/org/apache/cassandra/index/sasi/disk/. Writes "STAGE4 ..." lines to the file named by -Dstage4.out.
 * Cells (B2b/B2c, with the 2026-10-28 amendments): mode SPARSE and PREFIX x (K,T); control = segmenting rule at 8 MiB (B2h).
 */
package org.apache.cassandra.index.sasi.disk;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.db.marshal.UTF8Type;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.index.sasi.disk.OnDiskIndexBuilder.Mode;
import org.apache.cassandra.io.FSWriteError;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.io.util.FileUtils;

public class SparseKeysProbeTest
{
    static PrintWriter out;
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

    @BeforeClass
    public static void setup() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        out = new PrintWriter(new FileWriter(System.getProperty("stage4.out", "/tmp/stage4-sparse.out")), true);
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

    static List<DecoratedKey> keys(int k)
    {
        List<DecoratedKey> l = new ArrayList<>(k);
        for (int j = 0; j < k; j++)
            l.add(Murmur3Partitioner.instance.decorateKey(UTF8Type.instance.decompose("k" + j)));
        return l;
    }

    static OnDiskIndexBuilder builder(Mode m) { return new OnDiskIndexBuilder(UTF8Type.instance, Int32Type.instance, m); }

    void cell(Mode mode, int K, int T) throws Exception
    {
        List<DecoratedKey> ks = keys(K);
        long h0 = heapUsed();
        long a0 = alloc();
        OnDiskIndexBuilder b = builder(mode);
        for (int i = 0; i < T; i++)
        {
            ByteBuffer term = Int32Type.instance.decompose(i);
            for (int j = 0; j < K; j++)
                b.add(term, ks.get(j), j);
        }
        long a1 = alloc();
        long est = b.estimatedMemoryUse();
        long h1 = heapUsed();
        long expected = (long) T * 116 + (long) T * K * 108;
        File f = FileUtils.createTempFile("s4-sparse", "db");
        String outcome; String cause = "-";
        long len = -1;
        try
        {
            boolean r = b.finish(f);
            outcome = "ok finish=" + r;
            len = f.length();
        }
        catch (FSWriteError e)
        {
            outcome = "FSWriteError";
            cause = String.valueOf(e.getCause() == null ? "null" : e.getCause().getMessage()).replace(' ', '_');
            len = f.exists() ? f.length() : -1;
        }
        f.tryDelete();
        out.println("STAGE4 cell mode=" + mode + " K=" + K + " T=" + T + " est=" + est + " expected=" + expected
                    + " allocAdds=" + (a1 - a0) + " heapDelta=" + (h1 - h0) + " outcome=" + outcome + " filelen=" + len + " cause=" + cause);
        boolean estOk = est == expected;
        boolean predOk = mode == Mode.PREFIX || K <= 5 ? outcome.startsWith("ok") : (outcome.equals("FSWriteError") && cause.contains("belongs_to_more_than_5_keys_in_SPARSE_mode"));
        out.println("STAGE4 check mode=" + mode + " K=" + K + " T=" + T + " est==expected " + (estOk ? "ok" : "MISMATCH"));
        out.println("STAGE4 check mode=" + mode + " K=" + K + " T=" + T + " outcome-as-predicted " + (predOk ? "ok" : "MISMATCH"));
    }

    @Test
    public void cells() throws Exception
    {
        // JIT/class warm-up, not recorded as a cell
        cellQuiet();
        int[][] plan = { {1, 10000}, {4, 10000}, {5, 10000}, {6, 10000}, {7, 10000}, {50, 10000}, {1000, 500}, {4, 20000}, {6, 20000} };
        for (int rep = 1; rep <= 3; rep++)
            for (Mode m : new Mode[]{ Mode.SPARSE, Mode.PREFIX })
                for (int[] p : plan)
                {
                    out.println("STAGE4 rep " + rep);
                    cell(m, p[0], p[1]);
                }
    }

    void cellQuiet() throws Exception
    {
        OnDiskIndexBuilder b = builder(Mode.PREFIX);
        List<DecoratedKey> ks = keys(3);
        for (int i = 0; i < 2000; i++) for (int j = 0; j < 3; j++) b.add(Int32Type.instance.decompose(i), ks.get(j), j);
        File f = FileUtils.createTempFile("s4-warm", "db");
        b.finish(f); f.tryDelete();
    }

    /** B2h control: emulate PerSSTableIndexWriter.Index.add's rule (PerSSTableIndexWriter.java:247) with maxMemorySize 8 MiB, PREFIX, K = 6. */
    @Test
    public void control() throws Exception
    {
        final long max = 8L * 1024 * 1024;
        final int K = 6;
        List<DecoratedKey> ks = keys(K);
        for (int T : new int[]{ 20000, 40000, 80000 })
        {
            OnDiskIndexBuilder b = builder(Mode.PREFIX);
            int closed = 0; long maxClosed = 0, minClosed = Long.MAX_VALUE, maxAny = 0, totalEst = 0; long finishedBytes = 0;
            for (int i = 0; i < T; i++)
            {
                ByteBuffer term = Int32Type.instance.decompose(i);
                for (int j = 0; j < K; j++)
                {
                    b.add(term, ks.get(j), j);
                    long e = b.estimatedMemoryUse();
                    maxAny = Math.max(maxAny, e);
                    if (e >= max)
                    {
                        File f = FileUtils.createTempFile("s4-seg", "db");
                        b.finish(f);
                        finishedBytes += f.length();
                        f.tryDelete();
                        closed++; maxClosed = Math.max(maxClosed, e); minClosed = Math.min(minClosed, e); totalEst += e;
                        b = builder(Mode.PREFIX);
                    }
                }
            }
            long rem = b.estimatedMemoryUse();
            long E = (long) T * 764;
            out.println("STAGE4 control T=" + T + " E=" + E + " closedSegments=" + closed + " floorE/max=" + (E / max) + " maxClosedEst=" + maxClosed
                        + " minClosedEst=" + (closed == 0 ? -1 : minClosed) + " maxAnyEst=" + maxAny + " remainderEst=" + rem + " segmentFileBytes=" + finishedBytes);
            long fl = E / max;
            out.println("STAGE4 check control T=" + T + " segments-within-1-of-floor " + (Math.abs(closed - fl) <= 1 ? "ok" : "MISMATCH"));
            out.println("STAGE4 check control T=" + T + " no-builder-above-max+223 " + (maxAny <= max + 223 ? "ok" : "MISMATCH"));
            out.println("STAGE4 check control T=" + T + " total-est-conserved-up-to-116-per-split-term " + (totalEst + rem >= E && totalEst + rem <= E + 116L * closed ? "ok" : "MISMATCH"));
        }
    }
}
