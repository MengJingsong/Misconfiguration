package org.apache.cassandra.db;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;

import org.junit.Test;

import org.apache.cassandra.Util;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.db.aggregation.AggregationSpecification;
import org.apache.cassandra.db.filter.DataLimits;
import org.apache.cassandra.db.partitions.UnfilteredPartitionIterator;
import org.apache.cassandra.db.rows.Row;
import org.apache.cassandra.db.rows.Unfiltered;
import org.apache.cassandra.db.rows.UnfilteredRowIterator;
import org.apache.cassandra.db.transform.Transformation;
import org.apache.cassandra.utils.FBUtilities;

/**
 * Stage-4 harness, unit tier (B2) of group-per-partition-limit-incrementGroupInCurrentPartitionCount-groupPerPartitionLimit--autonomous.
 * Shape A: table ta, 20 partitions x 1000 clusterings, grouped by the clustering column (prefix 1): 1000 one-row groups per partition.
 * Shape B: table tb, 4 partitions x 100000 rows, grouped by the partition key only (prefix 0): one group per partition.
 * Each is read with a PartitionRangeReadCommand and passed through DataLimits.groupByLimits(NO_LIMIT, gppl, rowLimit, spec).newCounter(...).applyTo(partitions).
 * Writes "key=value" lines to $STAGE4_OUT/unit.txt; analyze_unit.py makes the verdict.
 * Env STAGE4_B_ROWS overrides the shape-B rows per partition (default 100000; shakedown only), STAGE4_REPS (default 5).
 */
public class GroupPerPartitionLimitProbeTest extends CQLTester
{
    static PrintWriter out;
    static final String V100 = "x".repeat(100);
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static final int A_PARTS = 20, A_ROWS = 1000, B_PARTS = 4;

    static void rec(String s) { out.println(s); out.flush(); System.out.println("STAGE4 " + s); }

    /** counts rows (and partitions) requested from the source: sits UNDER the limit counter */
    static class Pulled extends Transformation<UnfilteredRowIterator>
    {
        long rows, parts;
        final Transformation<UnfilteredRowIterator> rowCounter = new Transformation<UnfilteredRowIterator>()
        {
            @Override public Row applyToRow(Row row) { rows++; return row; }
        };
        @Override protected UnfilteredRowIterator applyToPartition(UnfilteredRowIterator partition)
        {
            parts++;
            return Transformation.apply(partition, rowCounter);
        }
    }

