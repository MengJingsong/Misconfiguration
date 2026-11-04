package org.apache.cassandra.db;

import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

import org.junit.Test;

import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.filter.DataLimits;
import org.apache.cassandra.db.rows.AbstractUnfilteredRowIterator;
import org.apache.cassandra.db.rows.BTreeRow;
import org.apache.cassandra.db.rows.BufferCell;
import org.apache.cassandra.db.rows.EncodingStats;
import org.apache.cassandra.db.rows.Row;
import org.apache.cassandra.db.rows.Rows;
import org.apache.cassandra.db.rows.Unfiltered;
import org.apache.cassandra.db.rows.UnfilteredRowIterator;
import org.apache.cassandra.schema.ColumnMetadata;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.utils.ByteBufferUtil;

/**
 * Stage-4 unit tier (B2, as amended 2026-10-27) of cql-row-limit-incrementRowCount-rowsCounted--autonomous. Not upstream code.
 * Drains a synthetic lazy source of SOURCE rows (one partition, one blob cell of the stated width, a fresh buffer per row) through
 * DataLimits.cqlLimits(L) (its CQLCounter, the counter whose incrementRowCount() is the target) and retains the rows; reads rowsCounted,
 * output rows, retained heap (three System.gc() before each reading) and the sum of Row.unsharedHeapSize().
 * Writes $STAGE4_OUT/unit.txt (key=value lines). $STAGE4_SRC (default 1200000) shrinks the source for shakedowns only.
 */
public class RowLimitMemoryProbeTest extends CQLTester
{
    static final int[] WIDTHS = { 16, 1024, 65536 };
    static final int REPS = Integer.getInteger("stage4.reps", Integer.parseInt(System.getenv().getOrDefault("STAGE4_REPS", "5")));
    static final long BYTE_STOP = 8L << 20;
    static final long NOW = 1_000_000L;     // nowInSec; the cells and markers are written at timestamp 1000 us

    PrintWriter out;
    TableMetadata md;
    ColumnMetadata col;
    int source;

    static class Src extends AbstractUnfilteredRowIterator
    {
        final ColumnMetadata col; final int n, width, liveEvery; int i = 0; long pulled = 0;
        Src(TableMetadata md, ColumnMetadata col, int n, int width, int liveEvery)
        {
            super(md, md.partitioner.decorateKey(ByteBufferUtil.bytes(1)), DeletionTime.LIVE, md.regularAndStaticColumns(), Rows.EMPTY_STATIC_ROW, false, EncodingStats.NO_STATS);
            this.col = col; this.n = n; this.width = width; this.liveEvery = liveEvery;
        }
        protected Unfiltered computeNext()
        {
            if (i >= n) return endOfData();
            int k = i++; pulled++;
            Clustering<?> c = Clustering.make(ByteBufferUtil.bytes(k));
            if (liveEvery > 0 && k % liveEvery != 0)
                return BTreeRow.emptyDeletedRow(c, Row.Deletion.regular(DeletionTime.build(1000, 1000)));
            return BTreeRow.singleCellRow(c, BufferCell.live(col, 1000, ByteBuffer.allocate(width)));
        }
    }

