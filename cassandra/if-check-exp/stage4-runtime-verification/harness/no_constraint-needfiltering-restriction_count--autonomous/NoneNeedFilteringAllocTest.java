/*
 * Stage-4 harness, unit tier, for no_constraint-needfiltering-restriction_count--autonomous (B2 as amended 2026-10-29).
 * Written after the freeze of the case file (sha256 in the results file). Asserts only instrument and set-up errors; every reading
 * goes to $stage4.out/raw.csv and proof.txt and is judged by analyze.py against the frozen prediction W1-W5.
 *
 * N partitions (pk = ck = 0..N-1, v = 100 bytes), memtable only. Q = SELECT ck, v FROM t WHERE ck = 5.
 *   R  : Q without ALLOW FILTERING: getStatement(Q) throws at prepare (SelectStatement.java:1610); window = the call.
 *   F  : Q ALLOW FILTERING: window Fp = getStatement, window Fx = executeLocally.
 *   C1 : SELECT ck, v FROM t (all rows)    C2 : the same with LIMIT 10 (windows around executeLocally).
 * Per (N, pass, arm): 3 warm-up repetitions, 7 timed; bytes allocated by the calling thread (ThreadMXBean.getThreadAllocatedBytes).
 */
package org.apache.cassandra.cql3;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;

import org.junit.Assert;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.cql3.restrictions.StatementRestrictions;
import org.apache.cassandra.cql3.statements.SelectStatement;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.exceptions.InvalidRequestException;
import org.apache.cassandra.index.IndexRegistry;
import org.apache.cassandra.schema.Schema;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.service.ClientState;
import org.apache.cassandra.service.QueryState;
import org.apache.cassandra.transport.messages.ResultMessage;

