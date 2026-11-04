/*
 * Stage-4 harness, unit tier (B2, as amended 2026-10-26) of
 * sai_vector_term_size_fail_threshold-add-value--autonomous.
 * Not upstream code. Copied by unit-run.sh into test/unit/org/apache/cassandra/index/sai/cql/ of the run clone and
 * removed after the run.
 *
 * Arms (B2b + amendment B2b): A warn 16KiB / fail 32KiB; B 4KiB / 8KiB; C 2KiB / 8191B; D = C with two passes;
 * D0 = C with two passes on a table without the SAI index. Plus KA, the known-answer check of the float[] instrument.
 * Table: (k int PRIMARY KEY, v vector<float, 2048>); N inserts via execute() (internal); data Random(42), component
 * 0.1 + 0.9 * nextFloat(); ANN query vector Random(7).
 * Every reading is one stdout line starting "PROBE "; the test never fails on a reading. N defaults to 500; the
 * environment variable VTSC_N overrides it (shakedown only).
 */
package org.apache.cassandra.index.sai.cql;

import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;

import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.db.memtable.Memtable;
import org.apache.cassandra.index.sai.SAITester;
import org.apache.cassandra.index.sai.StorageAttachedIndex;

public class VectorTermSizeCapTest extends SAITester
{
    static final int DIM = 2048;
    static final int N = System.getenv("VTSC_N") == null ? 500 : Integer.parseInt(System.getenv("VTSC_N"));
    static final List<float[]> KA_HOLD = new ArrayList<>();

    static void out(String s)
    {
        System.out.println("PROBE " + s);
        System.out.flush();
    }

    /** live bytes of float[] and the Total line, from the JVM's class histogram (forces a full GC) */
    static long[] histo()
    {
        try
        {
            MBeanServer s = ManagementFactory.getPlatformMBeanServer();
            String h = (String) s.invoke(new ObjectName("com.sun.management:type=DiagnosticCommand"), "gcClassHistogram",
                                         new Object[]{ new String[0] }, new String[]{ String[].class.getName() });
            long f = -1, total = -1;
            for (String line : h.split("\n"))
            {
                String[] p = line.trim().split("\\s+");
                if (p.length >= 4 && p[3].equals("[F"))
                    f = Long.parseLong(p[2]);
                if (p.length >= 3 && p[0].equals("Total"))
                    total = Long.parseLong(p[2]);
            }
            return new long[]{ f, total };
        }
        catch (Exception e)
        {
            throw new RuntimeException(e);
        }
    }

    static float[] vec(Random r)
    {
        float[] v = new float[DIM];
        for (int i = 0; i < DIM; i++)
            v[i] = 0.1f + 0.9f * r.nextFloat();
        return v;
    }

    static long owns(ColumnFamilyStore cfs)
    {
        return Memtable.getMemoryUsage(cfs.getTracker().getView().getCurrentMemtable()).ownsOnHeap;
    }

    static void thresholds(String warn, String fail)
    {
        DatabaseDescriptor.getGuardrailsConfig().setSaiVectorTermSizeThreshold(new DataStorageSpec.LongBytesBound(warn),
                                                                               new DataStorageSpec.LongBytesBound(fail));
    }

    @Before
    public void readThresholdsOff()
    {
        DatabaseDescriptor.setReadThresholdsEnabled(false);
    }

    @After
    public void restoreDefaults()
    {
        thresholds("16KiB", "32KiB");
    }

    void arm(String name, String warn, String fail, boolean withIndex, boolean twice) throws Throwable
    {
        thresholds(warn, fail);
        long failBytes = DatabaseDescriptor.getGuardrailsConfig().getSaiVectorTermSizeFailThreshold().toBytes();
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v vector<float, 2048>)");
        String idx = withIndex
                     ? createIndex("CREATE INDEX ON %s(v) USING 'sai' WITH OPTIONS = {'similarity_function':'euclidean'}")
                     : null;
        disableCompaction();
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();

        Random r = new Random(42);
        long[] h0 = histo();
        long owns0 = owns(cfs);
        int passes = twice ? 2 : 1;
        for (int p = 0; p < passes; p++)
            for (int k = 0; k < N; k++)
                execute("INSERT INTO %s (k, v) VALUES (?, ?)", k, vector(vec(r)));
        long owns1 = owns(cfs);
        long[] h1 = histo();

        String sai = "memtableIndexBytes=na writeCount=na validateTermSize=na ann=na";
        if (withIndex)
        {
            StorageAttachedIndex index = (StorageAttachedIndex) cfs.indexManager.getIndexByName(idx);
            long bytes = index.memtableIndexManager().estimatedMemIndexMemoryUsed();
            long writes = index.memtableIndexManager().liveMemtableWriteCount();
            boolean valid = index.validateTermSize(cfs.decorateKey(Int32Type.instance.decompose(0)),
                                                   ByteBuffer.allocate(DIM * 4), false, null);
            int ann = execute("SELECT k FROM %s ORDER BY v ANN OF ? LIMIT 10", vector(vec(new Random(7)))).size();
            sai = "memtableIndexBytes=" + bytes + " writeCount=" + writes + " validateTermSize=" + valid + " ann=" + ann;
        }
        long rows = execute("SELECT count(*) FROM %s").one().getLong("count");
        out("arm=" + name + " warn=" + warn + " fail=" + fail + " failBytes=" + failBytes + " termBytes=" + (DIM * 4)
            + " N=" + N + " passes=" + passes + " index=" + (idx == null ? "none" : idx) + ' ' + sai
            + " ownsBefore=" + owns0 + " ownsAfter=" + owns1 + " ownsDelta=" + (owns1 - owns0)
            + " floatBefore=" + h0[0] + " floatAfter=" + h1[0] + " floatDelta=" + (h1[0] - h0[0])
            + " totalBefore=" + h0[1] + " totalAfter=" + h1[1]
            + " rows=" + rows + " sstables=" + cfs.getLiveSSTables().size());
    }

    @Test
    public void armA() throws Throwable
    {
        arm("A", "16KiB", "32KiB", true, false);
    }

    @Test
    public void armB() throws Throwable
    {
        arm("B", "4KiB", "8KiB", true, false);
    }

    @Test
    public void armC() throws Throwable
    {
        arm("C", "2KiB", "8191B", true, false);
    }

    @Test
    public void armD() throws Throwable
    {
        arm("D", "2KiB", "8191B", true, true);
    }

    @Test
    public void armD0() throws Throwable
    {
        arm("D0", "2KiB", "8191B", false, true);
    }

    @Test
    public void knownAnswer()
    {
        long[] h0 = histo();
        for (int i = 0; i < 500; i++)
            KA_HOLD.add(new float[DIM]);
        long[] h1 = histo();
        out("arm=KA held=" + KA_HOLD.size() + " expectedMin=" + (500L * (16 + 4 * DIM)) + " floatBefore=" + h0[0]
            + " floatAfter=" + h1[0] + " floatDelta=" + (h1[0] - h0[0]));
    }
}
