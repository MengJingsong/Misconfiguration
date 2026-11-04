/*
 * Stage-4 harness, unit tier (B2, as amended 2026-10-26) of
 * sai_vector_search_max_top_k-execute-pageSize--autonomous. Not upstream code.
 *
 * Shared body of TopKProbe100Test, TopKProbeDefaultTest and TopKProbe1500Test. Copied by unit-run.sh into
 * test/unit/org/apache/cassandra/index/sai/cql/ of the run clone, run with `ant testsome` (one JVM per class), then removed.
 * Prints one line per item, starting "PROBE ", to stdout (lands in build/test/logs/.../TEST-<class>.log).
 *
 * Workload (B2c): k int PRIMARY KEY, v vector<float, 4>, p text; SAI on v; 2000 rows, v = [1+i%7, 2+i%11, 3+i%13, 1],
 * p = 50 chars. Cases (P, L) with V = expected max_top_k: (10, 50), (10, V), (10, V+1), (-1, V), (5000, 50).
 * Each case: SelectStatement.execute(QueryState.forInternalCalls(), QueryOptions.create(ONE, [], false, P, ...), now).
 */
package org.apache.cassandra.index.sai.cql;

import java.util.ArrayList;
import java.util.List;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.cql3.QueryProcessor;
import org.apache.cassandra.cql3.statements.SelectStatement;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.index.sai.SAITester;
import org.apache.cassandra.index.sai.disk.v1.IndexWriterConfig;
import org.apache.cassandra.service.ClientState;
import org.apache.cassandra.service.ClientWarn;
import org.apache.cassandra.service.QueryState;
import org.apache.cassandra.transport.Dispatcher;
import org.apache.cassandra.transport.ProtocolVersion;
import org.apache.cassandra.transport.messages.ResultMessage;

import static org.junit.Assert.assertEquals;

public abstract class TopKProbeBase extends SAITester
{
    protected abstract int expected();

    @BeforeClass
    public static void network() throws Throwable
    {
        // amendment B2a: the ANN query without a partition key is a range read through StorageProxy
        requireNetwork();
    }

    @Test
    public void probe() throws Throwable
    {
        int v = expected();
        System.out.println("PROBE setup class=" + getClass().getSimpleName() + " MAX_TOP_K=" + IndexWriterConfig.MAX_TOP_K
                           + " expected=" + v + " property=" + System.getProperty("cassandra.sai.vector_search.max_top_k"));
        assertEquals(v, IndexWriterConfig.MAX_TOP_K);

        // amendment B2c item 2: the unit yaml enables read thresholds (test/conf/cassandra.yaml:63-67)
        DatabaseDescriptor.setReadThresholdsEnabled(false);
        System.out.println("PROBE setup readThresholdsEnabled=" + DatabaseDescriptor.getReadThresholdsEnabled());

        createTable("CREATE TABLE %s (k int PRIMARY KEY, v vector<float, 4>, p text)");
        createIndex("CREATE INDEX ON %s(v) USING 'sai'");
        String p = "abcdefghijabcdefghijabcdefghijabcdefghijabcdefghij";
        for (int i = 0; i < 2000; i++)
            execute("INSERT INTO %s (k, v, p) VALUES (" + i + ", [" + (1 + i % 7) + ", " + (2 + i % 11) + ", " + (3 + i % 13) + ", 1], '" + p + "')");
        long n = execute("SELECT count(*) FROM %s").one().getLong("count");
        System.out.println("PROBE table rows=" + n + " plen=" + p.length());

        int[][] cases = { { 10, 50 }, { 10, v }, { 10, v + 1 }, { -1, v }, { 5000, 50 } };
        int done = 0;
        for (int[] c : cases)
        {
            System.out.println("PROBE case maxTopK=" + v + " P=" + c[0] + " L=" + c[1] + " " + runCase(c[0], c[1]));
            done++;
        }
        System.out.println("PROBE done cases=" + done);
    }

    private String runCase(int pageSize, int limit)
    {
        String q = "SELECT k FROM %s ORDER BY v ANN OF [1, 2, 3, 1] LIMIT " + limit;
        SelectStatement st = (SelectStatement) QueryProcessor.parseStatement(formatQuery(q), ClientState.forInternalCalls());
        QueryOptions opts = QueryOptions.create(ConsistencyLevel.ONE, new ArrayList<>(), false, pageSize,
                                                null, null, ProtocolVersion.CURRENT, KEYSPACE);
        int rows = -1;
        String single = "na";
        String ex = "none";
        ClientWarn.instance.captureWarnings();
        try
        {
            ResultMessage.Rows r = st.execute(QueryState.forInternalCalls(), opts, Dispatcher.RequestTime.forImmediateExecution());
            rows = r.result.size();
            single = String.valueOf(r.result.metadata.getPagingState() == null);
        }
        catch (Throwable t)
        {
            ex = t.getClass().getSimpleName() + ": " + String.valueOf(t.getMessage()).replace('\n', ' ');
        }
        List<String> ws = ClientWarn.instance.getWarnings();
        ClientWarn.instance.resetWarnings();
        List<String> wl = ws == null ? new ArrayList<>() : ws;
        int topk = 0;
        for (String w : wl)
            if (w.startsWith("Top-K queries do not support paging"))
                topk++;
        return "rows=" + rows + " singlePage=" + single + " warnedTopKPageSize=" + topk + " warnings=" + wl.size()
               + " exception=[" + ex + "] warntext=" + wl;
    }
}
