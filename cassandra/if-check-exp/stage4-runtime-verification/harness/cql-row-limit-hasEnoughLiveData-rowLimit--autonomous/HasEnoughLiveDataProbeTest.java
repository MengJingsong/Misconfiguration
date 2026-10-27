package org.apache.cassandra.db;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;

import org.junit.Test;

import org.apache.cassandra.cache.IRowCacheEntry;
import org.apache.cassandra.cache.RowCacheKey;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.filter.DataLimits;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.db.partitions.CachedBTreePartition;
import org.apache.cassandra.db.partitions.CachedPartition;
import org.apache.cassandra.service.CacheService;
import org.apache.cassandra.utils.FBUtilities;

/**
 * Stage-4 harness for cql-row-limit-hasEnoughLiveData-rowLimit--autonomous (unit tier, B2 as amended 2026-10-27).
 * Writes "key=value" lines to $STAGE4_OUT/unit.txt (echoed as "STAGE4 key=value"). The verdict is made by analyze_unit.py, not here.
 * Env STAGE4_ROWS overrides the partition size (default 1000; shakedown only).
 */
public class HasEnoughLiveDataProbeTest extends CQLTester
{
    static PrintWriter out;
    static int ROWS;
    static final String V100 = "x".repeat(100);
    static final int NONE = -1; // "no limit"
    static final List<ColumnFamilyStore> PREV = new ArrayList<>();
    static final int[] LS = { 1, 50, 100, 101, 1000, 1000000, NONE };

    static void rec(String s) { out.println(s); out.flush(); System.out.println("STAGE4 " + s); }
    static String ln(int l) { return l == NONE ? "none" : Integer.toString(l); }

    @Test
    public void all() throws Throwable
    {
        String dir = System.getenv().getOrDefault("STAGE4_OUT", "/tmp");
        ROWS = Integer.parseInt(System.getenv().getOrDefault("STAGE4_ROWS", "1000"));
        out = new PrintWriter(new FileWriter(dir + "/unit.txt", false));
        try
        {
            rec("ROWS=" + ROWS);
            rec("rowCacheCapacity=" + CacheService.instance.rowCache.getCapacity());
            // first trigger: R=100 must leave an entry of 100 rows and the direct call for L=100 must return true
            if (!arm("100", true))
            {
                rec("firsttrigger=FAIL");
                return;
            }
            rec("firsttrigger=OK");
            arm("ALL", false);
            arm("500", false);
            negativeControl();
            rec("done=1");
        }
        finally
        {
            out.close();
        }
    }

    static RowCacheKey key(ColumnFamilyStore cfs, int pk)
    {
        DecoratedKey dk = cfs.decorateKey(Int32Type.instance.decompose(pk));
        return new RowCacheKey(cfs.metadata(), dk);
    }

    static CachedBTreePartition entry(ColumnFamilyStore cfs)
    {
        IRowCacheEntry e = CacheService.instance.rowCache.get(key(cfs, 1));
        return e instanceof CachedBTreePartition ? (CachedBTreePartition) e : null;
    }

