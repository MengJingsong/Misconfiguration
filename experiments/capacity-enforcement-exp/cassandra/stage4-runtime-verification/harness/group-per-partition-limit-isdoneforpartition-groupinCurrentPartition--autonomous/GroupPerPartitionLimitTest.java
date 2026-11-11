package org.apache.cassandra.db;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;

import org.junit.Test;

import org.apache.cassandra.Util;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.db.aggregation.AggregationSpecification;
import org.apache.cassandra.db.filter.DataLimits;
import org.apache.cassandra.db.rows.Row;
import org.apache.cassandra.db.rows.Unfiltered;
import org.apache.cassandra.db.rows.UnfilteredRowIterator;
import org.apache.cassandra.db.transform.Transformation;
import org.apache.cassandra.utils.FBUtilities;
import org.apache.cassandra.utils.memory.HeapCloner;

/**
 * Stage-4 harness, unit tier (B2) of group-per-partition-limit-isdoneforpartition-groupinCurrentPartition--autonomous.
 * One partition of R rows (clustering ck, one group per row under GROUP BY k, ck) is read from the memtable and passed through
 * DataLimits.groupByLimits(NO_LIMIT, N, NO_LIMIT, spec).newCounter(...).applyTo(iterator). Writes "key=value" lines to $STAGE4_OUT/unit.txt.
 * The verdict is made by analyze_unit.py. Env STAGE4_ROWS overrides R (default 100000; shakedown only), STAGE4_REPS (default 5).
 */
public class GroupPerPartitionLimitTest extends CQLTester
{
    static PrintWriter out;
    static final String V100 = "x".repeat(100);
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

    static void rec(String s) { out.println(s); out.flush(); System.out.println("STAGE4 " + s); }

    static long usedAfterGc()
    {
        for (int i = 0; i < 3; i++) { System.gc(); try { Thread.sleep(50); } catch (InterruptedException e) {} }
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    /** counts rows requested from the source: applied BEFORE the limit counter, so it sits under it */
    static class Pulled extends Transformation<UnfilteredRowIterator>
    {
        long n;
        @Override public Row applyToRow(Row row) { n++; return row; }
    }

    @Test
    public void all() throws Throwable
    {
        String dir = System.getenv().getOrDefault("STAGE4_OUT", "/tmp");
        int R = Integer.parseInt(System.getenv().getOrDefault("STAGE4_ROWS", "100000"));
        int reps = Integer.parseInt(System.getenv().getOrDefault("STAGE4_REPS", "5"));
        out = new PrintWriter(new FileWriter(dir + "/unit.txt", false));
        try
        {
            rec("R=" + R); rec("reps=" + reps); rec("maxMemory=" + Runtime.getRuntime().maxMemory());
            createTable("CREATE TABLE %s (k int, ck int, v blob, PRIMARY KEY (k, ck))");
            String ins = "INSERT INTO %s (k, ck, v) VALUES (1, ?, ?)";
            java.nio.ByteBuffer v = java.nio.ByteBuffer.wrap(V100.getBytes());
            for (int i = 0; i < R; i++) execute(ins, i, v);
            ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
            rec("rows_in_memtable=" + execute("SELECT count(*) FROM %s WHERE k = 1").one().getLong("count"));
            // first trigger: N=10 must return exactly 10 groups and pull far fewer than R rows; otherwise nothing else runs
            long[] t = one(cfs, 10, false, R);
            if (!(t[0] == 10 && t[1] < R / 2))
            {
                rec("firsttrigger=FAIL groups=" + t[0] + " pulled=" + t[1]);
                return;
            }
            rec("firsttrigger=OK groups=" + t[0] + " pulled=" + t[1]);
            int[] ns = { 1, 10, 100, 1000, DataLimits.NO_LIMIT };
            // noise floor of the retained-heap reading: no query at all
            for (int rep = 0; rep < reps; rep++)
            {
                long a = usedAfterGc(), b = usedAfterGc();
                rec("noise rep=" + rep + " used_before=" + a + " used_after=" + b);
            }
            for (int pass = 0; pass < 2; pass++)   // pass 0: no retention; pass 1: positive control (rows cloned and kept)
                for (int n : ns)
                    for (int rep = 0; rep < reps; rep++)
                        one(cfs, n, pass == 1, R);
            rec("done=1");
        }
        finally
        {
            out.close();
        }
    }

    /** returns {groups returned, rows pulled} */
    long[] one(ColumnFamilyStore cfs, int n, boolean materialize, int R) throws Throwable
    {
        AggregationSpecification spec = AggregationSpecification.aggregatePkPrefixFactory(cfs.metadata().comparator, 1).newInstance(QueryOptions.DEFAULT);
        DataLimits limits = DataLimits.groupByLimits(DataLimits.NO_LIMIT, n, DataLimits.NO_LIMIT, spec);
        ReadCommand cmd = Util.cmd(cfs, 1).build();
        long before = usedAfterGc();
        long tid = Thread.currentThread().getId();
        long a0 = TMX.getThreadAllocatedBytes(tid);
        long groups = 0; int counted, countedInPartition, rowsCounted; Pulled pulled = new Pulled();
        List<Row> keep = materialize ? new ArrayList<>() : null;
        try (ReadExecutionController ec = cmd.executionController(); org.apache.cassandra.db.partitions.UnfilteredPartitionIterator pi = cmd.executeLocally(ec))
        {
            UnfilteredRowIterator ri = pi.next();
            UnfilteredRowIterator counted_ = Transformation.apply(ri, pulled);
            DataLimits.Counter counter = limits.newCounter(FBUtilities.nowInSeconds(), false, false, true);
            try (UnfilteredRowIterator it = counter.applyTo(counted_))
            {
                while (it.hasNext())
                {
                    Unfiltered u = it.next();
                    if (u.isRow()) { groups++; if (keep != null) keep.add(((Row) u).clone(HeapCloner.instance)); }
                }
            }
            counted = counter.counted(); countedInPartition = counter.countedInCurrentPartition(); rowsCounted = counter.rowsCounted();
        }
        long a1 = TMX.getThreadAllocatedBytes(tid);
        long after = usedAfterGc();   // the kept list (if any) is still reachable here
        rec(String.format("%s N=%s groups=%d pulled=%d counted=%d countedInPartition=%d rowsCounted=%d alloc=%d used_before=%d used_after=%d kept=%d",
                          materialize ? "ctl" : "run", n == DataLimits.NO_LIMIT ? "NO_LIMIT" : "" + n, groups, pulled.n, counted, countedInPartition, rowsCounted,
                          a1 - a0, before, after, keep == null ? 0 : keep.size()));
        return new long[]{ groups, pulled.n };
    }
}
