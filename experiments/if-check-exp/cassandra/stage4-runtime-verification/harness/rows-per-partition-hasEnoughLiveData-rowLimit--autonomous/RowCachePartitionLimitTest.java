package org.apache.cassandra.db;

import java.io.FileWriter;
import java.io.PrintWriter;

import org.junit.Test;

import org.apache.cassandra.cache.IRowCacheEntry;
import org.apache.cassandra.cache.RowCacheKey;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.filter.ClusteringIndexSliceFilter;
import org.apache.cassandra.db.filter.DataLimits;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.db.partitions.CachedBTreePartition;
import org.apache.cassandra.db.partitions.CachedPartition;
import org.apache.cassandra.service.CacheService;
import org.apache.cassandra.utils.FBUtilities;

/**
 * Stage-4 harness for rows-per-partition-hasEnoughLiveData-rowLimit--autonomous (unit tier, B2).
 * Writes "key=value" lines to $STAGE4_OUT/unit.txt (echoed as "STAGE4 key=value"). The verdict is made by analyze_unit.py, not here.
 * Env STAGE4_ROWS overrides the partition size (default 200; shakedown only).
 */
public class RowCachePartitionLimitTest extends CQLTester
{
    static PrintWriter out;
    static int ROWS;
    static final String V100 = "x".repeat(100);
    static final int[] LIMITS = { 1, 4, 5, 6, 49, 50, 51, 1000 };

    static void rec(String s) { out.println(s); out.flush(); System.out.println("STAGE4 " + s); }

    @Test
    public void all() throws Throwable
    {
        String dir = System.getenv().getOrDefault("STAGE4_OUT", "/tmp");
        ROWS = Integer.parseInt(System.getenv().getOrDefault("STAGE4_ROWS", "200"));
        out = new PrintWriter(new FileWriter(dir + "/unit.txt", false));
        try
        {
            rec("ROWS=" + ROWS);
            rec("rowCacheCapacity=" + CacheService.instance.rowCache.getCapacity());
            // first trigger: N=5 must leave a real entry after the populating read; if not the setup is wrong and nothing else is run
            if (!arm("5", "5", false, 0))
            {
                rec("firsttrigger=FAIL");
                return;
            }
            rec("firsttrigger=OK");
            arm("50", "50", false, 0);
            arm("ALL", "ALL", false, 0);
            arm("NONE", "NONE", false, 0);
            arm("TTL", "5", true, 0);
            arm("TOMB", "5", false, 50);
            noClustering();
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

    /** records the entry of pk=1 under prefix p; returns the entry or null if absent / a sentinel */
    CachedBTreePartition entry(String p)
    {
        IRowCacheEntry e = CacheService.instance.rowCache.get(key(getCurrentColumnFamilyStore(), 1));
        if (e == null) { rec(p + ".entry=absent"); return null; }
        if (!(e instanceof CachedPartition)) { rec(p + ".entry=" + e.getClass().getSimpleName()); return null; }
        CachedBTreePartition cp = (CachedBTreePartition) e;
        rec(p + ".entry=present");
        rec(p + ".cachedLiveRows=" + cp.cachedLiveRows());
        rec(p + ".rowCount=" + cp.rowCount());
        rec(p + ".rowsWithNonExpiringCells=" + cp.rowsWithNonExpiringCells());
        rec(p + ".serializedSize=" + CachedPartition.cacheSerializer.serializedSize(cp));
        rec(p + ".rcSize=" + CacheService.instance.rowCache.size());
        rec(p + ".rcWeightedSize=" + CacheService.instance.rowCache.weightedSize());
        return cp;
    }

    void metrics(ColumnFamilyStore cfs, String p)
    {
        rec(p + ".hit=" + cfs.metric.rowCacheHit.getCount());
        rec(p + ".miss=" + cfs.metric.rowCacheMiss.getCount());
        rec(p + ".outOfRange=" + cfs.metric.rowCacheHitOutOfRange.getCount());
    }

    /** one arm: table with rows_per_partition n; ttl: rows inserted with TTL; deleted: ck 0..deleted-1 are row-deleted before the first read */
    boolean arm(String label, String n, boolean ttl, int deleted) throws Throwable
    {
        String p = label;
        createTable("CREATE TABLE %s (pk int, ck int, v text, PRIMARY KEY (pk, ck)) WITH caching = {'keys':'ALL','rows_per_partition':'" + n + "'}");
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        rec(p + ".cachingParam=" + cfs.metadata().params.caching.rowsPerPartitionToCache());
        for (int i = 0; i < ROWS; i++)
            execute("INSERT INTO %s (pk, ck, v) VALUES (1, ?, ?)" + (ttl ? " USING TTL 3600" : ""), i, V100);
        flush();
        for (int i = 0; i < deleted; i++)
            execute("DELETE FROM %s WHERE pk=1 AND ck=?", i);
        if (deleted > 0) flush();
        CacheService.instance.invalidateRowCacheForCf(cfs.metadata());
        rec(p + ".pre.rcSize=" + CacheService.instance.rowCache.size());
        rec(p + ".pre.rcWeightedSize=" + CacheService.instance.rowCache.weightedSize());
        rec(p + ".isRowCacheEnabled=" + cfs.isRowCacheEnabled());
        rec(p + ".populate.rows=" + execute("SELECT * FROM %s WHERE pk=1 LIMIT 1").size());
        metrics(cfs, p + ".populate");
        CachedBTreePartition cp = entry(p + ".populate");
        boolean present = cp != null;
        long now = FBUtilities.nowInSeconds();
        boolean strict = cfs.metadata().enforceStrictLiveness();
        for (int l : LIMITS)
        {
            long h0 = cfs.metric.rowCacheHit.getCount(), m0 = cfs.metric.rowCacheMiss.getCount(), o0 = cfs.metric.rowCacheHitOutOfRange.getCount();
            if (present)
            {
                rec(p + ".L" + l + ".hasEnough=" + DataLimits.cqlLimits(l).hasEnoughLiveData(cp, now, false, strict));
                rec(p + ".L" + l + ".covered=" + cfs.isFilterFullyCoveredBy(new ClusteringIndexSliceFilter(Slices.ALL, false), DataLimits.cqlLimits(l), cp, now, strict));
            }
            int rows = execute("SELECT * FROM %s WHERE pk=1 LIMIT " + l).size();
            rec(p + ".L" + l + ".rows=" + rows);
            rec(p + ".L" + l + ".dHit=" + (cfs.metric.rowCacheHit.getCount() - h0));
            rec(p + ".L" + l + ".dMiss=" + (cfs.metric.rowCacheMiss.getCount() - m0));
            rec(p + ".L" + l + ".dOut=" + (cfs.metric.rowCacheHitOutOfRange.getCount() - o0));
        }
        entry(p + ".after");
        return present;
    }

    void noClustering() throws Throwable
    {
        String p = "NOCK";
        createTable("CREATE TABLE %s (pk int PRIMARY KEY, v text) WITH caching = {'keys':'ALL','rows_per_partition':'5'}");
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        execute("INSERT INTO %s (pk, v) VALUES (1, ?)", V100);
        flush();
        CacheService.instance.invalidateRowCacheForCf(cfs.metadata());
        rec(p + ".read.rows=" + execute("SELECT * FROM %s WHERE pk=1").size());
        entry(p);
    }
}
