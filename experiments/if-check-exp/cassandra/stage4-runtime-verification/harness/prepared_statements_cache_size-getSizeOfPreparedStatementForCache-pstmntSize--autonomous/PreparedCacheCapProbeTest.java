package org.apache.cassandra.cql3;

import java.util.Map;
import org.junit.Test;
import org.apache.cassandra.service.ClientState;
import org.apache.cassandra.utils.MD5Digest;

public class PreparedCacheCapProbeTest extends CQLTester
{
    @Test
    public void probe() throws Throwable
    {
        StringBuilder cols = new StringBuilder();
        for (int i = 0; i < 20; i++) cols.append(", v").append(i).append(" text");
        createTable("CREATE TABLE %s (k int, c int" + cols + ", PRIMARY KEY (k, c))");
        QueryProcessor.clearPreparedStatements(true);           // EXPLICIT removals, not counted as evictions
        long cap = QueryProcessor.PREPARED_STATEMENT_CACHE_SIZE_BYTES;
        long ev0 = QueryProcessor.metrics.preparedStatementsEvicted.getCount();
        int n = Integer.getInteger("probe.n", 3000);
        ClientState cs = ClientState.forInternalCalls();        // raw keyspace null -> one cache id per statement
        long maxW = 0;
        for (int i = 1; i <= n; i++)
        {
            String q = String.format("SELECT * FROM %s.%s WHERE k = ? AND c = %d", keyspace(), currentTable(), i);
            QueryProcessor.instance.prepare(q, cs);
            if (i % 100 == 0 || i == n)
            {
                long sum = 0; int cnt = 0;
                for (Map.Entry<MD5Digest, QueryHandler.Prepared> e : QueryProcessor.instance.getPreparedStatements().entrySet())
                {
                    long w = e.getKey().size() + e.getValue().pstmntSize;
                    sum += w; cnt++; maxW = Math.max(maxW, w);
                }
                // stage-4 amendment 2026-10-26 (B2c): one write per reading; same format string and arguments as the case file's printf
                System.out.println(String.format("PROBE i=%d cap=%d resident=%d sumWeight=%d maxW=%d evicted=%d",
                                  i, cap, cnt, sum, maxW,
                                  QueryProcessor.metrics.preparedStatementsEvicted.getCount() - ev0));
            }
        }
    }
}
