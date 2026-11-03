/*
 * Stage 4, unit tier Program 2 (B2, amended 2026-10-25) of
 * prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous. Not upstream.
 * Copy into test/unit/org/apache/cassandra/probe/ of the run clone; one `ant testsome` (own JVM) per knob value, the knob set
 * on the one line of test/conf/cassandra.yaml (unit-run.sh):
 *   ant testsome -Dtest.name=org.apache.cassandra.probe.PreparedCacheCapProbeTest -Dtest.jvm.args="-Dstage4.out=<file> -Dstage4.label=<l>"
 * Order (B2e amendment): calibration -> main series of N distinct statements -> B2h control (a) -> B2h control (b).
 * Statements are fully qualified and ClientState has no keyspace: one cache entry per prepare (QueryProcessor.java:760-767).
 */
package org.apache.cassandra.probe;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.util.Map;

import com.github.benmanes.caffeine.cache.Cache;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.cql3.QueryHandler;
import org.apache.cassandra.cql3.QueryProcessor;
import org.apache.cassandra.service.ClientState;
import org.apache.cassandra.transport.messages.ResultMessage;
import org.apache.cassandra.utils.MD5Digest;

public class PreparedCacheCapProbeTest extends CQLTester
{
    static PrintWriter out;

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

    @SuppressWarnings("unchecked")
    static long weightedSize() throws Exception
    {
        Field f = QueryProcessor.class.getDeclaredField("preparedStatements");
        f.setAccessible(true);
        Cache<MD5Digest, QueryHandler.Prepared> c = (Cache<MD5Digest, QueryHandler.Prepared>) f.get(null);
        return c.policy().eviction().get().weightedSize().getAsLong();
    }

    static long sumWeights()
    {
        long sum = 0;
        for (Map.Entry<MD5Digest, QueryHandler.Prepared> e : QueryProcessor.instance.getPreparedStatements().entrySet())
            sum += e.getKey().size() + e.getValue().pstmntSize;
        return sum;
    }

    static long evicted()
    {
        return QueryProcessor.metrics.preparedStatementsEvicted.getCount();
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

    String cols;

    String q(int i)
    {
        return "SELECT " + cols + " FROM " + KEYSPACE + "." + currentTable() + " WHERE k = ? AND c0 = '" + i + "' ALLOW FILTERING";
    }

    @Test
    public void run() throws Throwable
    {
        String label = System.getProperty("stage4.label", "x");
        long mib = DatabaseDescriptor.getPreparedStatementsCacheSizeMiB();
        long cap = mib * 1024 * 1024;
        long maxMem = Runtime.getRuntime().maxMemory();
        long autoExpected = Math.max(10, (int) (maxMem / 1024 / 1024 / 256));
        StringBuilder ddl = new StringBuilder("CREATE TABLE %s (k int PRIMARY KEY");
        StringBuilder sel = new StringBuilder();
        for (int c = 0; c < 50; c++)
        {
            ddl.append(", c").append(c).append(" text");
            sel.append(c == 0 ? "" : ", ").append('c').append(c);
        }
        cols = sel.toString();
        createTable(ddl.append(")").toString());
        ClientState cs = ClientState.forInternalCalls();
        line("STAGE4 run label=" + label + " cap_mib=" + mib + " cap_bytes=" + cap + " maxMemory=" + maxMem + " auto_expected_mib=" + autoExpected
             + " cache_bytes_static=" + QueryProcessor.PREPARED_STATEMENT_CACHE_SIZE_BYTES + " keyspace_in_clientstate=" + cs.getRawKeyspace()
             + " count_at_start=" + QueryProcessor.preparedStatementsCount());

        // calibration = statement 0
        long ev0 = evicted();
        ResultMessage.Prepared p0 = QueryProcessor.instance.prepare(q(0), cs);
        QueryHandler.Prepared prep0 = QueryProcessor.instance.getPrepared(p0.statementId);
        long w = p0.statementId.size() + prep0.pstmntSize;
        line("STAGE4 calibration id_size=" + p0.statementId.size() + " pstmntSize=" + prep0.pstmntSize + " w=" + w
             + " count_after_one=" + QueryProcessor.preparedStatementsCount() + " query_chars=" + q(0).length());
        long n = (4L * 16 * 1024 * 1024 + w - 1) / w;
        line("STAGE4 plan N=" + n + " offered_weight=" + n * w + " expected_plateau=" + (double) cap / w);
        long h0 = usedAfterGc();
        for (int i = 1; i < n; i++)
        {
            QueryProcessor.instance.prepare(q(i), cs);
            if ((i + 1) % 100 == 0 || i + 1 == n)
                line("STAGE4 sample i=" + (i + 1) + " weightedSize=" + weightedSize() + " sumWeights=" + sumWeights()
                     + " count=" + QueryProcessor.preparedStatementsCount() + " evicted=" + (evicted() - ev0));
        }
        long countEnd = QueryProcessor.preparedStatementsCount();
        long evEnd = evicted() - ev0;
        long ws = weightedSize();
        long h1 = usedAfterGc();
        line("STAGE4 final label=" + label + " cap=" + cap + " N=" + n + " w=" + w + " weightedSize=" + ws + " sumWeights=" + sumWeights()
             + " count=" + countEnd + " evicted=" + evEnd + " heapAfterGcBaseline=" + h0 + " heapAfterGcEnd=" + h1 + " heapDelta=" + (h1 - h0));

        // B2h control (a): empty cache, first floor(count_end/2) statements again
        QueryProcessor.clearPreparedStatementsCache();
        long evA = evicted();
        long half = countEnd / 2;
        line("STAGE4 controlA start count_after_clear=" + QueryProcessor.preparedStatementsCount() + " half=" + half);
        for (int i = 0; i < half; i++)
            QueryProcessor.instance.prepare(q(i), cs);
        line("STAGE4 controlA label=" + label + " prepared=" + half + " count=" + QueryProcessor.preparedStatementsCount()
             + " evicted_delta=" + (evicted() - evA) + " weightedSize=" + weightedSize());

        // B2h control (b): empty cache, statement 0 prepared N times
        QueryProcessor.clearPreparedStatementsCache();
        long evB = evicted();
        String same = q(0);
        for (long i = 0; i < n; i++)
            QueryProcessor.instance.prepare(same, cs);
        line("STAGE4 controlB label=" + label + " prepared=" + n + " count=" + QueryProcessor.preparedStatementsCount()
             + " evicted_delta=" + (evicted() - evB));
        line("STAGE4 done label=" + label);
    }
}
