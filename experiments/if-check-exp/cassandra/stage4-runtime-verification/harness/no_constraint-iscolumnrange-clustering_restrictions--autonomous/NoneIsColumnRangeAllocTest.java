/*
 * Stage-4 harness, unit tier, for no_constraint-iscolumnrange-clustering_restrictions--autonomous (B2 as amended 2026-10-29).
 * Written after the freeze of the case file (sha256 in the results file). Asserts only instrument and set-up errors; every
 * reading goes to $stage4.out/raw.csv and $stage4.out/proof.txt and is judged by analyze.py against the frozen prediction U1-U5.
 *
 * One partition pk=1 with N rows (ck1 = 0..N-1, ck2 = 7, v = 100 bytes); five arms that all return the one row (5, 7); controls C1
 * (whole partition) and C2 (LIMIT 10). Per (N, state, pass, arm): 3 warm-up calls, 7 timed calls of SelectStatement.executeLocally,
 * bytes allocated by the calling thread read with ThreadMXBean.getThreadAllocatedBytes.
 */
package org.apache.cassandra.cql3;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.List;

import org.junit.Assert;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.cql3.statements.SelectStatement;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.SinglePartitionReadQuery;
import org.apache.cassandra.db.ReadQuery;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.service.ClientState;
import org.apache.cassandra.service.QueryState;
import org.apache.cassandra.transport.messages.ResultMessage;
import org.apache.cassandra.utils.FBUtilities;

public class NoneIsColumnRangeAllocTest extends CQLTester
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

    static final String[][] ARMS = {
        { "F1", "SELECT ck1, ck2, v FROM %s WHERE pk=1 AND ck1 = 5 AND ck2 = 7", "false", "ClusteringIndexNamesFilter" },
        { "F2", "SELECT ck1, ck2, v FROM %s WHERE pk=1 AND ck1 IN (5) AND ck2 = 7", "false", "ClusteringIndexNamesFilter" },
        { "T1", "SELECT ck1, ck2, v FROM %s WHERE pk=1 AND ck1 = 5", "true", "ClusteringIndexSliceFilter" },
        { "T2", "SELECT ck1, ck2, v FROM %s WHERE pk=1 AND ck1 = 5 AND ck2 >= 7 AND ck2 <= 7", "true", "ClusteringIndexSliceFilter" },
        { "T3", "SELECT ck1, ck2, v FROM %s WHERE pk=1 AND ck1 = 5 AND ck2 >= 7", "true", "ClusteringIndexSliceFilter" },
        { "C1", "SELECT v FROM %s WHERE pk=1", null, null },
        { "C2", "SELECT v FROM %s WHERE pk=1 LIMIT 10", null, null },
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
        String dir = System.getProperty("stage4.out", "build/test/stage4-iscolumnrange");
        new java.io.File(dir).mkdirs();
        csv = new PrintWriter(new FileWriter(dir + "/raw.csv", true), true);
        proof = new PrintWriter(new FileWriter(dir + "/proof.txt", true), true);
        proof.println("INFO read-size guardrails after relax: coordinatorFail=" + DatabaseDescriptor.getCoordinatorReadSizeFailThreshold() + " localFail=" + DatabaseDescriptor.getLocalReadSizeFailThreshold() + " rowIndexFail=" + DatabaseDescriptor.getRowIndexReadSizeFailThreshold());
        csv.println("pass,state,N,arm,rep,alloc,rows");

        // instrument known-answer check
        long a = now(); byte[] b = new byte[8 * 1024 * 1024]; long got = now() - a;
        proof.println("CHECK alloc-known-answer expected=[8388608,8454144] actual=" + got + " len=" + b.length
                      + (got >= 8388608 && got <= 8454144 ? " ok" : " MISMATCH"));
        Assert.assertTrue("alloc known answer", got >= 8388608 && got <= 8454144);

        for (int n : SIZES)
        {
            createTable("CREATE TABLE %s (pk int, ck1 int, ck2 int, v blob, PRIMARY KEY (pk, ck1, ck2))");
            byte[] val = new byte[100];
            new java.util.Random(n).nextBytes(val);
            for (int i = 0; i < n; i++)
                execute("INSERT INTO %s (pk, ck1, ck2, v) VALUES (1, ?, 7, ?)", i, ByteBuffer.wrap(val));
            ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
            String tbl = KEYSPACE + "." + currentTable();
            SelectStatement[] st = new SelectStatement[ARMS.length];
            for (int k = 0; k < ARMS.length; k++)
                st[k] = (SelectStatement) QueryProcessor.getStatement(ARMS[k][1].replace("%s", tbl), ClientState.forInternalCalls());

            for (String state : new String[]{ "memtable", "sstable" })
            {
                if (state.equals("sstable")) flush();
                int ss = cfs.getLiveSSTables().size();
                boolean memEmpty = cfs.getTracker().getView().getCurrentMemtable().isClean();
                proof.println("STATE n=" + n + " state=" + state + " sstables=" + ss + " memtableEmpty=" + memEmpty);
                Assert.assertEquals(state.equals("memtable") ? 0 : 1, ss);
                for (String pass : new String[]{ "A", "B" })
                {
                    for (int k = 0; k < ARMS.length; k++)
                    {
                        String arm = ARMS[k][0];
                        mark("cell pass=" + pass + " state=" + state + " n=" + n + " arm=" + arm);
                        for (int r = 0; r < WARM + REPS; r++)
                        {
                            long t0 = now();
                            ResultMessage.Rows rows = st[k].executeLocally(QueryState.forInternalCalls(), OPTS);
                            long t1 = now();
                            int nrows = rows.result.size();
                            if (r < WARM) continue;
                            csv.println(pass + "," + state + "," + n + "," + arm + "," + (r - WARM) + "," + (t1 - t0) + "," + nrows);
                            if (r == WARM) proofLine(st[k], ARMS[k], rows, n, state, pass);
                        }
                    }
                }
            }
            dropTable("DROP TABLE %s");
        }
    }

    void proofLine(SelectStatement st, String[] arm, ResultMessage.Rows rows, int n, String state, String pass)
    {
        String icr = "-", filter = "-";
        if (arm[2] != null)
        {
            boolean cr = st.getRestrictions().isColumnRange();
            ReadQuery q = st.getQuery(OPTS, FBUtilities.nowInSeconds());
            filter = ((SinglePartitionReadQuery.Group<?>) q).queries.get(0).clusteringIndexFilter().getClass().getSimpleName();
            icr = String.valueOf(cr);
        }
        List<ByteBuffer> r0 = rows.result.rows.get(0);
        String vals = arm[2] == null ? "-" : Int32Type.instance.compose(r0.get(0)) + "/" + Int32Type.instance.compose(r0.get(1));
        proof.println("PROOF pass=" + pass + " state=" + state + " n=" + n + " arm=" + arm[0] + " isColumnRange=" + icr
                      + " expect=" + arm[2] + " filter=" + filter + " expectFilter=" + arm[3] + " rows=" + rows.result.size() + " ck1/ck2=" + vals);
    }
}
