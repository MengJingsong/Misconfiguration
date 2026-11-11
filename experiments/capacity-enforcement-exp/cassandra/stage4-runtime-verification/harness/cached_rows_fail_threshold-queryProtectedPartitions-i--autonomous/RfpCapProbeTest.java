/*
 * Stage-4 harness, unit tier (B2, amendments U1-U5 of 2026-10-27) of
 * cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.
 * Copied into the run clone at test/distributed/org/apache/cassandra/distributed/test/ only for the run, removed afterwards.
 *
 * Two in-JVM instances, keyspace RF 2 (TestBaseImpl.init), hinted handoff off. For each fail threshold T of rfp.ts:
 *   fresh table t_<T>; N rows k=0, c=0..N-1, v='old' inserted through coordinator 1 at ALL; then on node 1 only
 *   (executeInternal, not replicated) v='new' for every c; warn threshold Integer.MAX_VALUE, fail threshold T (read back);
 *   SELECT * FROM t_<T> WHERE v='old' ALLOW FILTERING at ALL through coordinator 1 (unpaged); record outcome, exception,
 *   node-1 log lines (the RFP logger's own lines, and for information all lines containing the text), node-1 histogram
 *   rfpRowsCachedPerQuery (count, max) and the RFP request meter.
 * Control (B2h): table t_ctl loaded the same way without the node-1 update, queried at T = rfp.ctl.
 * Known answer (U4): a fresh DecayingEstimatedHistogramReservoir(true) on node 1 updated with one value reads getMax().
 * Every reading is one stdout line starting with RFPU; nothing is asserted except that the cluster runs.
 */
package org.apache.cassandra.distributed.test;

import java.util.ArrayList;
import java.util.List;

import org.junit.Test;

import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.distributed.Cluster;
import org.apache.cassandra.distributed.api.SimpleQueryResult;
import org.apache.cassandra.metrics.DecayingEstimatedHistogramReservoir;
import org.apache.cassandra.service.StorageService;

import static org.apache.cassandra.distributed.api.ConsistencyLevel.ALL;

public class RfpCapProbeTest extends TestBaseImpl
{
    private static final String MARK = "Replica filtering protection has cached over";
    // amendment D1 (2026-10-27): the RFP logger's own line (ReplicaFilteringProtection.java:329), not the in-JVM executor's
    // uncaught-exception report, whose message line also contains MARK
    private static final java.util.regex.Pattern RFP_LINE = java.util.regex.Pattern.compile("ReplicaFilteringProtection\\.java:[0-9]+ - " + MARK);

    private static void out(String s)
    {
        System.out.println(s);
        System.out.flush();
    }