    @Test
    public void all() throws Throwable
    {
        String dir = System.getenv().getOrDefault("STAGE4_OUT", "/tmp");
        int bRows = Integer.parseInt(System.getenv().getOrDefault("STAGE4_B_ROWS", "100000"));
        int reps = Integer.parseInt(System.getenv().getOrDefault("STAGE4_REPS", "5"));
        out = new PrintWriter(new FileWriter(dir + "/unit.txt", false));
        try
        {
            rec("A_PARTS=" + A_PARTS); rec("A_ROWS=" + A_ROWS); rec("B_PARTS=" + B_PARTS); rec("B_ROWS=" + bRows); rec("reps=" + reps);
            rec("maxMemory=" + Runtime.getRuntime().maxMemory());
            String ta = createTable("CREATE TABLE %s (k int, ck int, v blob, PRIMARY KEY (k, ck))");
            java.nio.ByteBuffer v = java.nio.ByteBuffer.wrap(V100.getBytes());
            for (int k = 0; k < A_PARTS; k++)
                for (int c = 0; c < A_ROWS; c++)
                    execute("INSERT INTO %s (k, ck, v) VALUES (?, ?, ?)", k, c, v);
            ColumnFamilyStore cfsA = getCurrentColumnFamilyStore();
            String tb = createTable("CREATE TABLE %s (k int, ck int, v blob, PRIMARY KEY (k, ck))");
            for (int k = 0; k < B_PARTS; k++)
                for (int c = 0; c < bRows; c++)
                    execute("INSERT INTO %s (k, ck, v) VALUES (?, ?, ?)", k, c, v);
            ColumnFamilyStore cfsB = getCurrentColumnFamilyStore();
            rec("rows_A=" + execute("SELECT count(*) FROM " + KEYSPACE + "." + ta).one().getLong("count"));
            rec("rows_B=" + execute("SELECT count(*) FROM " + KEYSPACE + "." + tb).one().getLong("count"));
            // first trigger: shape A, gppl=10, rowLimit=NO_LIMIT must return 200 rows and pull fewer than 1000 rows; otherwise nothing else runs
            long[] t = one(cfsA, "A", 1, 10, DataLimits.NO_LIMIT);
            if (!(t[0] == A_PARTS * 10 && t[1] < 1000))
            {
                rec("firsttrigger=FAIL returned=" + t[0] + " pulled=" + t[1]);
                return;
            }
            rec("firsttrigger=OK returned=" + t[0] + " pulled=" + t[1]);
            int[] gs = { 1, 10, DataLimits.NO_LIMIT };
            int[] rls = { 100, 10000, DataLimits.NO_LIMIT };
            // warm-up passes (not recorded as readings): one of each shape
            one(cfsA, "A", 1, DataLimits.NO_LIMIT, DataLimits.NO_LIMIT); one(cfsB, "B", 0, DataLimits.NO_LIMIT, DataLimits.NO_LIMIT);
            for (int rep = 0; rep < reps; rep++)
                for (int rl : rls)
                    for (int g : gs)
                    {
                        one(cfsA, "A", 1, g, rl);
                        one(cfsB, "B", 0, g, rl);
                    }
            rec("done=1");
        }
        finally
        {
            out.close();
        }
    }

    /** returns {rows returned, rows pulled}; logs one line */
    long[] one(ColumnFamilyStore cfs, String shape, int prefix, int gppl, int rowLimit) throws Throwable
    {
        AggregationSpecification spec = AggregationSpecification.aggregatePkPrefixFactory(cfs.metadata().comparator, prefix).newInstance(QueryOptions.DEFAULT);
        DataLimits limits = DataLimits.groupByLimits(DataLimits.NO_LIMIT, gppl, rowLimit, spec);
        ReadCommand cmd = Util.cmd(cfs).build();
        System.gc();
        long tid = Thread.currentThread().getId();
        long a0 = TMX.getThreadAllocatedBytes(tid);
        long returned = 0; int counted, cip, cipBefore, rowsCounted; Pulled pulled = new Pulled();
        try (ReadExecutionController ec = cmd.executionController())
        {
            UnfilteredPartitionIterator pi = cmd.executeLocally(ec);
            DataLimits.Counter counter = limits.newCounter(FBUtilities.nowInSeconds(), false, false, true);
            UnfilteredPartitionIterator it = counter.applyTo(Transformation.apply(pi, pulled));
            while (it.hasNext())
                try (UnfilteredRowIterator ri = it.next())
                {
                    while (ri.hasNext())
                    {
                        Unfiltered u = ri.next();
                        if (u.isRow()) returned++;
                    }
                }
            cipBefore = counter.countedInCurrentPartition();
            it.close();   // closes pi too; onClose: counts the open last group at the end of the data
            counted = counter.counted(); cip = counter.countedInCurrentPartition(); rowsCounted = counter.rowsCounted();
        }
        long a1 = TMX.getThreadAllocatedBytes(tid);
        rec(String.format("run shape=%s gppl=%s rowLimit=%s returned=%d pulled=%d parts=%d counted=%d cip_before_close=%d cip=%d rowsCounted=%d alloc=%d",
                          shape, gppl == DataLimits.NO_LIMIT ? "NO_LIMIT" : "" + gppl, rowLimit == DataLimits.NO_LIMIT ? "NO_LIMIT" : "" + rowLimit,
                          returned, pulled.rows, pulled.parts, counted, cipBefore, cip, rowsCounted, a1 - a0));
        return new long[]{ returned, pulled.rows };
    }
}
