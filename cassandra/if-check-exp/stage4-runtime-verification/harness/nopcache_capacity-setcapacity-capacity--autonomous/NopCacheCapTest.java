package org.apache.cassandra.cache;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Paths;

import org.junit.Test;

import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.schema.TableId;
import org.apache.cassandra.service.CacheService;

/**
 * Stage-4 harness for nopcache_capacity-setcapacity-capacity--autonomous (unit tier, B2).
 * Writes "N<part> key=value ..." lines to $STAGE4_OUT/unit.txt; verdicts are made by analyze_unit.py, not here.
 *   N1 : NopCache from NopCacheProvider.create(): setCapacity(0, 1 MiB, 64 MiB, -1, Long.MAX), 2,000,000 puts, get/size/weightedSize/capacity
 *   N2 : the same call through InstrumentingCache (the wrapper CacheService holds)
 *   N3 : OHC control (the unit yaml's row cache, OHCProvider, 16 MiB): 20,000 x 1 KiB partitions read twice, then setRowCacheCapacityInMB(32), read again
 */
public class NopCacheCapTest extends CQLTester
{
    static final long MIB = 1024 * 1024;
    static PrintWriter out;

    static void rec(String s) { out.println(s); out.flush(); System.out.println("STAGE4 " + s); }

    static long rssAnon() throws Exception
    {
        for (String l : Files.readAllLines(Paths.get("/proc/self/status")))
            if (l.startsWith("RssAnon:")) return Long.parseLong(l.replaceAll("[^0-9]", "")) * 1024;
        return -1;
    }

    static long heap()
    {
        for (int i = 0; i < 3; i++) { System.gc(); try { Thread.sleep(150); } catch (InterruptedException e) {} }
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    static String trySet(ICache<RowCacheKey, IRowCacheEntry> c, long v)
    {
        try { c.setCapacity(v); return "none"; }
        catch (Throwable t) { return t.getClass().getName() + ":" + t.getMessage(); }
    }

    @Test
    public void all() throws Exception
    {
        String dir = System.getenv().getOrDefault("STAGE4_OUT", "/tmp");
        out = new PrintWriter(new FileWriter(dir + "/unit.txt", false));
        try
        {
            nop();
            wrapper();
            ohcControl();
        }
        finally { out.close(); }
    }

    void nop() throws Exception
    {
        ICache<RowCacheKey, IRowCacheEntry> c = new NopCacheProvider().create();
        rec("N1 class=" + c.getClass().getName() + " capacityAtCreate=" + c.capacity());
        for (long v : new long[]{ 0, 1 * MIB, 64 * MIB, -1, Long.MAX_VALUE })
            rec(String.format("N1 setCapacity v=%d exception=%s capacityAfter=%d", v, trySet(c, v), c.capacity()));
        long h0 = heap(), r0 = rssAnon();
        TableId tid = TableId.generate();
        int putIfAbsentTrue = 0, replaceTrue = 0, getNonNull = 0;
        for (int i = 0; i < 2000000; i++)
        {
            RowCacheKey k = new RowCacheKey(tid, null, ("key" + i).getBytes());
            IRowCacheEntry e = new RowCacheSentinel(i);
            c.put(k, e);
            if (c.putIfAbsent(k, e)) putIfAbsentTrue++;
            if (c.replace(k, e, e)) replaceTrue++;
            if (c.get(k) != null) getNonNull++;
        }
        long h1 = heap(), r1 = rssAnon();
        rec(String.format("N1 puts=2000000 size=%d weightedSize=%d capacity=%d putIfAbsentTrue=%d replaceTrue=%d getNonNull=%d heapDelta=%d rssAnonDelta=%d",
                          c.size(), c.weightedSize(), c.capacity(), putIfAbsentTrue, replaceTrue, getNonNull, h1 - h0, r1 - r0));
    }

    void wrapper() throws Exception
    {
        InstrumentingCache<RowCacheKey, IRowCacheEntry> w = new InstrumentingCache<>("nopRowCacheTest", new NopCacheProvider().create());
        for (long v : new long[]{ 0, 64 * MIB })
        {
            String ex = "none";
            try { w.setCapacity(v); } catch (Throwable t) { ex = t.getClass().getName() + ":" + t.getMessage(); }
            rec(String.format("N2 wrapper setCapacity v=%d exception=%s getCapacity=%d", v, ex, w.getCapacity()));
        }
    }

    void ohcControl() throws Exception
    {
        InstrumentingCache<RowCacheKey, IRowCacheEntry> rc = CacheService.instance.rowCache;
        rec(String.format("N3 class=%s capacityAtStart=%d", rc.getClass().getSimpleName(), rc.getCapacity()));
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob) WITH caching = {'keys':'ALL','rows_per_partition':'ALL'}");
        final int N = 20000;
        ByteBuffer val = ByteBuffer.allocate(1024);
        for (int i = 0; i < N; i++) execute("INSERT INTO %s (k, v) VALUES (?, ?)", i, val);
        flush();
        long r0 = rssAnon();
        for (int pass = 1; pass <= 2; pass++)
        {
            for (int i = 0; i < N; i++)
            {
                execute("SELECT * FROM %s WHERE k = ?", i);
                if (i % 5000 == 4999)
                    rec(String.format("N3 phase=A pass=%d reads=%d capacity=%d size=%d weightedSize=%d rssAnonDelta=%d", pass, i + 1, rc.getCapacity(), rc.size(), rc.weightedSize(), rssAnon() - r0));
            }
        }
        String ex = "none";
        try { CacheService.instance.setRowCacheCapacityInMB(32); } catch (Throwable t) { ex = t.getClass().getName() + ":" + t.getMessage(); }
        rec(String.format("N3 setRowCacheCapacityInMB(32) exception=%s capacityAfter=%d", ex, rc.getCapacity()));
        for (int pass = 1; pass <= 2; pass++)
        {
            for (int i = 0; i < N; i++) execute("SELECT * FROM %s WHERE k = ?", i);
            rec(String.format("N3 phase=B pass=%d capacity=%d size=%d weightedSize=%d rssAnonDelta=%d", pass, rc.getCapacity(), rc.size(), rc.weightedSize(), rssAnon() - r0));
        }
    }
}
