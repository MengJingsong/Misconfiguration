package org.apache.cassandra.db;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.cache.CounterCacheKey;
import org.apache.cassandra.db.marshal.CounterColumnType;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.schema.ColumnMetadata;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.service.CacheService;
import org.apache.cassandra.utils.ByteBufferUtil;

import static org.apache.cassandra.utils.ByteBufferUtil.bytes;

/**
 * Stage-4 harness for the three counter_cache_size autonomous cases (unit tier, B2 of each file).
 * One class, one JVM; writes "U<part> key=value ..." lines to $STAGE4_OUT/unit.txt; verdicts are made by the analyze_unit_*.py scripts, not here.
 *   U1 direct   : puts straight into counterCache (case iscountercacheenabled B2c) + the helper's value on a counter and a regular table
 *   U2 cfs      : cfs.putCachedCounter / getCachedCounter (cases getcachedcounter, putcachedcounter B2c) + heap after gc
 *   U3 real     : CounterMutation.apply (the production path that calls the gates) at capacities 0/1/4
 *   U4 reload   : save the cache, then loadSaved() at several capacities (the only caller of isCounterCacheEnabled)
 *   U5 resize   : runtime shrink and reopen
 * The same class runs on the unpatched tree and on the patched "noguard" tree (guards at ColumnFamilyStore 2501/2508 removed, helper >= 0).
 */
public class CounterCacheCapTest
{
    static final long MIB = 1024 * 1024;
    static final String KS = "S4CounterCap", CTR = "Ctr", REG = "Reg";
    static PrintWriter out;
    static long initCap;
    static CounterCacheKey dummy;

