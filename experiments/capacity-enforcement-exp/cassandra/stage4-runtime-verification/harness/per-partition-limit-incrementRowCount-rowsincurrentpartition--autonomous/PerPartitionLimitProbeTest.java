package org.apache.cassandra.db;

import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

import org.junit.Test;

import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.filter.DataLimits;
import org.apache.cassandra.db.partitions.AbstractUnfilteredPartitionIterator;
import org.apache.cassandra.db.partitions.UnfilteredPartitionIterator;
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
 * Stage-4 unit tier (B2, as amended 2026-10-27) of per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous. Not upstream code.
 * Drains synthetic lazy sources through DataLimits.cqlLimits(NO_LIMIT, n) (its CQLCounter; incrementRowCount() is the target) and retains the rows;
 * reads rowsCounted, rowsCountedInCurrentPartition, output rows, retained heap (three System.gc() before each reading), the sum of Row.unsharedHeapSize()
 * and the thread's allocated bytes. Writes $STAGE4_OUT/unit.txt (key=value lines). $STAGE4_SRC (default 20000) shrinks the source for shakedowns only.
 */
public class PerPartitionLimitProbeTest extends CQLTester
{
    static final int[] WIDTHS = { 16, 1024, 65536 };
    static final int REPS = Integer.parseInt(System.getenv().getOrDefault("STAGE4_REPS", "5"));
    static final long BYTE_STOP = 8L << 20;
    static final long NOW = 1_000_000L;     // nowInSec; cells and markers are written at timestamp 1000 us
    static final int PARTS = 20, PART_ROWS = 5000;

    PrintWriter out;
    TableMetadata md;
    ColumnMetadata col;
    int source;

    static Unfiltered mkRow(ColumnMetadata col, int k, int width, int liveEvery)
    {
        Clustering<?> c = Clustering.make(ByteBufferUtil.bytes(k));
        if (liveEvery > 0 && k % liveEvery != 0)
            return BTreeRow.emptyDeletedRow(c, Row.Deletion.regular(DeletionTime.build(1000, 1000)));
        return BTreeRow.singleCellRow(c, BufferCell.live(col, 1000, ByteBuffer.allocate(width)));
    }

    static class Src extends AbstractUnfilteredRowIterator
    {
        final ColumnMetadata col; final int n, width, liveEvery; int i = 0; long pulled = 0; final long[] total;
        Src(TableMetadata md, ColumnMetadata col, int pk, int n, int width, int liveEvery, long[] total)
        {
            super(md, md.partitioner.decorateKey(ByteBufferUtil.bytes(pk)), DeletionTime.LIVE, md.regularAndStaticColumns(), Rows.EMPTY_STATIC_ROW, false, EncodingStats.NO_STATS);
            this.col = col; this.n = n; this.width = width; this.liveEvery = liveEvery; this.total = total;
        }
        protected Unfiltered computeNext()
        {
            if (i >= n) return endOfData();
            int k = i++; pulled++; if (total != null) total[0]++;
            return mkRow(col, k, width, liveEvery);
        }
    }

    static class PSrc extends AbstractUnfilteredPartitionIterator
    {
        final TableMetadata md; final ColumnMetadata col; final int parts, rows, width; int next = 0; int started = 0; final long[] pulled = new long[1];
        PSrc(TableMetadata md, ColumnMetadata col, int parts, int rows, int width) { this.md = md; this.col = col; this.parts = parts; this.rows = rows; this.width = width; }
        public TableMetadata metadata() { return md; }
        public boolean hasNext() { return next < parts; }
        public UnfilteredRowIterator next() { started++; return new Src(md, col, next++, rows, width, 0, pulled); }
    }

