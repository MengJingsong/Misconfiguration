package org.apache.cassandra.index.internal;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.Base64;
import java.util.Optional;
import java.util.Random;

import org.junit.Test;

import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.memtable.AbstractAllocatorMemtable;
import org.apache.cassandra.db.memtable.Memtable;
import org.apache.cassandra.cql3.CQLTester;

/**
 * Stage 4 harness, unit tier (B2 + B2i) of max_unsigned_short-validateindexedvalue-value_remaining--autonomous.
 * -Dprobe.mode=bounds | scale ; -Dprobe.out=<file> ; -Dprobe.ns=100,1000,4000 ; -Dprobe.label=<arm label>
 * Every reading is one line "STAGE4 <kind> k=v k=v ..." in the out file.
 */
public class IndexedValueLimitTest extends CQLTester
{
    static PrintWriter out;

    static void emit(String s)
    {
        out.println("STAGE4 " + s);
        out.flush();
    }

    static String text(int i, int s)
    {
        // distinct (8-digit counter prefix) random base64 ASCII, exactly s chars
        byte[] b = new byte[(s * 3) / 4 + 8];
        new Random(1000003L * i + 17).nextBytes(b);
        String r = String.format("%08d", i) + Base64.getEncoder().encodeToString(b);
        return r.substring(0, s);
    }

    static ByteBuffer blob(int i, int s)
    {
        byte[] b = new byte[s];
        new Random(7000003L * i + 5).nextBytes(b);
        return ByteBuffer.wrap(b);
    }

    static String root(Throwable t)
    {
        while (t.getCause() != null && t.getCause() != t)
            t = t.getCause();
        String m = String.valueOf(t.getMessage()).replace('\n', ' ');
        return t.getClass().getSimpleName() + ": " + m;
    }

    String tryInsert(String q, Object... v)
    {
        try { execute(q, v); return "accepted"; }
        catch (Throwable t) { return "rejected " + root(t); }
    }

    @Test
    public void probe() throws Throwable
    {
        out = new PrintWriter(new FileWriter(System.getProperty("probe.out"), true));
        String mode = System.getProperty("probe.mode", "bounds");
        emit("start mode=" + mode + " label=" + System.getProperty("probe.label", "") + " heap_max=" + Runtime.getRuntime().maxMemory()
             + " pool_heap_limit=" + AbstractAllocatorMemtable.MEMORY_POOL.onHeap.limit);
        if (mode.equals("bounds")) bounds(); else scale();
        emit("done");
        out.close();
    }

