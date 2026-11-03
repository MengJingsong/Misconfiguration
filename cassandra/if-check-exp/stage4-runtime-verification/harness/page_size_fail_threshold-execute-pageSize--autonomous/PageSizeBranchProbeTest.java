/*
 * Stage-4 harness, unit tier (B2, as amended 2026-10-26) of
 * page_size_fail_threshold-execute-pageSize--autonomous. Not upstream code.
 *
 * Copied by unit-run.sh into test/unit/org/apache/cassandra/db/guardrails/ of the run clone, run with
 * `ant testsome`, then removed. Prints one line per case, starting "PROBE ", to stdout (lands in
 * build/test/logs/.../TEST-<class>.log).
 *
 * Loop: thresholds (warn, fail) in {(5,10), (500,1000), (-1,-1)} x entry point {D, L} x case c1..c6.
 *   D = SelectStatement.execute(QueryState, QueryOptions, RequestTime)  -> target :338
 *   L = SelectStatement.executeLocally(QueryState, QueryOptions)        -> target :602
 * Properties (shakedown only): -Dprobe.rows=<n> (default 2000), -Dprobe.thr=5:10,500:1000,-1:-1
 */
package org.apache.cassandra.db.guardrails;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.cql3.QueryProcessor;
import org.apache.cassandra.cql3.UntypedResultSet;
import org.apache.cassandra.cql3.statements.SelectStatement;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.service.ClientState;
import org.apache.cassandra.service.ClientWarn;
import org.apache.cassandra.service.QueryState;
import org.apache.cassandra.transport.Dispatcher;
import org.apache.cassandra.transport.ProtocolVersion;
import org.apache.cassandra.transport.messages.ResultMessage;

public class PageSizeBranchProbeTest extends ThresholdTester
{
    public PageSizeBranchProbeTest()
    {
        super(5, 10,
              Guardrails.pageSize,
              Guardrails::setPageSizeThreshold,
              Guardrails::getPageSizeWarnThreshold,
              Guardrails::getPageSizeFailThreshold);
    }

    private static final String Q = "SELECT * FROM %s WHERE k = 0";

    @Test
    public void probe() throws Throwable
    {
        int nRows = Integer.getInteger("probe.rows", 2000);
        String thrSpec = System.getProperty("probe.thr", "5:10,500:1000,-1:-1");

        // Amendment B2c item 4: the unit yaml enables read thresholds (test/conf/cassandra.yaml:63-67); off, as on a node with defaults.
        DatabaseDescriptor.setReadThresholdsEnabled(false);
        System.out.println("PROBE setup readThresholdsEnabled=" + DatabaseDescriptor.getReadThresholdsEnabled()
                           + " userOrdinary=" + userClientState.isOrdinaryUser()
                           + " superOrdinary=" + superClientState.isOrdinaryUser()
                           + " daemonInitialized=" + DatabaseDescriptor.isDaemonInitialized());

        createTable("CREATE TABLE %s (k int, c int, v text, PRIMARY KEY (k, c))");
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 100; i++)
            sb.append((char) ('a' + (i % 26)));
        String v = sb.toString();
        for (int c = 0; c < nRows; c++)
            execute("INSERT INTO %s (k, c, v) VALUES (0, ?, ?)", c, v);
        UntypedResultSet cnt = execute("SELECT count(*) FROM %s WHERE k = 0");
        System.out.println("PROBE table " + currentTable() + " rows=" + cnt.one().getLong("count") + " vlen=" + v.length());

        String[][] cases = {
            // name, query suffix, page size, state
            { "c1", "", "3", "user" },
            { "c2", "", "11", "user" },
            { "c3", "", "-1", "user" },
            { "c4", " LIMIT 2000", "2000", "user" },
            { "c5", " LIMIT 2001", "2000", "user" },
            { "c6", "", "11", "super" },
        };
        int n = 0;
        for (String tp : thrSpec.split(","))
        {
            int w = Integer.parseInt(tp.split(":")[0]);
            int f = Integer.parseInt(tp.split(":")[1]);
            Guardrails.instance.setPageSizeThreshold(w, f);
            System.out.println("PROBE readback warn=" + w + " fail=" + f
                               + " getWarn=" + Guardrails.instance.getPageSizeWarnThreshold()
                               + " getFail=" + Guardrails.instance.getPageSizeFailThreshold());
            for (String entry : new String[]{ "D", "L" })
            {
                for (String[] cs : cases)
                {
                    ClientState state = cs[3].equals("super") ? superClientState : userClientState;
                    int p = Integer.parseInt(cs[2]);
                    String line = runCase(entry, state, Q + cs[1], p);
                    System.out.println("PROBE case thr=" + w + ":" + f + " entry=" + entry + " case=" + cs[0]
                                       + " P=" + p + " state=" + cs[3] + " " + line);
                    n++;
                }
            }
        }
        System.out.println("PROBE done cases=" + n);
    }

    private String runCase(String entry, ClientState state, String query, int pageSize)
    {
        QueryState qs = new QueryState(state);
        SelectStatement st = (SelectStatement) QueryProcessor.parseStatement(formatQuery(query), qs.getClientState());
        QueryOptions opts = QueryOptions.create(ConsistencyLevel.ONE, Collections.emptyList(), false, pageSize,
                                                null, null, ProtocolVersion.CURRENT, KEYSPACE);
        String threw = "none";
        int rows = -1;
        String hasMore = "na";
        ClientWarn.instance.captureWarnings();
        try
        {
            ResultMessage.Rows r = entry.equals("D")
                                   ? st.execute(qs, opts, Dispatcher.RequestTime.forImmediateExecution())
                                   : st.executeLocally(qs, opts);
            rows = r.result.size();
            hasMore = String.valueOf(r.result.metadata.getPagingState() != null);
        }
        catch (Throwable t)
        {
            threw = t.getClass().getSimpleName() + ": " + String.valueOf(t.getMessage()).replace('\n', ' ');
        }
        List<String> ws = ClientWarn.instance.getWarnings();
        ClientWarn.instance.resetWarnings();
        List<String> wl = ws == null ? new ArrayList<>() : ws;
        int pageWarn = 0;
        for (String s : wl)
            if (s.contains("page size") && s.contains("exceeds warning threshold"))
                pageWarn++;
        return "rows=" + rows + " hasMore=" + hasMore + " pageSizeWarnings=" + pageWarn + " warnings=" + wl.size()
               + " threw=[" + threw + "] warntext=" + wl;
    }
}
