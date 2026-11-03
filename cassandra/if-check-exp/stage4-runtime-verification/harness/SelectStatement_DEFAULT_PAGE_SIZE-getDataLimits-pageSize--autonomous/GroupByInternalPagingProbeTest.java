/*
 * Stage-4 harness, unit tier (B2, as amended 2026-10-26) of
 * SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous. Not upstream code.
 *
 * Copied by unit-run.sh into test/unit/org/apache/cassandra/cql3/ of the run clone, run with `ant testsome`, then
 * removed. Prints one line per cell, starting "PROBE ", to stdout (lands in build/test/logs/.../TEST-<class>.log).
 *
 * For each N in {25000, 50000}: a fresh table (k int, g int, c int, v blob, PRIMARY KEY (k, g, c)), one partition k=0,
 * G=50 groups of N/G rows, v = 16 random bytes; flush. Then for (query, P) in
 * (Qg,-1), (Qg,1000), (Qg,50000), (Qa,-1): parse, build QueryOptions (CL ONE, page size P), record
 * limits = getQuery(options, now).limits().toString(), the delta of ClientRequestsMetricsHolder.readMetrics latency count
 * (one per StorageProxy.read) and of the table's readLatency count (one per local single-partition read), result rows,
 * and whether the response has more pages.
 * Properties (shakedown only): -Dprobe.n=<comma list> (default 25000,50000)
 */
package org.apache.cassandra.cql3;

import java.nio.ByteBuffer;
import java.util.List;
import java.util.Random;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.statements.SelectStatement;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.metrics.ClientRequestsMetricsHolder;
import org.apache.cassandra.service.ClientState;
import org.apache.cassandra.service.QueryState;
import org.apache.cassandra.transport.Dispatcher;
import org.apache.cassandra.transport.ProtocolVersion;
import org.apache.cassandra.transport.messages.ResultMessage;
import org.apache.cassandra.utils.FBUtilities;

public class GroupByInternalPagingProbeTest extends CQLTester
{
    static final String QG = "SELECT k, g, max(v) FROM %s WHERE k=0 GROUP BY k, g";
    static final String QA = "SELECT max(v) FROM %s WHERE k=0";
    static final int G = 50;

    @BeforeClass
    public static void network() throws Exception
    {
        requireNetwork();
    }

    @Test
    public void probe() throws Throwable
    {
        // Amendment B2c: the unit yaml enables read thresholds (test/conf/cassandra.yaml:63-67); a node's defaults leave
        // the size thresholds unset, so they are turned off here (they would otherwise abort or warn on these reads).
        DatabaseDescriptor.setReadThresholdsEnabled(false);
        System.out.println("PROBE setup readThresholdsEnabled=" + DatabaseDescriptor.getReadThresholdsEnabled()
                           + " DEFAULT_PAGE_SIZE=" + SelectStatement.DEFAULT_PAGE_SIZE
                           + " daemonInitialized=" + DatabaseDescriptor.isDaemonInitialized());
        String[] ns = System.getProperty("probe.n", "25000,50000").split(",");
        Random rnd = new Random(42);
        int cells = 0;
        for (String nStr : ns)
        {
            int n = Integer.parseInt(nStr.trim());
            int perGroup = n / G;
            createTable("CREATE TABLE %s (k int, g int, c int, v blob, PRIMARY KEY (k, g, c))");
            for (int g = 0; g < G; g++)
                for (int c = 0; c < perGroup; c++)
                {
                    byte[] b = new byte[16];
                    rnd.nextBytes(b);
                    execute("INSERT INTO %s (k, g, c, v) VALUES (0, ?, ?, ?)", g, c, ByteBuffer.wrap(b));
                }
            flush();
            ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
            long count = execute("SELECT count(*) FROM %s WHERE k=0").one().getLong("count");
            System.out.println("PROBE load N=" + n + " table=" + currentTable() + " rows=" + count
                               + " sstables=" + cfs.getLiveSSTables().size() + " memtableCells=" + cfs.getTracker().getView().getCurrentMemtable().operationCount());

            Object[][] runs = { { "Qg", QG, -1 }, { "Qg", QG, 1000 }, { "Qg", QG, 50000 }, { "Qa", QA, -1 } };
            for (Object[] r : runs)
            {
                String name = (String) r[0];
                int p = (Integer) r[2];
                SelectStatement stmt = (SelectStatement) QueryProcessor.parseStatement(formatQuery((String) r[1]), ClientState.forInternalCalls());
                QueryOptions options = QueryOptions.create(ConsistencyLevel.ONE, List.of(), false, p, null, null, ProtocolVersion.CURRENT, KEYSPACE);
                String limits = stmt.getQuery(options, FBUtilities.nowInSeconds()).limits().toString();
                long r0 = ClientRequestsMetricsHolder.readMetrics.latency.getCount();
                long l0 = cfs.metric.readLatency.latency.getCount();
                ResultMessage.Rows rows = stmt.execute(QueryState.forInternalCalls(), options, Dispatcher.RequestTime.forImmediateExecution());
                long r1 = ClientRequestsMetricsHolder.readMetrics.latency.getCount();
                long l1 = cfs.metric.readLatency.latency.getCount();
                boolean hasMore = rows.result.metadata.getPagingState() != null;
                System.out.println("PROBE cell N=" + n + ",query=" + name + ",P=" + p + ",limits=[" + limits + "],reads=" + (r1 - r0)
                                   + ",localReads=" + (l1 - l0) + ",groups=" + rows.result.size() + ",hasMore=" + hasMore);
                cells++;
            }
        }
        System.out.println("PROBE done cells=" + cells);
    }
}