    void bounds() throws Throwable
    {
        // regular text column, with and without the index
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v text)");
        createIndex("CREATE INDEX ON %s(v)");
        int[] sizes = {1000, 65533, 65534, 65535, 65536};
        int k = 0;
        for (int s : sizes)
            emit("bound path=regular indexed=yes S=" + s + " result=" + tryInsert("INSERT INTO %s (k, v) VALUES (?, ?)", k++, text(s, s)));
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v text)");
        for (int s : new int[]{65534, 65535, 65536})
            emit("bound path=regular indexed=no S=" + s + " result=" + tryInsert("INSERT INTO %s (k, v) VALUES (?, ?)", k++, text(s, s)));
        // clustering blob column
        createTable("CREATE TABLE %s (k int, c blob, v int, PRIMARY KEY (k, c))");
        createIndex("CREATE INDEX ON %s(c)");
        for (int s : new int[]{1000, 65534, 65535, 65536})
            emit("bound path=clustering indexed=yes S=" + s + " result=" + tryInsert("INSERT INTO %s (k, c, v) VALUES (?, ?, 1)", k++, blob(s, s)));
        createTable("CREATE TABLE %s (k int, c blob, v int, PRIMARY KEY (k, c))");
        for (int s : new int[]{65535, 65536})
            emit("bound path=clustering indexed=no S=" + s + " result=" + tryInsert("INSERT INTO %s (k, c, v) VALUES (?, ?, 1)", k++, blob(s, s)));
        // information probe: a composite partition key (single-column PK cannot be indexed)
        try
        {
            createTable("CREATE TABLE %s (k blob, c int, v int, PRIMARY KEY ((k, c)))");
            createIndex("CREATE INDEX ON %s(k)");
            for (int s : new int[]{65500, 65535})
                emit("bound path=partitionkey-composite indexed=yes S=" + s + " result=" + tryInsert("INSERT INTO %s (k, c, v) VALUES (?, 1, 1)", blob(s, s)));
        }
        catch (Throwable t)
        {
            emit("bound path=partitionkey-composite setup=failed msg=" + root(t));
        }
    }

    static long ownsOf(ColumnFamilyStore cfs)
    {
        Memtable m = cfs.getTracker().getView().getCurrentMemtable();
        return m instanceof AbstractAllocatorMemtable ? ((AbstractAllocatorMemtable) m).getAllocator().onHeap().owns() : -1;
    }

    static long heapUsedAfterGc()
    {
        for (int i = 0; i < 3; i++) System.gc();
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    void scale() throws Throwable
    {
        final int S = 65534;
        String label = System.getProperty("probe.label", "");
        for (String ns : System.getProperty("probe.ns", "100,1000,4000").split(","))
        {
            int n = Integer.parseInt(ns);
            for (boolean indexed : new boolean[]{true, false})
            {
                createTable("CREATE TABLE %s (k int PRIMARY KEY, v text)");
                String iname = indexed ? createIndex("CREATE INDEX ON %s(v)") : null;
                ColumnFamilyStore base = getCurrentColumnFamilyStore();
                ColumnFamilyStore idx = null;
                if (indexed)
                {
                    CassandraIndex ci = (CassandraIndex) base.indexManager.getIndexByName(iname);
                    Optional<ColumnFamilyStore> bt = ci.getBackingTable();
                    idx = bt.get();
                }
                long heap0 = heapUsedAfterGc();
                long peakPool = 0, peakIdx = 0, peakBase = 0, rejected = 0;
                long t0 = System.nanoTime();
                for (int i = 0; i < n; i++)
                {
                    try { execute("INSERT INTO %s (k, v) VALUES (?, ?)", i, text(i, S)); }
                    catch (Throwable t) { rejected++; if (rejected < 3) emit("reject N=" + n + " msg=" + root(t)); }
                    peakPool = Math.max(peakPool, AbstractAllocatorMemtable.MEMORY_POOL.onHeap.used());
                    peakBase = Math.max(peakBase, ownsOf(base));
                    if (idx != null) peakIdx = Math.max(peakIdx, ownsOf(idx));
                }
                double secs = (System.nanoTime() - t0) / 1e9;
                long poolEnd = AbstractAllocatorMemtable.MEMORY_POOL.onHeap.used();
                long baseOwns = ownsOf(base), idxOwns = idx == null ? 0 : ownsOf(idx);
                long baseLive = base.getTracker().getView().getCurrentMemtable().getLiveDataSize();
                long idxLive = idx == null ? 0 : idx.getTracker().getView().getCurrentMemtable().getLiveDataSize();
                int idxSstPre = idx == null ? 0 : idx.getLiveSSTables().size();
                int baseSstPre = base.getLiveSSTables().size();
                long heap1 = heapUsedAfterGc();
                base.forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
                if (idx != null) idx.forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
                long baseDisk = base.metric.liveDiskSpaceUsed.getCount();
                long idxDisk = idx == null ? 0 : idx.metric.liveDiskSpaceUsed.getCount();
                emit("scale label=" + label + " indexed=" + (indexed ? "yes" : "no") + " N=" + n + " S=" + S + " rejected=" + rejected
                     + " NxS=" + ((long) n * S) + " secs=" + String.format("%.1f", secs)
                     + " peak_pool_onheap=" + peakPool + " peak_base_owns=" + peakBase + " peak_idx_owns=" + peakIdx
                     + " end_pool_onheap=" + poolEnd + " base_owns_end=" + baseOwns + " idx_owns_end=" + idxOwns
                     + " base_live_data=" + baseLive + " idx_live_data=" + idxLive
                     + " base_sstables_before_flush=" + baseSstPre + " idx_sstables_before_flush=" + idxSstPre
                     + " heap_after_gc_before=" + heap0 + " heap_after_gc_after_load=" + heap1
                     + " base_disk=" + baseDisk + " idx_disk=" + idxDisk
                     + " base_sstables=" + base.getLiveSSTables().size() + " idx_sstables=" + (idx == null ? 0 : idx.getLiveSSTables().size()));
            }
        }
    }
}
