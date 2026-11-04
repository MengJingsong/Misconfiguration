/*
 * Stage 4, unit tier (B2, amended 2026-10-27) of key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous. Not upstream.
 * Copied by unit-run.sh into test/unit/org/apache/cassandra/service/ of the run clone and run with
 *   ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.service.KeyCacheCapacityProbeTest
 * Every reading is one System.out.println with prefix "KCR " (B2d amendment); read from the test log.
 * guard: setKeyCacheCapacityInMB(-1) must throw, capacity unchanged.
 * sweep: N rows (k bigint, v int), flush, compact; for C in 64, (shrink to 1 without invalidation), 4, 2, 1, 0:
 *        invalidateKeyCache(), set C, read every k in order (sample every 1,000 reads), record.
 * -Dkcr.n=<N> overrides N for the shakedown only (default 200,000).
 */
package org.apache.cassandra.service;

import java.util.Iterator;
import java.util.TreeMap;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;

import org.apache.cassandra.cache.AutoSavingCache;
import org.apache.cassandra.cache.KeyCacheKey;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.io.sstable.AbstractRowIndexEntry;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.schema.TableId;

public class KeyCacheCapacityProbeTest extends CQLTester
{
    static final int N = Integer.getInteger("kcr.n", 200_000);
    static final long MIB = 1024L * 1024L;
    long initialCapacity;

    static AutoSavingCache<KeyCacheKey, AbstractRowIndexEntry> kc()
    {
        return CacheService.instance.keyCache;
    }

    static void line(String s)
    {
        System.out.println("KCR " + s);
    }

    static long own(TableId id)
    {
        long n = 0;
        Iterator<KeyCacheKey> it = kc().keyIterator();
        while (it.hasNext())
            if (it.next().tableId.equals(id))
                n++;
        return n;
    }

    @Before
    public void rememberCapacity()
    {
        initialCapacity = kc().getCapacity();
        line("start capacity=" + initialCapacity + " size=" + kc().size() + " N=" + N);
    }

    @After
    public void restoreCapacity()
    {
        CacheService.instance.setKeyCacheCapacityInMB(initialCapacity / MIB);
        line("restored capacity=" + kc().getCapacity());
    }

    @Test
    public void guard()
    {
        long before = kc().getCapacity();
        String threw = "none", msg = "";
        try
        {
            CacheService.instance.setKeyCacheCapacityInMB(-1);
        }
        catch (Throwable t)
        {
            threw = t.getClass().getName();
            msg = String.valueOf(t.getMessage());
        }
        line("guard threw=" + threw + " msg=" + msg + " capBefore=" + before + " capAfter=" + kc().getCapacity());
    }

    @Test
    public void sweep() throws Throwable
    {
        createTable("CREATE TABLE %s (k bigint PRIMARY KEY, v int) WITH caching = {'keys':'ALL','rows_per_partition':'NONE'}");
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        TableId id = cfs.metadata().id;
        for (long k = 0; k < N; k++)
            execute("INSERT INTO %s (k, v) VALUES (?, ?)", k, (int) k);
        flush();
        compact();
        TreeMap<String, Integer> formats = new TreeMap<>();
        for (SSTableReader s : cfs.getLiveSSTables())
            formats.merge(s.descriptor.version.format.name() + "/" + s.descriptor.version.version, 1, Integer::sum);
        line("table sstables=" + cfs.getLiveSSTables().size() + " formats=" + formats + " caching_keys=" + cfs.metadata().params.caching.cacheKeys());

        long[] values = { 64, -1 /* shrink step */, 4, 2, 1, 0 };
        for (long c : values)
        {
            try
            {
                if (c == -1)
                {
                    long wb = kc().weightedSize(), sb = kc().size(), ob = own(id);
                    CacheService.instance.setKeyCacheCapacityInMB(1);
                    long wa = kc().weightedSize(), sa = kc().size(), cap = kc().getCapacity();
                    line("shrink weightedBefore=" + wb + " sizeBefore=" + sb + " ownBefore=" + ob + " weightedAfter=" + wa + " sizeAfter=" + sa
                         + " ownAfter=" + own(id) + " capAfter=" + cap);
                    continue;
                }
                CacheService.instance.invalidateKeyCache();
                CacheService.instance.setKeyCacheCapacityInMB(c);
                long miss0 = kc().getMetrics().misses.getCount(), hit0 = kc().getMetrics().hits.getCount();
                long maxW = kc().weightedSize();
                for (long k = 0; k < N; k++)
                {
                    execute("SELECT v FROM %s WHERE k = ?", k);
                    if ((k + 1) % 1000 == 0)
                    {
                        long w = kc().weightedSize();
                        maxW = Math.max(maxW, w);
                        line("sample C=" + c + " reads=" + (k + 1) + " weighted=" + w + " size=" + kc().size());
                    }
                }
                long fw = kc().weightedSize(), sz = kc().size(), o = own(id);
                maxW = Math.max(maxW, fw);
                line("pass C=" + c + " cap=" + kc().getCapacity() + " maxWeighted=" + maxW + " finalWeighted=" + fw + " size=" + sz + " own=" + o
                     + " w=" + (o > 0 ? String.valueOf((double) fw / o) : "n/a")
                     + " misses=" + (kc().getMetrics().misses.getCount() - miss0) + " hits=" + (kc().getMetrics().hits.getCount() - hit0));
            }
            catch (Throwable t)
            {
                line("error C=" + c + " " + t);
            }
        }
        line("done");
    }
}
