/*
 * Stage-4 harness, unit tier, for no_constraint-doesaggregation-aggregatefactories--autonomous (B2 as amended 2026-10-29).
 * Written after the freeze of the case file (sha256 in the results file). Asserts only instrument and set-up errors; every reading
 * goes to $stage4.out/raw.csv and proof.txt and is judged by analyze.py against the frozen prediction V1-V5.
 *
 * One partition pk=1 with N rows (ck = v = 0..N-1), memtable only. Arms P (plain), P2 (abs(v): processing, no aggregate), A1 (max), A2 (max, min) and control C (P with
 * LIMIT 100). Per (N, pass, arm): 3 warm-up calls, 7 timed calls of SelectStatement.executeLocally; bytes allocated by the calling
 * thread (ThreadMXBean.getThreadAllocatedBytes), result row count, and the retained size of the result rows after the call (compactDeep; the
 * raw ObjectSizes.measureDeep(resultSet.rows) is kept in column retained_ref).
 */
package org.apache.cassandra.cql3;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.util.List;

import org.junit.Assert;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.cql3.selection.Selection;
import org.apache.cassandra.cql3.statements.SelectStatement;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.service.ClientState;
import org.apache.cassandra.service.QueryState;
import org.apache.cassandra.transport.messages.ResultMessage;
import org.apache.cassandra.utils.ObjectSizes;