    static long used()
    {
        try { for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(100); } } catch (InterruptedException e) { throw new RuntimeException(e); }
        Runtime r = Runtime.getRuntime(); return r.totalMemory() - r.freeMemory();
    }

    static long alloc()
    {
        return ((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId());
    }

    void kv(String k, Object v) { out.println(k + "=" + v); out.flush(); }

    /** One drain, single partition: per-partition limit n (or -1 = NONE), width w. liveEvery 0 = all rows live. retain = keep the rows. */
    void point(String key, int n, int w, int liveEvery, boolean retain)
    {
        long base = retain ? used() : 0;
        try
        {
            Src src = new Src(md, col, 1, source, w, liveEvery, null);
            DataLimits limits = n < 0 ? DataLimits.NONE : DataLimits.cqlLimits(DataLimits.NO_LIMIT, n);
            DataLimits.Counter counter = null; UnfilteredRowIterator it;
            long a0 = alloc();
            if (n < 0) it = limits.filter(src, NOW, false);               // NONE: the identity, no counter at all
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
            long a1 = alloc();
            kv(key + ".rowsCounted", counter == null ? -1 : counter.rowsCounted());
            kv(key + ".inPart", counter == null ? -1 : counter.rowsCountedInCurrentPartition());
            kv(key + ".isDone", counter == null ? "na" : counter.isDone());
            kv(key + ".out", outRows); kv(key + ".outLive", outLive); kv(key + ".pulled", src.pulled); kv(key + ".alloc", a1 - a0);
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

    /** Many partitions: PARTS partitions of PART_ROWS rows, per-partition limit n (cqlLimits(NO_LIMIT, n)) or global limit g (cqlLimits(g)). */
    void many(String key, int perPartition, int global)
    {
        PSrc src = new PSrc(md, col, PARTS, PART_ROWS, 16);
        DataLimits limits = global > 0 ? DataLimits.cqlLimits(global) : DataLimits.cqlLimits(DataLimits.NO_LIMIT, perPartition);
        DataLimits.Counter counter = limits.newCounter(NOW, false, false, md.enforceStrictLiveness());
        long outRows = 0;
        try (UnfilteredPartitionIterator it = counter.applyTo(src))
        {
            while (it.hasNext())
                try (UnfilteredRowIterator p = it.next()) { while (p.hasNext()) { Unfiltered u = p.next(); if (u.isRow()) outRows++; } }
        }
        kv(key + ".out", outRows); kv(key + ".rowsCounted", counter.rowsCounted()); kv(key + ".started", src.started); kv(key + ".pulled", src.pulled[0]);
    }

    /** Positive control: NONE chain, the consumer stops at a running Row.unsharedHeapSize() sum of BYTE_STOP. */
    void control(String key, int w)
    {
        long base = used();
        Src src = new Src(md, col, 1, 100000, w, 0, null);   // 100,000 rows: a 16 B row (304 B) needs about 27,600 rows to reach BYTE_STOP
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
        source = Integer.parseInt(System.getenv().getOrDefault("STAGE4_SRC", "20000"));
        out = new PrintWriter(new java.io.FileWriter(dir + "/unit.txt"));
        createTable("CREATE TABLE %s (pk int, ck int, v blob, PRIMARY KEY (pk, ck))");
        md = getCurrentColumnFamilyStore().metadata();
        col = md.getColumn(ByteBufferUtil.bytes("v"));
        kv("SOURCE", source); kv("REPS", REPS);
        point("warm", 100, 16, 0, true);          // first trigger: n=100, w=16 must stop at 100 rows
        int[][] grid = {
            { 16, 1, 10, 100, 1000, 10000 },
            { 1024, 1, 10, 100, 1000, 10000 },
            { 65536, 1, 10, 100, 1000, 0 } };
        for (int rep = 1; rep <= REPS; rep++)
        {
            for (int[] g : grid)
                for (int j = 1; j < g.length; j++)
                {
                    if (g[j] == 0 || g[j] >= source) continue;
                    point("P.w" + g[0] + ".L" + g[j] + ".r" + rep, g[j], g[0], 0, true);
                }
            point("NONE.w16.r" + rep, -1, 16, 0, true);
            for (int n : new int[] { 1, 100, 1000 })
                if (10L * n < source) point("DEAD.w16.L" + n + ".r" + rep, n, 16, 10, false);
            for (int n : new int[] { 1, 10, 100 }) many("MANY.n" + n + ".r" + rep, n, 0);
            many("GLOBAL.g10.r" + rep, 0, 10);
            for (int w : WIDTHS) control("CTL.w" + w + ".r" + rep, w);
        }
        kv("done", 1);
        out.close();
    }
}
