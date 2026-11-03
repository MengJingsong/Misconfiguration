/*
 * Stage 4, unit tier (B2, amended 2026-10-27) of counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous. Not upstream.
 * Copied by unit-run.sh into test/unit/org/apache/cassandra/service/ of the run clone and run with
 *   ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.service.CounterCacheCapacityProbeTest
 * Every reading is one System.out.println with prefix "CCR " (B2d amendment); read from the test log.
 * guard: setCounterCacheCapacityInMB(-1) must throw, capacity unchanged.
 * sweep: table (k int PRIMARY KEY, c counter); for C in 64, (shrink to 1 without invalidation), 4, 2, 1, 0:
 *        invalidateCounterCache(), set C, UPDATE c = c + 1 for k = 1..N in order (sample every 1,000 updates), record.
 * -Dccr.n=<N> overrides N for the shakedown only (default 200,000).
 */
package org.apache.cassandra.service;

import java.util.Iterator;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;

import org.apache.cassandra.cache.AutoSavingCache;
import org.apache.cassandra.cache.CounterCacheKey;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ClockAndCount;
import org.apache.cassandra.schema.TableId;

public class CounterCacheCapacityProbeTest extends CQLTester
{
    static final int N = Integer.getInteger("ccr.n", 200_000);
    static final long MIB = 1024L * 1024L;
    long initialCapacity;

    static AutoSavingCache<CounterCacheKey, ClockAndCount> cc()
    {
        return CacheService.instance.counterCache;
    }

    static void line(String s)
    {
        System.out.println("CCR " + s);
    }

    static long own(TableId id)
    {
        long n = 0;
        Iterator<CounterCacheKey> it = cc().keyIterator();
        while (it.hasNext())
            if (it.next().tableId.equals(id))
                n++;
        return n;
    }

    @Before
    public void rememberCapacity()
    {
        initialCapacity = cc().getCapacity();
        line("start capacity=" + initialCapacity + " size=" + cc().size() + " N=" + N);
    }

    @After
    public void restoreCapacity()
    {
        CacheService.instance.setCounterCacheCapacityInMB(initialCapacity / MIB);
        line("restored capacity=" + cc().getCapacity());
    }

    @Test
    public void guard()
    {
        long before = cc().getCapacity();
        String threw = "none", msg = "";
        try
        {
            CacheService.instance.setCounterCacheCapacityInMB(-1);
        }
        catch (Throwable t)
        {
            threw = t.getClass().getName();
            msg = String.valueOf(t.getMessage());
        }
        line("guard threw=" + threw + " msg=" + msg + " capBefore=" + before + " capAfter=" + cc().getCapacity());
    }

    @Test
    public void sweep() throws Throwable
    {
        createTable("CREATE TABLE %s (k int PRIMARY KEY, c counter)");
        TableId id = getCurrentColumnFamilyStore().metadata().id;

        long[] values = { 64, -1 /* shrink step */, 4, 2, 1, 0 };
        for (long c : values)
        {
            try
            {
                if (c == -1)
                {
                    long wb = cc().weightedSize(), sb = cc().size(), ob = own(id);
                    CacheService.instance.setCounterCacheCapacityInMB(1);
                    long wa = cc().weightedSize(), sa = cc().size(), cap = cc().getCapacity();
                    line("shrink weightedBefore=" + wb + " sizeBefore=" + sb + " ownBefore=" + ob + " weightedAfter=" + wa + " sizeAfter=" + sa
                         + " ownAfter=" + own(id) + " capAfter=" + cap);
                    continue;
                }
                CacheService.instance.invalidateCounterCache();
                CacheService.instance.setCounterCacheCapacityInMB(c);
                long miss0 = cc().getMetrics().misses.getCount(), hit0 = cc().getMetrics().hits.getCount();
                long maxW = cc().weightedSize();
                for (int k = 1; k <= N; k++)
                {
                    execute("UPDATE %s SET c = c + 1 WHERE k = ?", k);
                    if (k % 1000 == 0)
                    {
                        long w = cc().weightedSize();
                        maxW = Math.max(maxW, w);
                        line("sample C=" + c + " updates=" + k + " weighted=" + w + " size=" + cc().size());
                    }
                }
                long fw = cc().weightedSize(), sz = cc().size(), o = own(id);
                maxW = Math.max(maxW, fw);
                line("pass C=" + c + " cap=" + cc().getCapacity() + " maxWeighted=" + maxW + " finalWeighted=" + fw + " size=" + sz + " own=" + o
                     + " w=" + (o > 0 ? String.valueOf((double) fw / o) : "n/a")
                     + " misses=" + (cc().getMetrics().misses.getCount() - miss0) + " hits=" + (cc().getMetrics().hits.getCount() - hit0));
            }
            catch (Throwable t)
            {
                line("error C=" + c + " " + t);
            }
        }
        line("done");
    }
}