    static long used()
    {
        try { for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(100); } } catch (InterruptedException e) { throw new RuntimeException(e); }
        Runtime r = Runtime.getRuntime(); return r.totalMemory() - r.freeMemory();
    }

    void kv(String k, Object v) { out.println(k + "=" + v); out.flush(); }

    /** One drain: limit L (or -1 = NONE), width w. liveEvery 0 = all rows live. retain = keep the rows. Returns output rows. */
    void point(String key, int L, int w, int liveEvery, boolean retain)
    {
        long base = retain ? used() : 0;
        try
        {
            Src src = new Src(md, col, source, w, liveEvery);
            DataLimits limits = L < 0 ? DataLimits.NONE : DataLimits.cqlLimits(L);
            DataLimits.Counter counter = null; UnfilteredRowIterator it;
            if (L < 0) it = limits.filter(src, NOW, false);               // NONE: the identity, no counter at all (DataLimits.java:59-78)
            else { counter = limits.newCounter(NOW, false, false, md.enforceStrictLiveness()); it = counter.applyTo(src); }   // = limits.filter(...)
            List<Row> keep = retain ? new ArrayList<>() : null;
            long outRows = 0, outLive = 0, unshared = 0;
            try (UnfilteredRowIterator iter = it)
            {
                while (iter.hasNext())
                {
                    Unfiltered u = iter.next();
                    if (!u.isRow()) continue;
                    Row r = (Row) u; outRows++;
                    if (r.hasLiveData(NOW, false)) outLive++;
                    if (retain) { keep.add(r); unshared += r.unsharedHeapSize(); }
                }
            }
            kv(key + ".rowsCounted", counter == null ? -1 : counter.rowsCounted());
            kv(key + ".isDone", counter == null ? "na" : counter.isDone());
            kv(key + ".out", outRows); kv(key + ".outLive", outLive); kv(key + ".pulled", src.pulled);
            if (retain)
            {
                long after = used();
                kv(key + ".retained", after - base); kv(key + ".unshared", unshared);
                if (keep.size() != outRows) throw new IllegalStateException("retain mismatch");
            }
            keep = null;
        }
        catch (OutOfMemoryError e) { kv(key + ".oom", 1); }
    }

    /** Positive control: NONE chain, the consumer stops at a running Row.unsharedHeapSize() sum of BYTE_STOP. */
    void control(String key, int w)
    {
        long base = used();
        Src src = new Src(md, col, source, w, 0);
        List<Row> keep = new ArrayList<>(); long sum = 0;
        try (UnfilteredRowIterator iter = DataLimits.NONE.filter(src, NOW, false))
        {
            while (iter.hasNext() && sum < BYTE_STOP)
            {
                Unfiltered u = iter.next(); Row r = (Row) u; keep.add(r); sum += r.unsharedHeapSize();
            }
        }
        long after = used();
        kv(key + ".rows", keep.size()); kv(key + ".unshared", sum); kv(key + ".retained", after - base); kv(key + ".pulled", src.pulled);
        keep = null;
    }

    @Test
    public void probe() throws Throwable
    {
        String dir = System.getenv("STAGE4_OUT");
        source = Integer.parseInt(System.getenv().getOrDefault("STAGE4_SRC", "1200000"));
        out = new PrintWriter(new java.io.FileWriter(dir + "/unit.txt"));
        createTable("CREATE TABLE %s (pk int, ck int, v blob, PRIMARY KEY (pk, ck))");
        md = getCurrentColumnFamilyStore().metadata();
        col = md.getColumn(ByteBufferUtil.bytes("v"));
        kv("SOURCE", source); kv("REPS", REPS);
        // first trigger: L=100, w=16 must stop at 100 rows
        point("warm", 100, 16, 0, true);
        kv("firsttrigger", (source > 100) ? "OK" : "BAD");   // replaced by the analyzer's check of warm.rowsCounted == 100
        int[][] grid = {
            { 16, 1, 100, 1000, 10000, 1000000 },
            { 1024, 1, 100, 1000, 10000, 0 },
            { 65536, 1, 100, 1000, 0, 0 } };
        for (int rep = 1; rep <= REPS; rep++)
        {
            for (int[] g : grid)
                for (int j = 1; j < g.length; j++)
                {
                    if (g[j] == 0 || g[j] >= source) continue;
                    point("P.w" + g[0] + ".L" + g[j] + ".r" + rep, g[j], g[0], 0, true);
                }
            point("NONE.w16.r" + rep, -1, 16, 0, true);
            for (int L : new int[] { 1, 100, 1000 })
                if (10L * L < source) point("DEAD.w16.L" + L + ".r" + rep, L, 16, 10, false);
            for (int w : WIDTHS) control("CTL.w" + w + ".r" + rep, w);
        }
        kv("done", 1);
        out.close();
    }
}