public class NoneNeedFilteringAllocTest extends CQLTester
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
        String dir = System.getProperty("stage4.out", "build/test/stage4-needfiltering");
        new java.io.File(dir).mkdirs();
        csv = new PrintWriter(new FileWriter(dir + "/raw.csv", true), true);
        proof = new PrintWriter(new FileWriter(dir + "/proof.txt", true), true);
        proof.println("INFO read-size guardrails after relax: coordinatorFail=" + DatabaseDescriptor.getCoordinatorReadSizeFailThreshold() + " localFail=" + DatabaseDescriptor.getLocalReadSizeFailThreshold() + " rowIndexFail=" + DatabaseDescriptor.getRowIndexReadSizeFailThreshold());
        csv.println("pass,N,arm,rep,alloc,rows");

        long a = now(); byte[] b = new byte[8 * 1024 * 1024]; long got = now() - a;
        proof.println("CHECK alloc-known-answer expected=[8388608,8454144] actual=" + got + " len=" + b.length
                      + (got >= 8388608 && got <= 8454144 ? " ok" : " MISMATCH"));
        Assert.assertTrue("alloc known answer", got >= 8388608 && got <= 8454144);

        for (int n : SIZES)
        {
            createTable("CREATE TABLE %s (pk int, ck int, v blob, PRIMARY KEY (pk, ck))");
            byte[] val = new byte[100];
            new java.util.Random(n).nextBytes(val);
            for (int i = 0; i < n; i++)
                execute("INSERT INTO %s (pk, ck, v) VALUES (?, ?, ?)", i, i, ByteBuffer.wrap(val));
            ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
            proof.println("STATE n=" + n + " sstables=" + cfs.getLiveSSTables().size());
            Assert.assertEquals(0, cfs.getLiveSSTables().size());
            String tbl = KEYSPACE + "." + currentTable();
            String q = "SELECT ck, v FROM " + tbl + " WHERE ck = 5";
            SelectStatement c1 = (SelectStatement) QueryProcessor.getStatement("SELECT ck, v FROM " + tbl, ClientState.forInternalCalls());
            SelectStatement c2 = (SelectStatement) QueryProcessor.getStatement("SELECT ck, v FROM " + tbl + " LIMIT 10", ClientState.forInternalCalls());
            SelectStatement f0 = (SelectStatement) QueryProcessor.getStatement(q + " ALLOW FILTERING", ClientState.forInternalCalls());
            TableMetadata t = Schema.instance.getTableMetadata(f0.keyspace(), f0.table());

            for (String pass : new String[]{ "A", "B" })
            {
                // ---- arm R
                mark("cell pass=" + pass + " n=" + n + " arm=R");
                String firstMsg = null; String firstCls = null;
                for (int r = 0; r < WARM + REPS; r++)
                {
                    long t0 = now(); String cls = "none", msg = "";
                    try { QueryProcessor.getStatement(q, ClientState.forInternalCalls()); }
                    catch (Throwable e) { cls = e.getClass().getSimpleName(); msg = String.valueOf(e.getMessage()); }
                    long t1 = now();
                    if (r == WARM) { firstCls = cls; firstMsg = msg; }
                    if (r >= WARM) csv.println(pass + "," + n + ",R," + (r - WARM) + "," + (t1 - t0) + ",-1");
                }
                proof.println("PROOF pass=" + pass + " n=" + n + " arm=R class=" + firstCls + " rejectedWithFilteringMessage="
                              + (firstMsg != null && firstMsg.startsWith("Cannot execute this query as it might involve data filtering"))
                              + " msg=" + (firstMsg == null ? "" : firstMsg.substring(0, Math.min(90, firstMsg.length()))));

                // ---- arm F (Fp, Fx)
                mark("cell pass=" + pass + " n=" + n + " arm=F");
                for (int r = 0; r < WARM + REPS; r++)
                {
                    long t0 = now();
                    SelectStatement f = (SelectStatement) QueryProcessor.getStatement(q + " ALLOW FILTERING", ClientState.forInternalCalls());
                    long t1 = now();
                    ResultMessage.Rows rows = f.executeLocally(QueryState.forInternalCalls(), OPTS);
                    long t2 = now();
                    if (r < WARM) continue;
                    csv.println(pass + "," + n + ",Fp," + (r - WARM) + "," + (t1 - t0) + ",-1");
                    csv.println(pass + "," + n + ",Fx," + (r - WARM) + "," + (t2 - t1) + "," + rows.result.size());
                    if (r == WARM)
                    {
                        StatementRestrictions sr = f.getRestrictions();
                        Field fr = StatementRestrictions.class.getDeclaredField("filterRestrictions");
                        fr.setAccessible(true);
                        Object o = fr.get(sr);
                        boolean l985 = (Boolean) o.getClass().getMethod("needsFiltering", IndexRegistry.class).invoke(o, IndexRegistry.obtain(t));
                        proof.println("PROOF pass=" + pass + " n=" + n + " arm=F needFiltering=" + sr.needFiltering(t) + " keyRange=" + sr.isKeyRange()
                                      + " usesIndex=" + sr.usesSecondaryIndexing() + " line985=" + l985 + " rows=" + rows.result.size()
                                      + " ck=" + (rows.result.size() == 1 ? Int32Type.instance.compose(rows.result.rows.get(0).get(0)) : -1));
                    }
                }

                // ---- controls
                for (SelectStatement c : new SelectStatement[]{ c1, c2 })
                {
                    String arm = c == c1 ? "C1" : "C2";
                    mark("cell pass=" + pass + " n=" + n + " arm=" + arm);
                    for (int r = 0; r < WARM + REPS; r++)
                    {
                        long t0 = now();
                        ResultMessage.Rows rows = c.executeLocally(QueryState.forInternalCalls(), OPTS);
                        long t1 = now();
                        if (r >= WARM) csv.println(pass + "," + n + "," + arm + "," + (r - WARM) + "," + (t1 - t0) + "," + rows.result.size());
                    }
                }
            }
            dropTable("DROP TABLE %s");
        }
    }
}
