/*
 * Stage 4, unit tier (B2) of max-unsigned-short-prepare-boundTerms--autonomous. Not upstream.
 * Copy into test/unit/org/apache/cassandra/cql3/ of a copy-source.sh tree and run, one JVM per cache size (unit-run.sh):
 *   ant testsome -Dtest.name=org.apache.cassandra.cql3.PrepareMarkerLimitTest \
 *     -Dtest.jvm.args="-Dcassandra.config=file://<yaml copy> -Dstage4.out=<file> -Dstage4.label=<l>"
 * Statements: SELECT * FROM ks.t WHERE k IN (?, ..., ?) with M markers, fully qualified, ClientState without keyspace (one cache entry per PREPARE).
 */
package org.apache.cassandra.cql3;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Map;

import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.exceptions.InvalidRequestException;
import org.apache.cassandra.service.ClientState;
import org.apache.cassandra.utils.MD5Digest;
import org.apache.cassandra.utils.ObjectSizes;

public class PrepareMarkerLimitTest extends CQLTester
{
    static PrintWriter out;
    int mismatches = 0;
    long cap;
    ClientState cs;
    String label;

    static synchronized void line(String s)
    {
        System.out.println(s);
        try
        {
            if (out == null && System.getProperty("stage4.out") != null)
                out = new PrintWriter(new FileWriter(System.getProperty("stage4.out"), true), true);
        }
        catch (java.io.IOException e)
        {
            throw new RuntimeException(e);
        }
        if (out != null)
            out.println(s);
    }

    void check(String name, boolean ok, String detail)
    {
        if (!ok)
            mismatches++;
        line("STAGE4 check " + label + " " + name + " " + detail + (ok ? " OK" : " MISMATCH"));
    }

