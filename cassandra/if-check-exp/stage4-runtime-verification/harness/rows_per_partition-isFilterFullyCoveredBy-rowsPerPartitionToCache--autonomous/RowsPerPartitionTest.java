package org.apache.cassandra.db;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.ByteBuffer;

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
 * Stage-4 harness for rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache--autonomous (unit tier, B2).
 * Writes "key=value" lines to $STAGE4_OUT/unit.txt (echoed as "STAGE4 key=value"). The verdict is made by analyze_unit.py, not here.
 * Env STAGE4_ROWS overrides the partition size (default 1000; shakedown only).
 */
public class RowsPerPartitionTest extends CQLTester
{
    static PrintWriter out;
    static int ROWS;
    static final String V100 = "x".repeat(100);

    static void rec(String s) { out.println(s); out.flush(); System.out.println("STAGE4 " + s); }

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
            // first trigger: N=10 must put an entry into the cache; if not the setup is wrong and nothing else is run
            if (!arm("10", "10"))
            {
                rec("firsttrigger=FAIL");
                return;
            }
            rec("firsttrigger=OK");
            for (String n : new String[]{ "1", "100", "ALL", "2000", "NONE" })
                arm(n, n);
            tombstoneRows();
            tombstoneRange();
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

    String createClustered(String n) throws Throwable
    {
        String t = createTable("CREATE TABLE %s (pk int, ck int, v text, PRIMARY KEY (pk, ck)) WITH caching = {'keys':'ALL','rows_per_partition':'" + n + "'}");
        return t;
    }

    void fill() throws Throwable
    {
        for (int i = 0; i < ROWS; i++)
            execute("INSERT INTO %s (pk, ck, v) VALUES (1, ?, ?)", i, V100);
        flush();
    }

    /** reads the entry of pk=1 and records its shape under prefix p; returns whether a real entry (not a sentinel) is present */
    boolean entry(ColumnFamilyStore cfs, String p)
    {
        IRowCacheEntry e = CacheService.instance.rowCache.get(key(cfs, 1));
        if (e == null) { rec(p + ".entry=absent"); return false; }
        if (!(e instanceof CachedPartition)) { rec(p + ".entry=" + e.getClass().getSimpleName()); return false; }
        CachedBTreePartition cp = (CachedBTreePartition) e;
        rec(p + ".entry=present");
        rec(p + ".cachedLiveRows=" + cp.cachedLiveRows());
        rec(p + ".rowCount=" + cp.rowCount());
        rec(p + ".serializedSize=" + CachedPartition.cacheSerializer.serializedSize(cp));
        rec(p + ".rangeTombstones=" + cp.deletionInfo().rangeCount());
        return true;
    }

    void metrics(ColumnFamilyStore cfs, String p)
    {
        rec(p + ".hit=" + cfs.metric.rowCacheHit.getCount());
        rec(p + ".miss=" + cfs.metric.rowCacheMiss.getCount());
        rec(p + ".outOfRange=" + cfs.metric.rowCacheHitOutOfRange.getCount());
    }

    void covered(ColumnFamilyStore cfs, String p)
    {
        IRowCacheEntry e = CacheService.instance.rowCache.get(key(cfs, 1));
        if (!(e instanceof CachedPartition)) return;
        CachedPartition cp = (CachedPartition) e;
        long now = FBUtilities.nowInSeconds();
        boolean strict = cfs.metadata().enforceStrictLiveness();
        boolean full = cfs.isFilterFullyCoveredBy(new ClusteringIndexSliceFilter(Slices.ALL, false), DataLimits.NONE, cp, now, strict);
        boolean head5 = cfs.isFilterFullyCoveredBy(new ClusteringIndexSliceFilter(Slices.ALL, false), DataLimits.cqlLimits(5), cp, now, strict);
        rec(p + ".coveredFullSlice=" + full);
        rec(p + ".coveredHead5=" + head5);
    }

    boolean arm(String label, String n) throws Throwable
    {
        String p = "N" + label;
        createClustered(n);
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        CacheService.instance.invalidateRowCacheForCf(cfs.metadata());
        rec(p + ".cachingParam=" + cfs.metadata().params.caching.rowsPerPartitionToCache());
        fill();
        rec(p + ".isRowCacheEnabled=" + cfs.isRowCacheEnabled());
        int rows1 = execute("SELECT * FROM %s WHERE pk=1 LIMIT 5").size();
        rec(p + ".read1.rows=" + rows1);
        metrics(cfs, p + ".after1");
        boolean present = entry(cfs, p);
        if (present) covered(cfs, p);
        int rows2 = execute("SELECT * FROM %s WHERE pk=1 LIMIT 5").size();
        rec(p + ".read2.rows=" + rows2);
        metrics(cfs, p + ".after2");
        return present;
    }

    void tombstoneRows() throws Throwable
    {
        String p = "TOMBROWS";
        createClustered("10");
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        fill();
        for (int i = 0; i < 50; i++)
            execute("DELETE FROM %s WHERE pk=1 AND ck=?", i);
        flush();
        CacheService.instance.invalidateRowCacheForCf(cfs.metadata());
        rec(p + ".read.rows=" + execute("SELECT * FROM %s WHERE pk=1 LIMIT 5").size());
        entry(cfs, p);
    }

    void tombstoneRange() throws Throwable
    {
        String p = "TOMBRANGE";
        createClustered("10");
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        fill();
        execute("DELETE FROM %s WHERE pk=1 AND ck < 50");
        flush();
        CacheService.instance.invalidateRowCacheForCf(cfs.metadata());
        rec(p + ".read.rows=" + execute("SELECT * FROM %s WHERE pk=1 LIMIT 5").size());
        entry(cfs, p);
    }

    void noClustering() throws Throwable
    {
        for (String[] c : new String[][]{ { "1", "100" }, { "5", "100" }, { "1", "5000" } })
        {
            String p = "NOCK_N" + c[0] + "_v" + c[1];
            createTable("CREATE TABLE %s (pk int PRIMARY KEY, v text) WITH caching = {'keys':'ALL','rows_per_partition':'" + c[0] + "'}");
            ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
            execute("INSERT INTO %s (pk, v) VALUES (1, ?)", "y".repeat(Integer.parseInt(c[1])));
            flush();
            CacheService.instance.invalidateRowCacheForCf(cfs.metadata());
            rec(p + ".read.rows=" + execute("SELECT * FROM %s WHERE pk=1").size());
            entry(cfs, p);
        }
    }
}