    @Test
    public void probe() throws Throwable
    {
        int n = Integer.getInteger("rfp.n", 20000);
        String ts = System.getProperty("rfp.ts", "1000,10000,32000,100000");
        int ctl = Integer.getInteger("rfp.ctl", 100000);
        out("RFPU-START," + n + ',' + ts.replace(',', ' ') + ',' + ctl);

        try (Cluster cluster = init(Cluster.build(2)
                                           .withConfig(c -> c.set("hinted_handoff_enabled", false))
                                           .start()))
        {
            // Known answers for the histogram reading (instrument check, U4).
            for (long v : new long[]{ 1001, 10001, 32001, 40000, 200000 })
            {
                long m = cluster.get(1).callOnInstance(() -> {
                    DecayingEstimatedHistogramReservoir r = new DecayingEstimatedHistogramReservoir(true);
                    r.update(v);
                    return r.getSnapshot().getMax();
                });
                out("RFPU-KA," + v + ',' + m);
            }

            List<String> runs = new ArrayList<>();
            for (String t : ts.split(","))
                runs.add(t.trim());
            runs.add("ctl");

            for (String run : runs)
            {
                boolean control = run.equals("ctl");
                int T = control ? ctl : Integer.parseInt(run);
                String table = "t_" + run;
                String fq = KEYSPACE + '.' + table;
                cluster.schemaChange("CREATE TABLE " + fq + " (k int, c int, v text, PRIMARY KEY (k, c))");
                for (int c = 0; c < n; c++)
                    cluster.coordinator(1).execute("INSERT INTO " + fq + " (k, c, v) VALUES (0, ?, 'old')", ALL, c);
                if (!control)
                    for (int c = 0; c < n; c++)
                        cluster.get(1).executeInternal("UPDATE " + fq + " SET v = 'new' WHERE k = 0 AND c = ?", c);

                cluster.get(1).runOnInstance(() -> StorageService.instance.setCachedReplicaRowsWarnThreshold(Integer.MAX_VALUE));
                cluster.get(1).runOnInstance(() -> StorageService.instance.setCachedReplicaRowsFailThreshold(T));
                int readBack = cluster.get(1).callOnInstance(() -> StorageService.instance.getCachedReplicaRowsFailThreshold());
                int warnBack = cluster.get(1).callOnInstance(() -> StorageService.instance.getCachedReplicaRowsWarnThreshold());
                long count0 = cluster.get(1).callOnInstance(() -> Keyspace.open(KEYSPACE).getColumnFamilyStore(table).metric.rfpRowsCachedPerQuery.getCount());
                long req0 = cluster.get(1).callOnInstance(() -> Keyspace.open(KEYSPACE).getColumnFamilyStore(table).metric.replicaFilteringProtectionRequests.getCount());
                long mark = cluster.get(1).logs().mark();

                String outcome, exClass = "-", msg = "-";
                int rows = -1, warnings = -1;
                long t0 = System.nanoTime();
                try
                {
                    SimpleQueryResult r = cluster.coordinator(1).executeWithResult("SELECT * FROM " + fq + " WHERE v = 'old' ALLOW FILTERING", ALL);
                    rows = r.toObjectArrays().length;
                    warnings = r.warnings().size();
                    outcome = "OK";
                }
                catch (Throwable e)
                {
                    outcome = "FAIL";
                    exClass = e.getClass().getName();
                    msg = String.valueOf(e.getMessage());
                }
                long ms = (System.nanoTime() - t0) / 1_000_000;

                long count1 = cluster.get(1).callOnInstance(() -> Keyspace.open(KEYSPACE).getColumnFamilyStore(table).metric.rfpRowsCachedPerQuery.getCount());
                long max = cluster.get(1).callOnInstance(() -> Keyspace.open(KEYSPACE).getColumnFamilyStore(table).metric.rfpRowsCachedPerQuery.getSnapshot().getMax());
                long req1 = cluster.get(1).callOnInstance(() -> Keyspace.open(KEYSPACE).getColumnFamilyStore(table).metric.replicaFilteringProtectionRequests.getCount());
                int logAll = cluster.get(1).logs().grep(mark, MARK).getResult().size();
                int logLines = cluster.get(1).logs().grep(mark, RFP_LINE).getResult().size();
                boolean msgFail = msg.contains("cached_replica_rows_fail_threshold");
                boolean msgOver = msg.contains("cached over " + T + " rows");

                // RFPU,table,T,readBack,warnBack,updated,N,outcome,rows,warnings,exClass,msgHasFailKey,msgHasCachedOverT,logLines(RFP logger),histSamples,histMax,rfpRequests,ms,logLinesAll
                out("RFPU," + table + ',' + T + ',' + readBack + ',' + warnBack + ',' + (!control) + ',' + n + ',' + outcome + ',' + rows + ',' + warnings + ','
                    + exClass + ',' + msgFail + ',' + msgOver + ',' + logLines + ',' + (count1 - count0) + ',' + max + ',' + (req1 - req0) + ',' + ms + ',' + logAll);
                out("RFPU-MSG," + table + ',' + msg.replace('\n', ' '));
            }
            out("RFPU-END");
        }
    }
}
