/*
 * Stage-4 unit tier for no_constraint-isempty-size--autonomous (case file B2 as amended 2026-10-29).
 * CQLTester (in-process node), table t(pk int, ck int, v int, PRIMARY KEY (pk, ck)), one partition pk = 1 holding N rows.
 * Arm A: SELECT count(*) FROM t WHERE pk = 1   (aggregate: GroupMaker.GROUP_EVERYTHING, returnAtLeastOneRow() true)
 * Arm B: SELECT v FROM t WHERE pk = 1          (plain)
 * The guarded call is ResultSetBuilder.build() (ResultSetBuilder.java:157-171): rules-alloc.btm brackets it with stage4.Alloc
 * (boot class path), the test writes a "mark" line before each repeat so the analysis can attribute the build lines; the test also
 * reads the calling thread's total allocation around the whole query (second observable). Mode "count" uses rules-count.btm
 * (traces ResultSet.isEmpty() return values, no Alloc) so the Alloc run carries no tracing of its own inside the window.
 * Observation only: asserts the instrument known-answer check only.
 */
package org.apache.cassandra.cql3;

import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.util.Arrays;

import org.junit.Assert;
import org.junit.Test;

public class ResultSetIsEmptyTest extends CQLTester
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static final int WARM = 3, REPS = 7;
    static PrintWriter raw;
    static volatile Object sink;

    static long now() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    void arm(String block, String arm, String table, int n, String query) throws Throwable
    {
        for (int rep = -WARM; rep < REPS; rep++)
        {
            stage4.Alloc.line("mark", "block=" + block + " arm=" + arm + " n=" + n + " rep=" + rep);
            long a0 = now();
            UntypedResultSet r = execute(String.format(query, table));
            long a1 = now();
            sink = r;
            if (rep >= 0)
                raw.println(String.join(",", block, arm, "" + n, "" + rep, "" + (a1 - a0), "" + r.size()));
        }
    }

    @Test
    public void run() throws Throwable
    {
        raw = new PrintWriter(new java.io.FileWriter(System.getProperty("stage4.out", ".") + "/raw.csv", true), true);
        raw.println("block,arm,n,rep,query_bytes,result_rows");
        stage4.Alloc.start("chk");
        byte[] b = new byte[8 << 20];
        stage4.Alloc.end("chk", "len=" + b.length);
        sink = b;
        long k0 = now(); byte[] big = new byte[8 << 20]; long k1 = now(); sink = big;
        boolean ok = (k1 - k0) >= (8 << 20) && (k1 - k0) <= (8 << 20) + 65536;
        System.out.println("STAGE4 check alloc-known-answer expected=[8388608,8454144] actual=" + (k1 - k0) + (ok ? " ok" : " MISMATCH"));
        Assert.assertTrue("known-answer", ok);
        if (System.getProperty("stage4.checkonly") != null)
            return;
        int[] ns = { 0, 1, 1000, 20000 };
        String[] tables = new String[ns.length];
        for (int i = 0; i < ns.length; i++)
        {
            tables[i] = createTable("CREATE TABLE %s (pk int, ck int, v int, PRIMARY KEY (pk, ck))");
            for (int c = 0; c < ns[i]; c++)
                execute("INSERT INTO " + KEYSPACE + "." + tables[i] + " (pk, ck, v) VALUES (1, ?, ?)", c, c);
        }
        String qa = "SELECT count(*) FROM " + KEYSPACE + ".%s WHERE pk = 1", qb = "SELECT v FROM " + KEYSPACE + ".%s WHERE pk = 1";
        arm("noise1", "A", tables[0], 0, qa);
        for (int i = 0; i < ns.length; i++)
        {
            arm("main", "A", tables[i], ns[i], qa);
            arm("main", "B", tables[i], ns[i], qb);
        }
        arm("noise2", "A", tables[0], 0, qa);
        stage4.Alloc.line("mark", "block=end arm=- n=-1 rep=-1"); // closes the last query's attribution window (teardown also runs build())
        System.out.println("STAGE4 done");
    }
}
