/*
 * Stage 4, unit tier (B2) of prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous. Not upstream.
 * Copy into test/unit/org/apache/cassandra/cql3/ of a clone at cassandra-5.0.9 and run, one JVM per knob value (unit-run.sh):
 *   ant testsome -Dtest.name=org.apache.cassandra.cql3.PreparedCacheCapTest \
 *     -Dtest.jvm.args="-Dcassandra.config=file://<yaml copy> -Dstage4.out=<file> -Dstage4.label=<l> [-Dstage4.n=<n>]"
 * Statements are fully qualified and ClientState has no keyspace: one cache entry per PREPARE (QueryProcessor.prepare, 760-779).
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

public class PreparedCacheCapTest extends CQLTester
{
    static PrintWriter out;
    int mismatches = 0;

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
        line("STAGE4 check " + name + " " + detail + (ok ? " OK" : " MISMATCH"));
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

    String q(String tag)
    {
        return "SELECT v FROM " + KEYSPACE + "." + currentTable() + " WHERE k = ? /* " + tag + " */";
    }

    @Test
    public void run() throws Throwable
    {
        String label = System.getProperty("stage4.label", "x");
        long mib = DatabaseDescriptor.getPreparedStatementsCacheSizeMiB();
        long cap = mib * 1024 * 1024;
        createTable("CREATE TABLE %s (k text PRIMARY KEY, v int)");
        ClientState cs = ClientState.forInternalCalls();
        line("STAGE4 run label=" + label + " cap_mib=" + mib + " cap_bytes=" + cap + " maxMemory=" + Runtime.getRuntime().maxMemory()
             + " keyspace_in_clientstate=" + cs.getRawKeyspace());

        // calibration: one statement
        QueryProcessor.instance.prepare(q("cal"), cs);
        QueryHandler.Prepared cal = QueryProcessor.instance.getPreparedStatements().values().iterator().next();
        long w0 = cal.pstmntSize + MD5Digest.compute("x").size();
        line("STAGE4 calibration pstmntSize=" + cal.pstmntSize + " weight=" + w0 + " entries_after_one_prepare=" + QueryProcessor.preparedStatementsCount());
        check(label + " one-entry-per-prepare", QueryProcessor.preparedStatementsCount() == 1, "count=" + QueryProcessor.preparedStatementsCount());
        QueryProcessor.clearPreparedStatementsCache();

        long h0 = usedAfterGc();
        long ev0 = QueryProcessor.metrics.preparedStatementsEvicted.getCount();
        int n = (int) Math.max(200, Math.min(200000, Long.getLong("stage4.n", 4 * cap / w0)));
        line("STAGE4 plan n=" + n + " offered_weight=" + (long) n * w0 + " (cap " + cap + ")");
        for (int i = 0; i < n; i++)
        {
            QueryProcessor.instance.prepare(q("u" + i), cs);
            if ((i + 1) % 50 == 0 || i + 1 == n)
                line("STAGE4 progress i=" + (i + 1) + " sumWeights=" + sumWeights() + " count=" + QueryProcessor.preparedStatementsCount()
                     + " evicted=" + (QueryProcessor.metrics.preparedStatementsEvicted.getCount() - ev0));
        }
        QueryProcessor.instance.prepare(q("settle"), cs);
        long sum = sumWeights();
        int count = QueryProcessor.preparedStatementsCount();
        long evicted = QueryProcessor.metrics.preparedStatementsEvicted.getCount() - ev0;
        long deep = ObjectSizes.measureDeep(QueryProcessor.instance.getPreparedStatements());
        long h1 = usedAfterGc();
        long rows = ((Number) execute("SELECT count(*) FROM system.prepared_statements").one().getLong("count")).longValue();
        line("STAGE4 final label=" + label + " cap=" + cap + " n=" + n + " w0=" + w0 + " sumWeights=" + sum + " count=" + count + " evicted=" + evicted
             + " systemRows=" + rows + " measureDeepMap=" + deep + " liveHeapBaseline=" + h0 + " liveHeapFull=" + h1 + " liveDelta=" + (h1 - h0));
        boolean noEvictionRun = Boolean.getBoolean("stage4.noeviction");
        if (noEvictionRun)
        {
            check(label + " control-no-eviction", evicted == 0 && count == n + 1, "evicted=" + evicted + " count=" + count + " expected_count=" + (n + 1));
            check(label + " control-sum<=cap", sum <= cap, "sum=" + sum + " cap=" + cap);
        }
        else
        {
            check(label + " sum<=cap", sum <= cap, "sum=" + sum + " cap=" + cap);
            check(label + " evictions-occurred", evicted > 0, "evicted=" + evicted);
            check(label + " count+evicted==inserts", count + evicted == n + 1, "count=" + count + " evicted=" + evicted + " inserts=" + (n + 1));
        }

        // duplicate control
        int before = QueryProcessor.preparedStatementsCount();
        for (int i = 0; i < 100; i++)
            QueryProcessor.instance.prepare(q("dup"), cs);
        int after = QueryProcessor.preparedStatementsCount();
        check(label + " dup-adds-at-most-one", after - before <= 1, "before=" + before + " after=" + after);

        // oversize statement: one literal bigger than the cap
        char[] big = new char[(int) (cap + 1024 * 1024)];
        java.util.Arrays.fill(big, 'x');
        String oversize = "SELECT v FROM " + KEYSPACE + "." + currentTable() + " WHERE k = '" + new String(big) + "'";
        int cBefore = QueryProcessor.preparedStatementsCount();
        String msg = null;
        try
        {
            QueryProcessor.instance.prepare(oversize, cs);
        }
        catch (InvalidRequestException e)
        {
            msg = e.getMessage();
        }
        catch (Throwable t)
        {
            msg = "OTHER " + t;
        }
        line("STAGE4 oversize query_chars=" + oversize.length() + " message=" + (msg == null ? "NONE (accepted)" : msg.substring(0, Math.min(msg.length(), 110)))
             + " count_before=" + cBefore + " count_after=" + QueryProcessor.preparedStatementsCount());
        check(label + " oversize-rejected", msg != null && msg.startsWith("Prepared statement of size") && QueryProcessor.preparedStatementsCount() == cBefore,
              "msg_prefix_ok=" + (msg != null && msg.startsWith("Prepared statement of size")));
        line("STAGE4 done label=" + label + " mismatches=" + mismatches);
    }
}