public class NoneDoesAggregationAllocTest extends CQLTester
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static final int WARM = Integer.getInteger("stage4.warm", 30), REPS = 7;   // 30 since defect 2 (was 3)
    static final int[] SIZES = parse(System.getProperty("stage4.sizes", "1000,10000,100000"));
    static PrintWriter csv, proof;
    static QueryOptions OPTS;

    static int[] parse(String s) { String[] p = s.split(","); int[] r = new int[p.length]; for (int i = 0; i < p.length; i++) r[i] = Integer.parseInt(p[i].trim()); return r; }
    static long now() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }
    /** Byteman marks this call in its trace (rules.btm); a no-op otherwise. */
    public static void mark(String s) { }

    /** Deep size of a compact copy of the result rows: every buffer is copied to an exact-size heap buffer, so that a buffer which is a view
     *  of a larger shared array (attempt 3 read a constant 1,048,576-byte structure in every arm through such a reference) counts only its own bytes. */
    static long compactDeep(List<List<java.nio.ByteBuffer>> rows)
    {
        List<List<java.nio.ByteBuffer>> c = new java.util.ArrayList<>(rows.size());
        for (List<java.nio.ByteBuffer> r : rows)
        {
            List<java.nio.ByteBuffer> cr = new java.util.ArrayList<>(r.size());
            for (java.nio.ByteBuffer b : r) cr.add(b == null ? null : (java.nio.ByteBuffer) java.nio.ByteBuffer.allocate(b.remaining()).put(b.duplicate()).flip());
            c.add(cr);
        }
        return ObjectSizes.measureDeep(c);
    }

    // arm, cql, expected isAggregate
    static final String[][] ARMS = {
        { "P",  "SELECT v FROM %s WHERE pk=1", "false" },
        { "P2", "SELECT abs(v) FROM %s WHERE pk=1", "false" },
        { "A1", "SELECT max(v) FROM %s WHERE pk=1", "true" },
        { "A2", "SELECT max(v), min(v) FROM %s WHERE pk=1", "true" },
        { "C",  "SELECT v FROM %s WHERE pk=1 LIMIT 100", "false" },
    };

    /** test/conf/cassandra.yaml sets read-size guardrails (coordinator fail 4096KiB, local fail 8192KiB, row index fail 8192KiB) that a default node does not have;
     *  they abort the large reads of the controls and of the scans. Set to null for this run (runbook defect 1, results section 3). */
    static Runnable relaxReadGuardrails()
    {
        DataStorageSpec.LongBytesBound cw = DatabaseDescriptor.getCoordinatorReadSizeWarnThreshold(), cf = DatabaseDescriptor.getCoordinatorReadSizeFailThreshold(),
                                       lw = DatabaseDescriptor.getLocalReadSizeWarnThreshold(), lf = DatabaseDescriptor.getLocalReadSizeFailThreshold(),
                                       rw = DatabaseDescriptor.getRowIndexReadSizeWarnThreshold(), rf = DatabaseDescriptor.getRowIndexReadSizeFailThreshold();
        DatabaseDescriptor.setCoordinatorReadSizeWarnThreshold(null); DatabaseDescriptor.setCoordinatorReadSizeFailThreshold(null);
        DatabaseDescriptor.setLocalReadSizeWarnThreshold(null); DatabaseDescriptor.setLocalReadSizeFailThreshold(null);
        DatabaseDescriptor.setRowIndexReadSizeWarnThreshold(null); DatabaseDescriptor.setRowIndexReadSizeFailThreshold(null);
        return () -> {
            DatabaseDescriptor.setCoordinatorReadSizeWarnThreshold(cw); DatabaseDescriptor.setCoordinatorReadSizeFailThreshold(cf);
            DatabaseDescriptor.setLocalReadSizeWarnThreshold(lw); DatabaseDescriptor.setLocalReadSizeFailThreshold(lf);
            DatabaseDescriptor.setRowIndexReadSizeWarnThreshold(rw); DatabaseDescriptor.setRowIndexReadSizeFailThreshold(rf);
        };
    }

    @Test
    public void run() throws Throwable
    {
        Runnable restore = relaxReadGuardrails();
        // QueryOptions caches the coordinator read-size thresholds at construction (QueryOptions.java:346), so QueryOptions.DEFAULT (built at class load) would still abort.
        OPTS = QueryOptions.forInternalCalls(org.apache.cassandra.db.ConsistencyLevel.ONE, java.util.Collections.emptyList());
        try { body(); } finally { restore.run(); }
    }

    void body() throws Throwable
    {
        String dir = System.getProperty("stage4.out", "build/test/stage4-doesaggregation");
        new java.io.File(dir).mkdirs();
        csv = new PrintWriter(new FileWriter(dir + "/raw.csv", true), true);
        proof = new PrintWriter(new FileWriter(dir + "/proof.txt", true), true);
        proof.println("INFO read-size guardrails after relax: coordinatorFail=" + DatabaseDescriptor.getCoordinatorReadSizeFailThreshold() + " localFail=" + DatabaseDescriptor.getLocalReadSizeFailThreshold() + " rowIndexFail=" + DatabaseDescriptor.getRowIndexReadSizeFailThreshold());
        csv.println("pass,N,arm,rep,alloc,rows,retained,retained_ref");

        long a = now(); byte[] b = new byte[8 * 1024 * 1024]; long got = now() - a;
        long deep = ObjectSizes.measureDeep(new byte[1_000_000]);
        proof.println("CHECK alloc-known-answer expected=[8388608,8454144] actual=" + got + " len=" + b.length
                      + (got >= 8388608 && got <= 8454144 ? " ok" : " MISMATCH"));
        proof.println("CHECK measureDeep-known-answer expected=[1000016,1000064] actual=" + deep
                      + (deep >= 1000016 && deep <= 1000064 ? " ok" : " MISMATCH"));
        Assert.assertTrue("alloc known answer", got >= 8388608 && got <= 8454144);
        Assert.assertTrue("measureDeep known answer", deep >= 1000016 && deep <= 1000064);

        Field selField = SelectStatement.class.getDeclaredField("selection");
        selField.setAccessible(true);

        for (int n : SIZES)
        {
            createTable("CREATE TABLE %s (pk int, ck int, v int, PRIMARY KEY (pk, ck))");
            for (int i = 0; i < n; i++)
                execute("INSERT INTO %s (pk, ck, v) VALUES (1, ?, ?)", i, i);
            ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
            proof.println("STATE n=" + n + " sstables=" + cfs.getLiveSSTables().size());
            Assert.assertEquals(0, cfs.getLiveSSTables().size());
            String tbl = KEYSPACE + "." + currentTable();
            SelectStatement[] st = new SelectStatement[ARMS.length];
            for (int k = 0; k < ARMS.length; k++)
            {
                mark("prep n=" + n + " arm=" + ARMS[k][0]);
                st[k] = (SelectStatement) QueryProcessor.getStatement(ARMS[k][1].replace("%s", tbl), ClientState.forInternalCalls());
            }

            for (String pass : new String[]{ "A", "B" })
            {
                for (int k = 0; k < ARMS.length; k++)
                {
                    String arm = ARMS[k][0];
                    mark("cell pass=" + pass + " n=" + n + " arm=" + arm);
                    for (int r = 0; r < WARM + REPS; r++)
                    {
                        long t0 = now();
                        ResultMessage.Rows rows = st[k].executeLocally(QueryState.forInternalCalls(), OPTS);
                        long t1 = now();
                        int nrows = rows.result.size();
                        if (r < WARM) continue;
                        long ret = compactDeep(rows.result.rows);              // defect 3: size of a compact copy of the rows
                        long ref = ObjectSizes.measureDeep(rows.result.rows);  // attempt-3 definition, kept for transparency
                        csv.println(pass + "," + n + "," + arm + "," + (r - WARM) + "," + (t1 - t0) + "," + nrows + "," + ret + "," + ref);
                        if (r == WARM)
                        {
                            boolean agg = ((Selection) selField.get(st[k])).isAggregate();
                            List<java.nio.ByteBuffer> r0 = rows.result.rows.get(0);
                            StringBuilder vals = new StringBuilder();
                            for (java.nio.ByteBuffer v : r0) vals.append(v == null ? "null" : String.valueOf(Int32Type.instance.compose(v))).append('/');
                            proof.println("PROOF pass=" + pass + " n=" + n + " arm=" + arm + " isAggregate=" + agg + " expect=" + ARMS[k][2]
                                          + " rows=" + nrows + " firstRow=" + vals);
                        }
                    }
                }
            }
            dropTable("DROP TABLE %s");
        }
    }
}
