/*
 * Stage-4 harness, unit tier (B2, as amended 2026-10-26) of
 * row_cache_size-setRowCacheCapacityInMB-capacity--autonomous.
 * Copied into test/unit/org/apache/cassandra/service/ of the run clone by unit-run.sh and removed afterwards.
 * Every reading is one "RCP " line on System.out (B2d amendment). RCP_SHAKE=1 runs a smaller N (shakedown, not judged).
 */
package org.apache.cassandra.service;

import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.Random;

import org.junit.After;
import org.junit.Test;

import org.apache.cassandra.cache.ICache;
import org.apache.cassandra.cache.InstrumentingCache;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.caffinitas.ohc.OHCache;
import org.caffinitas.ohc.OHCacheStats;

public class RowCacheCapacityProbeTest extends CQLTester
{
    static final boolean SHAKE = "1".equals(System.getenv("RCP_SHAKE"));
    static final int N = SHAKE ? 8000 : 40000;
    static final long MIB = 1024L * 1024L;

    static void out(String s)
    {
        System.out.println("RCP " + s);
    }

    static OHCache<?, ?> ohc() throws Exception
    {
        Field f = InstrumentingCache.class.getDeclaredField("map");
        f.setAccessible(true);
        ICache<?, ?> adapter = (ICache<?, ?>) f.get(CacheService.instance.rowCache);
        Field g = adapter.getClass().getDeclaredField("ohCache");
        g.setAccessible(true);
        return (OHCache<?, ?>) g.get(adapter);
    }

    static long used()
    {
        return CacheService.instance.rowCache.weightedSize();
    }

    static int entries()
    {
        return CacheService.instance.rowCache.size();
    }

    static long cap()
    {
        return CacheService.instance.rowCache.getCapacity();
    }

    @After
    public void restore()
    {
        CacheService.instance.setRowCacheCapacityInMB(16);
    }

    /** Reads k = from .. to-1 in order; samples every 1,000 reads; prints one pass line. */
    void pass(String phase, long c, int from, int to) throws Throwable
    {
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        OHCacheStats s0 = ohc().stats();
        long miss0 = cfs.metric.rowCacheMiss.getCount(), hit0 = cfs.metric.rowCacheHit.getCount();
        long maxUsed = 0;
        for (int k = from; k < to; k++)
        {
            execute("SELECT v FROM %s WHERE k = ?", k);
            long u = used();
            if (u > maxUsed)
                maxUsed = u;
            int i = k - from + 1;
            if (i % 1000 == 0)
                out("sample phase=" + phase + " C=" + c + " reads=" + i + " used=" + u + " entries=" + entries());
        }
        OHCacheStats s1 = ohc().stats();
        long u = used();
        int e = entries();
        out("pass phase=" + phase + " C=" + c + " cap=" + cap() + " maxUsed=" + maxUsed + " finalUsed=" + u + " entries=" + e
            + " perEntry=" + (e > 0 ? (u / (double) e) : 0) + " dMiss=" + (cfs.metric.rowCacheMiss.getCount() - miss0)
            + " dHit=" + (cfs.metric.rowCacheHit.getCount() - hit0) + " dEvict=" + (s1.getEvictionCount() - s0.getEvictionCount())
            + " dPutFail=" + (s1.getPutFailCount() - s0.getPutFailCount()));
    }

    @Test
    public void probe() throws Throwable
    {
        out("config N=" + N + " shake=" + SHAKE + " cpus=" + Runtime.getRuntime().availableProcessors());
        try
        {
            out("ohc " + ohc());
        }
        catch (Throwable t)
        {
            out("ohc error " + t);
        }

        // step 1: guard
        try
        {
            long before = cap();
            String threw = "none", msg = "";
            try
            {
                CacheService.instance.setRowCacheCapacityInMB(-1);
            }
            catch (Throwable t)
            {
                threw = t.getClass().getName();
                msg = String.valueOf(t.getMessage());
            }
            out("guard threw=" + threw + " msg=" + msg + " capBefore=" + before + " capAfter=" + cap());
        }
        catch (Throwable t)
        {
            out("guard error " + t);
        }

        createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob) WITH caching = {'keys':'NONE','rows_per_partition':'ALL'}");
        Random r = new Random(42);
        for (int k = 0; k < N; k++)
        {
            byte[] b = new byte[1024];
            r.nextBytes(b);
            execute("INSERT INTO %s (k, v) VALUES (?, ?)", k, ByteBuffer.wrap(b));
        }
        flush();
        out("data rows=" + N + " sstables=" + getCurrentColumnFamilyStore().getLiveSSTables().size());

        // step 2: sweep
        for (long c : new long[]{ 16, 8, 4, 2, 1 })
        {
            try
            {
                CacheService.instance.invalidateRowCache();
                CacheService.instance.setRowCacheCapacityInMB(c);
                pass("sweep", c, 0, N);
            }
            catch (Throwable t)
            {
                out("sweep error C=" + c + " " + t);
            }
        }

        // step 3: second pass at C = 1, no invalidation
        try
        {
            pass("second", 1, 0, N);
        }
        catch (Throwable t)
        {
            out("second error " + t);
        }

        // step 4: runtime shrink of a full cache
        try
        {
            CacheService.instance.invalidateRowCache();
            CacheService.instance.setRowCacheCapacityInMB(16);
            pass("refill", 16, 0, N);
            long ub = used();
            int eb = entries();
            CacheService.instance.setRowCacheCapacityInMB(1);
            out("shrink usedBefore=" + ub + " entriesBefore=" + eb + " usedAfterSet=" + used() + " entriesAfterSet=" + entries()
                + " capAfterSet=" + cap());
            pass("aftershrink", 1, 0, 2000);
        }
        catch (Throwable t)
        {
            out("shrink error " + t);
        }
        out("done");
    }
}