    static long heap()
    {
        System.gc(); System.gc();
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    static long alloc()
    {
        return ((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId());
    }

    String create(String r) throws Throwable
    {
        return createTable("CREATE TABLE %s (pk int, ck int, v text, PRIMARY KEY (pk, ck)) WITH caching = {'keys':'ALL','rows_per_partition':'" + r + "'}");
    }

    void fill() throws Throwable
    {
        for (int i = 0; i < ROWS; i++)
            execute("INSERT INTO %s (pk, ck, v) VALUES (1, ?, ?)", i, V100);
        flush();
    }

    String q(int l) { return l == NONE ? "SELECT * FROM %s WHERE pk=1" : "SELECT * FROM %s WHERE pk=1 LIMIT " + l; }

    boolean arm(String r, boolean firstTrigger) throws Throwable
    {
        String p = "R" + r;
        create(r);
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        // entries of the tables of earlier arms stay in the cache unless removed: weightedSize is the whole cache (defect found at the first unit pass, 2026-10-27)
        for (ColumnFamilyStore prev : PREV) CacheService.instance.invalidateRowCacheForCf(prev.metadata());
        CacheService.instance.invalidateRowCacheForCf(cfs.metadata());
        PREV.add(cfs);
        rec(p + ".pre.weighted=" + CacheService.instance.rowCache.weightedSize());
        rec(p + ".pre.size=" + CacheService.instance.rowCache.size());
        fill();
        rec(p + ".cachingParam=" + cfs.metadata().params.caching.rowsPerPartitionToCache());
        rec(p + ".isRowCacheEnabled=" + cfs.isRowCacheEnabled());
        rec(p + ".populate.rows=" + execute(q(NONE)).size());      // miss: fills the entry
        CachedBTreePartition cp = entry(cfs);
        if (cp == null) { rec(p + ".entry=absent"); return false; }
        rec(p + ".entry.cachedLiveRows=" + cp.cachedLiveRows());
        rec(p + ".entry.rowCount=" + cp.rowCount());
        rec(p + ".entry.rowsWithNonExpiringCells=" + cp.rowsWithNonExpiringCells());
        rec(p + ".entry.serializedSize=" + CachedPartition.cacheSerializer.serializedSize(cp));
        long now = FBUtilities.nowInSeconds();
        if (firstTrigger)
        {
            boolean ok = cp.cachedLiveRows() == 100 && DataLimits.cqlLimits(100).hasEnoughLiveData(cp, now, false, true);
            if (!ok) return false;
        }
        long w0 = CacheService.instance.rowCache.weightedSize(), s0 = CacheService.instance.rowCache.size();
        long h0 = heap();
        rec(p + ".base.weighted=" + w0);
        rec(p + ".base.size=" + s0);
        rec(p + ".base.heap=" + h0);
        for (int round = 1; round <= 3; round++)
        {
            List<Integer> order = new ArrayList<>();
            for (int l : LS) order.add(l);
            Collections.shuffle(order, new Random(74 + round));
            for (int l : order)
            {
                String k = p + ".r" + round + ".L" + ln(l);
                long hit0 = cfs.metric.rowCacheHit.getCount(), miss0 = cfs.metric.rowCacheMiss.getCount(), oor0 = cfs.metric.rowCacheHitOutOfRange.getCount();
                CachedBTreePartition e = entry(cfs);
                boolean direct = (l == NONE ? DataLimits.NONE : DataLimits.cqlLimits(l)).hasEnoughLiveData(e, now, false, true);
                long a0 = alloc();
                int rows = execute(q(l)).size();
                long a1 = alloc();
                rec(k + ".direct=" + direct);
                rec(k + ".rows=" + rows);
                rec(k + ".hit=" + (cfs.metric.rowCacheHit.getCount() - hit0));
                rec(k + ".miss=" + (cfs.metric.rowCacheMiss.getCount() - miss0));
                rec(k + ".oor=" + (cfs.metric.rowCacheHitOutOfRange.getCount() - oor0));
                rec(k + ".weighted=" + CacheService.instance.rowCache.weightedSize());
                rec(k + ".size=" + CacheService.instance.rowCache.size());
                rec(k + ".heap=" + heap());
                rec(k + ".allocBytes=" + (a1 - a0));
            }
        }
        return true;
    }

    void negativeControl() throws Throwable
    {
        String p = "NEG";
        long cap = CacheService.instance.rowCache.getCapacity();
        try
        {
            CacheService.instance.setRowCacheCapacityInMB(0);
            create("100");
            ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
            fill();
            rec(p + ".isRowCacheEnabled=" + cfs.isRowCacheEnabled());
            long hit0 = cfs.metric.rowCacheHit.getCount(), miss0 = cfs.metric.rowCacheMiss.getCount(), oor0 = cfs.metric.rowCacheHitOutOfRange.getCount();
            execute(q(NONE)); execute(q(10)); execute(q(1000));
            rec(p + ".hit=" + (cfs.metric.rowCacheHit.getCount() - hit0));
            rec(p + ".miss=" + (cfs.metric.rowCacheMiss.getCount() - miss0));
            rec(p + ".oor=" + (cfs.metric.rowCacheHitOutOfRange.getCount() - oor0));
            rec(p + ".entry=" + (entry(cfs) == null ? "absent" : "present"));
        }
        catch (Throwable t)
        {
            rec(p + ".error=" + t);
        }
        finally
        {
            try { CacheService.instance.rowCache.setCapacity(cap); } catch (Throwable t) { rec(p + ".restoreError=" + t); }
        }
    }
}