    static long usedAfterGc() throws InterruptedException
    {
        for (int i = 0; i < 2; i++)
        {
            System.gc();
            Thread.sleep(300);
        }
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    static long sumWeights()
    {
        long sum = 0;
        for (Map.Entry<MD5Digest, QueryHandler.Prepared> e : QueryProcessor.instance.getPreparedStatements().entrySet())
            sum += e.getKey().size() + e.getValue().pstmntSize;
        return sum;
    }

    String q(int m, String tag)
    {
        StringBuilder sb = new StringBuilder(m * 3 + 120);
        sb.append("SELECT * FROM ").append(KEYSPACE).append('.').append(currentTable()).append(" WHERE k IN (");
        for (int i = 0; i < m; i++)
            sb.append(i == 0 ? "?" : ", ?");
        return sb.append(") /* ").append(tag).append(" */").toString();
    }

    /** null when accepted, else the exception message */
    String tryPrepare(String query)
    {
        try
        {
            QueryProcessor.instance.prepare(query, cs);
            return null;
        }
        catch (InvalidRequestException e)
        {
            return e.getMessage();
        }
        catch (Throwable t)
        {
            return "OTHER " + t;
        }
    }

    static String head(String s)
    {
        return s == null ? "ACCEPTED" : s.substring(0, Math.min(s.length(), 100)).replace('\n', ' ');
    }

    /** weight and bind count of the single cached entry, or -1 */
    long[] onlyEntry()
    {
        for (Map.Entry<MD5Digest, QueryHandler.Prepared> e : QueryProcessor.instance.getPreparedStatements().entrySet())
            return new long[]{ e.getKey().size() + e.getValue().pstmntSize, e.getValue().statement.getBindVariables().size() };
        return new long[]{ -1, -1 };
    }

    @Test
    public void run() throws Throwable
    {
        label = System.getProperty("stage4.label", "x");
        long mib = DatabaseDescriptor.getPreparedStatementsCacheSizeMiB();
        cap = mib * 1024 * 1024;
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v int)");
        cs = ClientState.forInternalCalls();
        line("STAGE4 run label=" + label + " cap_mib=" + mib + " cap_bytes=" + cap + " maxMemory=" + Runtime.getRuntime().maxMemory()
             + " keyspace_in_clientstate=" + cs.getRawKeyspace());

        // ---- calibration and boundary (cap-independent statements)
        long[] w = new long[4];
        int[] ms = { 1, 10, 1000, 65535 };
        String[] calMsg = new String[4];
        for (int j = 0; j < ms.length; j++)
        {
            QueryProcessor.clearPreparedStatementsCache();
            String msg = tryPrepare(q(ms[j], "cal"));
            long[] e = onlyEntry();
            w[j] = msg == null ? e[0] : -1;
            calMsg[j] = msg;
            line("STAGE4 cal label=" + label + " M=" + ms[j] + " result=" + head(msg) + " weight=" + w[j] + " bind_variables=" + e[1]
                 + " count=" + QueryProcessor.preparedStatementsCount());
            check("cal-M" + ms[j], msg == null ? (e[1] == ms[j] && e[0] <= cap) : msg.startsWith("Prepared statement of size"),
                  "accepted=" + (msg == null) + " bind=" + e[1] + " weight=" + e[0] + " cap=" + cap + " msg=" + head(msg));
        }
        QueryProcessor.clearPreparedStatementsCache();
        int c0 = QueryProcessor.preparedStatementsCount();
        String m65536 = tryPrepare(q(65536, "b"));
        String expect = "Too many markers(?). 65536 markers exceed the allowed maximum of 65535";
        line("STAGE4 boundary label=" + label + " M=65536 result=" + head(m65536) + " count_before=" + c0 + " count_after=" + QueryProcessor.preparedStatementsCount());
        check("boundary-65536-rejected", m65536 != null && m65536.equals(expect) && QueryProcessor.preparedStatementsCount() == c0, "msg=" + head(m65536));

        // ---- load loops
        int[] loopM = { 10, 1000, 65535 };
        int[] limit = { 200000, 20000, 400 };
        for (int j = 0; j < loopM.length; j++)
        {
            int m = loopM[j];
            long wm = w[j + 1];
            QueryProcessor.clearPreparedStatementsCache();
            long h0 = usedAfterGc();
            long ev0 = QueryProcessor.metrics.preparedStatementsEvicted.getCount();
            int offered = 0, rejected = 0, consecutive = 0;
            String firstReject = null;
            if (wm < 0)
            {
                // heavier than the cap: five attempts, all must hit the size gate
                for (int i = 0; i < 5; i++)
                {
                    offered++;
                    String msg = tryPrepare(q(m, "g" + i));
                    if (msg != null) { rejected++; firstReject = firstReject == null ? msg : firstReject; }
                }
            }
            else
            {
                int n = (int) Math.max(10, Math.min(limit[j], (4 * cap + wm - 1) / wm));
                for (int i = 0; i < n; i++)
                {
                    offered++;
                    String msg = tryPrepare(q(m, "u" + i));
                    if (msg != null) { rejected++; firstReject = firstReject == null ? msg : firstReject; }
                    if ((i + 1) % 2000 == 0)
                        line("STAGE4 progress label=" + label + " M=" + m + " i=" + (i + 1) + " count=" + QueryProcessor.preparedStatementsCount()
                             + " sumWeights=" + sumWeights());
                }
            }
            long sum = sumWeights();
            int count = QueryProcessor.preparedStatementsCount();
            long evicted = QueryProcessor.metrics.preparedStatementsEvicted.getCount() - ev0;
            long deep = sum <= 20L * 1024 * 1024 ? ObjectSizes.measureDeep(QueryProcessor.instance.getPreparedStatements()) : -1;
            long h1 = usedAfterGc();
            long rows = execute("SELECT count(*) FROM system.prepared_statements").one().getLong("count");
            line("STAGE4 final label=" + label + " M=" + m + " cap=" + cap + " w=" + wm + " offered=" + offered + " rejected=" + rejected + " sumWeights=" + sum
                 + " count=" + count + " evicted=" + evicted + " systemRows=" + rows + " measureDeepMap=" + deep + " liveHeapBaseline=" + h0
                 + " liveHeapFull=" + h1 + " liveDelta=" + (h1 - h0) + " firstReject=" + head(firstReject));
            check("M" + m + "-sum<=cap", sum <= cap, "sum=" + sum + " cap=" + cap);
            if (wm < 0)
                check("M" + m + "-size-gate", rejected == offered && count == 0 && firstReject.startsWith("Prepared statement of size"),
                      "offered=" + offered + " rejected=" + rejected + " count=" + count);
            else
            {
                check("M" + m + "-all-accepted", rejected == 0, "rejected=" + rejected);
                boolean expectEvict = (long) offered * wm > cap + wm;
                check("M" + m + "-evictions", expectEvict ? evicted > 0 : true, "evicted=" + evicted + " expected_evictions=" + expectEvict + " offered_weight=" + (long) offered * wm);
                check("M" + m + "-count+evicted==offered", count + evicted == offered, "count=" + count + " evicted=" + evicted + " offered=" + offered);
            }
        }
        line("STAGE4 done label=" + label + " mismatches=" + mismatches);
    }
}
