package org.apache.cassandra.cql3;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Optional;
import java.util.Random;

import org.junit.Test;

import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.memtable.AbstractAllocatorMemtable;
import org.apache.cassandra.db.memtable.Memtable;
import org.apache.cassandra.index.internal.CassandraIndex;

/**
 * Stage 4 harness, unit tier (B2 + B2i) of name_length-validatecustomindexcolumnname-name--autonomous.
 * -Dprobe.mode=names | rows ; -Dprobe.out=<file>
 *   names: L in {1,47,48,49,64,200} x {custom (SASI), plain} x 3 repeats, 10,000 rows of a 100-char hex value each
 *   rows : plain index, L=10, N in {1000,10000,100000}; unindexed baseline L=10 N=10000
 * Every reading is one line "STAGE4 arm k=v ..." in the out file.
 */
public class NameLengthProbeTest extends CQLTester
{
    static PrintWriter out;
    static final String SASI = "org.apache.cassandra.index.sasi.SASIIndex";

    static void emit(String s) { out.println("STAGE4 " + s); out.flush(); }

    static String root(Throwable t)
    {
        while (t.getCause() != null && t.getCause() != t) t = t.getCause();
        return (t.getClass().getSimpleName() + ": " + t.getMessage()).replace('\n', ' ');
    }

    static String colName(int L)
    {
        StringBuilder b = new StringBuilder("c");
        while (b.length() < L) b.append('x');
        return b.toString();
    }

    static String hex(int i)
    {
        byte[] b = new byte[50];
        new Random(31L * i + 3).nextBytes(b);
        StringBuilder s = new StringBuilder();
        for (byte x : b) s.append(String.format("%02x", x));
        return s.toString(); // 100 chars
    }

    static long ownsOf(ColumnFamilyStore cfs)
    {
        Memtable m = cfs.getTracker().getView().getCurrentMemtable();
        return m instanceof AbstractAllocatorMemtable ? ((AbstractAllocatorMemtable) m).getAllocator().onHeap().owns() : -1;
    }

    static long dirBytes(File f)
    {
        if (f.isFile()) return f.length();
        long t = 0;
        File[] l = f.listFiles();
        if (l != null) for (File x : l) t += dirBytes(x);
        return t;
    }

    static long heapAfterGc()
    {
        for (int i = 0; i < 3; i++) System.gc();
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    @Test
    public void probe() throws Throwable
    {
        out = new PrintWriter(new FileWriter(System.getProperty("probe.out"), true));
        String mode = System.getProperty("probe.mode", "names");
        emit("start mode=" + mode + " sasi_enabled=" + org.apache.cassandra.config.DatabaseDescriptor.getSASIIndexesEnabled() + " heap_max=" + Runtime.getRuntime().maxMemory());
        if (mode.equals("names"))
        {
            for (int rep = 1; rep <= 3; rep++)
                for (int L : new int[]{1, 47, 48, 49, 64, 200})
                    for (String kind : new String[]{"custom", "plain"})
                        arm(kind, L, rep, 10000);
        }
        else
        {
            for (int n : new int[]{1000, 10000, 100000})
                arm("plain", 10, 1, n);
            arm("none", 10, 1, 10000);
        }
        emit("done");
        out.close();
    }

    void arm(String kind, int L, int rep, int n) throws Throwable
    {
        String col = colName(L);
        String tag = "kind=" + kind + " L=" + L + " rep=" + rep + " N=" + n;
        try
        {
            createTable("CREATE TABLE %s (k int PRIMARY KEY, " + col + " text)");
        }
        catch (Throwable t)
        {
            emit("arm " + tag + " create_table=rejected msg=" + root(t));
            return;
        }
        ColumnFamilyStore base = getCurrentColumnFamilyStore();
        ColumnFamilyStore idx = null;
        String iname = "i_" + kind + "_" + L + "_" + rep + "_" + n;
        if (!kind.equals("none"))
        {
            String q = kind.equals("custom")
                       ? "CREATE CUSTOM INDEX " + iname + " ON %s(" + col + ") USING '" + SASI + "'"
                       : "CREATE INDEX " + iname + " ON %s(" + col + ")";
            try
            {
                createIndex(q);
            }
            catch (Throwable t)
            {
                emit("arm " + tag + " create_index=rejected msg=" + root(t));
                return;
            }
            if (kind.equals("plain"))
            {
                Optional<ColumnFamilyStore> bt = ((CassandraIndex) base.indexManager.getIndexByName(iname)).getBackingTable();
                idx = bt.get();
            }
        }
        long heap0 = heapAfterGc();
        long rejected = 0;
        long t0 = System.nanoTime();
        for (int i = 0; i < n; i++)
        {
            try { execute("INSERT INTO %s (k, " + col + ") VALUES (?, ?)", i, hex(i)); }
            catch (Throwable t) { rejected++; if (rejected < 3) emit("reject " + tag + " msg=" + root(t)); }
        }
        double secs = (System.nanoTime() - t0) / 1e9;
        long baseOwns = ownsOf(base), idxOwns = idx == null ? 0 : ownsOf(idx);
        long baseLive = base.getTracker().getView().getCurrentMemtable().getLiveDataSize();
        long heap1 = heapAfterGc();
        base.forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
        if (idx != null) idx.forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
        long dir = 0;
        for (org.apache.cassandra.io.util.File d : base.getDirectories().getCFDirectories()) dir += dirBytes(d.toJavaIOFile());
        emit("arm " + tag + " result=accepted rejected_rows=" + rejected + " secs=" + String.format("%.1f", secs)
             + " base_owns=" + baseOwns + " idx_owns=" + idxOwns + " base_live_data=" + baseLive
             + " heap_before=" + heap0 + " heap_after_load=" + heap1 + " dir_bytes=" + dir
             + " base_sstables=" + base.getLiveSSTables().size());
    }
}