    @BeforeClass
    public static void defineSchema()
    {
        SchemaLoader.prepareServer();
        initCap = CacheService.instance.counterCache.getCapacity();
        TableMetadata.Builder ctr = TableMetadata.builder(KS, CTR).isCounter(true)
                                                 .addPartitionKeyColumn("key", Int32Type.instance)
                                                 .addClusteringColumn("name", Int32Type.instance)
                                                 .addRegularColumn("c", CounterColumnType.instance);
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1), ctr, SchemaLoader.standardCFMD(KS, REG));
    }

    static void rec(String s) { out.println(s); out.flush(); System.out.println("STAGE4 " + s); }

    static long alloc()
    {
        return ((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId());
    }

    static long heap()
    {
        for (int i = 0; i < 3; i++) { System.gc(); try { Thread.sleep(150); } catch (InterruptedException e) {} }
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    static void settle()
    {
        try { Thread.sleep(100); } catch (InterruptedException e) {}
        if (dummy != null) CacheService.instance.counterCache.get(dummy); // a read schedules Caffeine maintenance
        try { Thread.sleep(100); } catch (InterruptedException e) {}
    }

    static String stats(String tag)
    {
        return String.format("%s_weighted=%d %s_size=%d %s_capacity=%d", tag, CacheService.instance.counterCache.weightedSize(), tag, CacheService.instance.counterCache.size(), tag, CacheService.instance.counterCache.getCapacity());
    }

    @Test
    public void all() throws Exception
    {
        String dir = System.getenv().getOrDefault("STAGE4_OUT", "/tmp");
        out = new PrintWriter(new FileWriter(dir + "/unit.txt", false));
        try
        {
            rec(String.format("U0 initCapacity=%d initCapacityMiB=%d maxMemory=%d tree=%s", initCap, initCap / MIB, Runtime.getRuntime().maxMemory(), System.getenv().getOrDefault("STAGE4_TREE", "?")));
            ColumnFamilyStore ctr = Keyspace.open(KS).getColumnFamilyStore(CTR);
            ColumnFamilyStore reg = Keyspace.open(KS).getColumnFamilyStore(REG);
            dummy = CounterCacheKey.create(ctr.metadata(), bytes(-77), cl(ctr), ctr.metadata().getColumn(bytes("c")), null);
            // arms: init (the unit yaml default, left as it is), 0, 1, 4, 4 again (warm-up control)
            long[] arms = { -1, 0, 1, 4, 4 };
            for (int a = 0; a < arms.length; a++) direct(ctr, reg, arms[a], a);
            for (int a = 0; a < arms.length; a++) viaCfs(ctr, arms[a], a);
            real(ctr, reg);
            resize(ctr);
        }
        finally { out.close(); }
    }

    static void setCap(long mib)
    {
        if (mib >= 0) CacheService.instance.setCounterCacheCapacityInMB(mib);
        else CacheService.instance.counterCache.setCapacity(initCap);
        CacheService.instance.invalidateCounterCache();
    }

    static Clustering<?> cl(ColumnFamilyStore cfs) { return CBuilder.create(cfs.metadata().comparator).add(ByteBufferUtil.bytes(1)).build(); }

    static long entryWeight(ColumnFamilyStore cfs, ColumnMetadata cd)
    {
        CounterCacheKey k = CounterCacheKey.create(cfs.metadata(), bytes(1234567), cl(cfs), cd, null);
        return k.unsharedHeapSize() + ClockAndCount.create(1, 1).unsharedHeapSize();
    }

    static long nFor(long capBytes, long w) { return Math.max(200000, 4 * capBytes / w); }

    // U1: B2c of the iscountercacheenabled file
    static void direct(ColumnFamilyStore ctr, ColumnFamilyStore reg, long mib, int idx) throws Exception
    {
        setCap(mib);
        ColumnMetadata cd = ctr.metadata().getColumn(bytes("c"));
        long cap = CacheService.instance.counterCache.getCapacity();
        long w = entryWeight(ctr, cd);
        long n = nFor(cap, w);
        boolean hc = ctr.isCounterCacheEnabled(), hr = reg.isCounterCacheEnabled();
        long h0 = heap();
        Clustering<?> c1 = cl(ctr);
        for (long i = 0; i < n; i++)
            CacheService.instance.counterCache.put(CounterCacheKey.create(ctr.metadata(), bytes((int) i), c1, cd, null), ClockAndCount.create(i, i));
        String imm = stats("immediate");
        settle();
        long h1 = heap();
        rec(String.format("U1 arm=%d capMiB=%s helperCounter=%b helperRegular=%b entryWeight=%d puts=%d %s %s heapDelta=%d", idx, mib < 0 ? "init" : String.valueOf(mib), hc, hr, w, n, imm, stats("settled"), h1 - h0));
        CacheService.instance.invalidateCounterCache();
    }

    // U2: B2c of getcachedcounter and putcachedcounter
    static void viaCfs(ColumnFamilyStore ctr, long mib, int idx) throws Exception
    {
        setCap(mib);
        ColumnMetadata cd = ctr.metadata().getColumn(bytes("c"));
        long cap = CacheService.instance.counterCache.getCapacity();
        long w = entryWeight(ctr, cd);
        long n = nFor(cap, w);
        Clustering<?> c1 = cl(ctr);
        long h0 = heap();
        long a0 = alloc();
        for (long i = 0; i < n; i++)
            ctr.putCachedCounter(bytes((int) i), c1, cd, null, ClockAndCount.create(i, i));
        long putAlloc = alloc() - a0;
        String imm = stats("immediate");
        settle();
        long h1 = heap();
        String st = stats("settled");
        long hits = 0; boolean first = false, last = false;
        long a1 = alloc();
        for (long i = 0; i < n; i++)
        {
            ClockAndCount cc = ctr.getCachedCounter(bytes((int) i), c1, cd, null);
            if (cc != null) hits++;
            if (i == 0) first = cc != null;
            if (i == n - 1) last = cc != null;
        }
        long getAlloc = alloc() - a1;
        rec(String.format("U2 arm=%d capMiB=%s entryWeight=%d puts=%d %s %s heapDelta=%d getHits=%d getFirst=%b getLast=%b putAllocPerCall=%d getAllocPerCall=%d", idx, mib < 0 ? "init" : String.valueOf(mib), w, n, imm, st, h1 - h0, hits, first, last, putAlloc / n, getAlloc / n));
        CacheService.instance.invalidateCounterCache();
    }

    // U3 + U4: production write path, then save / load
    static void real(ColumnFamilyStore ctr, ColumnFamilyStore reg) throws Exception
    {
        final int N = 60000;
        for (long mib : new long[]{ 0, 1, 4 })
        {
            setCap(mib);
            long t0 = System.nanoTime();
            for (int i = 0; i < N; i++)
                new CounterMutation(new RowUpdateBuilder(ctr.metadata(), 0, bytes(i)).clustering(1).add("c", 1L).build(), ConsistencyLevel.ONE).apply();
            settle();
            rec(String.format("U3 capMiB=%d updates=%d %s ms=%d", mib, N, stats("settled"), (System.nanoTime() - t0) / 1000000));
        }
        // regular-table control at 4 MiB: writes to a non-counter table leave the counter cache empty
        setCap(4);
        for (int i = 0; i < 20000; i++)
            new RowUpdateBuilder(reg.metadata(), 0, bytes(i)).clustering("cc").add("val", "v").build().applyUnsafe();
        settle();
        rec(String.format("U3 control=regular-writes capMiB=4 inserts=20000 helperRegular=%b %s", reg.isCounterCacheEnabled(), stats("settled")));
        // refill at 4 MiB through the production path, save, and reload at several capacities
        setCap(4);
        for (int i = 0; i < N; i++)
            new CounterMutation(new RowUpdateBuilder(ctr.metadata(), 0, bytes(i)).clustering(1).add("c", 1L).build(), ConsistencyLevel.ONE).apply();
        settle();
        long before = CacheService.instance.counterCache.size();
        CacheService.instance.counterCache.submitWrite(Integer.MAX_VALUE).get();
        rec(String.format("U4 saved cacheSizeBeforeSave=%d %s", before, stats("afterSave")));
        for (long mib : new long[]{ 0, 1, 4, 0, -1 })
        {
            setCap(mib);
            boolean h = ctr.isCounterCacheEnabled();
            int cnt = CacheService.instance.counterCache.loadSaved();
            settle();
            rec(String.format("U4 reload capMiB=%s helperCounter=%b loadSavedReturned=%d %s", mib < 0 ? "init" : String.valueOf(mib), h, cnt, stats("settled")));
        }
        CacheService.instance.invalidateCounterCache();
    }

    // U5
    static void resize(ColumnFamilyStore ctr) throws Exception
    {
        ColumnMetadata cd = ctr.metadata().getColumn(bytes("c"));
        Clustering<?> c1 = cl(ctr);
        setCap(4);
        for (int i = 0; i < 200000; i++) ctr.putCachedCounter(bytes(i), c1, cd, null, ClockAndCount.create(i, i));
        settle();
        rec("U5 filled4 " + stats("settled"));
        CacheService.instance.setCounterCacheCapacityInMB(1);
        long wImm = CacheService.instance.counterCache.weightedSize();
        settle();
        rec(String.format("U5 shrunk1 weightedImmediate=%d %s", wImm, stats("settled")));
        CacheService.instance.setCounterCacheCapacityInMB(0);
        settle();
        rec("U5 shrunk0 " + stats("settled") + " getFirstKey=" + (ctr.getCachedCounter(bytes(199999), c1, cd, null) != null));
        CacheService.instance.setCounterCacheCapacityInMB(4);
        for (int i = 0; i < 200000; i++) ctr.putCachedCounter(bytes(i), c1, cd, null, ClockAndCount.create(i, i));
        settle();
        rec("U5 reopened4 " + stats("settled"));
    }
}
