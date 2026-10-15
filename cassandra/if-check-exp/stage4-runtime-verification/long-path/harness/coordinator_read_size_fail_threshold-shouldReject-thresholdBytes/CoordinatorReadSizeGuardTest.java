/*
 * Stage-4 harness, unit tier of coordinator_read_size_fail_threshold-shouldReject-thresholdBytes (case file section 9,
 * as amended 2026-10-15). Not part of upstream Cassandra. Copy into test/unit/org/apache/cassandra/cql3/ of a local clone
 * at cassandra-5.0.9. System property stage4.out: a file that also receives the STAGE4 lines.
 * Prints "STAGE4 check <name> <expected> <actual> ok|MISMATCH"; a mismatch is recorded and the test goes on; it fails at the end.
 */
package org.apache.cassandra.cql3;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.Collections;
import java.util.Map;

import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.selection.ResultSetBuilder;
import org.apache.cassandra.cql3.statements.SelectStatement;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.db.ReadExecutionController;
import org.apache.cassandra.db.ReadQuery;
import org.apache.cassandra.db.ReadResponse;
import org.apache.cassandra.db.SinglePartitionReadCommand;
import org.apache.cassandra.db.SinglePartitionReadQuery;
import org.apache.cassandra.db.partitions.PartitionIterator;
import org.apache.cassandra.db.partitions.UnfilteredPartitionIterator;
import org.apache.cassandra.db.partitions.UnfilteredPartitionIterators;
import org.apache.cassandra.db.rows.Row;
import org.apache.cassandra.db.rows.RowIterator;
import org.apache.cassandra.db.transform.Transformation;
import org.apache.cassandra.exceptions.ReadSizeAbortException;
import org.apache.cassandra.metrics.ClientRequestsMetricsHolder;
import org.apache.cassandra.net.MessagingService;
import org.apache.cassandra.service.ClientState;
import org.apache.cassandra.service.QueryState;
import org.apache.cassandra.transport.Dispatcher;
import org.apache.cassandra.transport.ProtocolVersion;
import org.apache.cassandra.transport.messages.ResultMessage;
import org.apache.cassandra.utils.FBUtilities;

public class CoordinatorReadSizeGuardTest extends CQLTester
{
    static final int N = 2000, PAYLOAD = 1000, S = 1008;
    static PrintWriter out;
    static int mismatches = 0, checks = 0;
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

    static void line(String s)
    {
        System.out.println(s);
        if (out != null) { out.println(s); out.flush(); }
    }

    static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        checks++;
        if (!ok) mismatches++;
        line("STAGE4 check " + name + " " + expected + " " + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    static void checkTrue(String name, boolean cond, String detail)
    {
        checks++;
        if (!cond) mismatches++;
        line("STAGE4 check " + name + " true " + cond + " " + (cond ? "ok" : "MISMATCH") + " [" + detail + "]");
    }

    @BeforeClass
    public static void setUpStage4() throws Exception
    {
        String f = System.getProperty("stage4.out");
        if (f != null) out = new PrintWriter(new FileWriter(f, true));
        requireNetwork();
        line("STAGE4 info jvm " + System.getProperty("java.version") + " allocatedBytesSupported " + TMX.isThreadAllocatedMemorySupported());
    }

    static long nStar(long F) { return F / S + 1; }

    static void limit(Long F)
    {
        DatabaseDescriptor.setCoordinatorReadSizeFailThreshold(F == null ? null : new DataStorageSpec.LongBytesBound(F, DataStorageSpec.DataStorageUnit.BYTES));
    }

    static long allocated() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    String table() { return KEYSPACE + '.' + currentTable(); }

    static class WB
    {
        boolean aborted; long size; int pulled; int rows = -1; long resp; long alloc;
        public String toString() { return "aborted=" + aborted + " size=" + size + " pulled=" + pulled + " rows=" + rows + " resp=" + resp + " alloc=" + alloc; }
    }

    static class RowCounter extends Transformation<RowIterator>
    {
        int rows;
        protected RowIterator applyToPartition(RowIterator p)
        {
            return Transformation.apply(p, new Transformation<RowIterator>()
            {
                protected Row applyToRow(Row r) { rows++; return r; }
            });
        }
    }

    /** White-box loop: mirrors SelectStatement.process() :1004-1014 without the warn, ordering and trim. */
    WB wb(String where)
    {
        String q = "SELECT * FROM " + table() + " WHERE pk = 1" + where;
        SelectStatement stmt = (SelectStatement) QueryProcessor.getStatement(q, ClientState.forInternalCalls());
        QueryOptions options = QueryOptions.forInternalCalls(ConsistencyLevel.ONE, Collections.emptyList());
        long nowInSec = FBUtilities.nowInSeconds();
        ReadQuery rq = stmt.getQuery(options, nowInSec);
        SinglePartitionReadCommand cmd = rq instanceof SinglePartitionReadCommand ? (SinglePartitionReadCommand) rq
                                         : (SinglePartitionReadCommand) ((SinglePartitionReadQuery.Group<?>) rq).queries.get(0);
        ReadResponse rsp;
        try (ReadExecutionController c = cmd.executionController(); UnfilteredPartitionIterator it = cmd.executeLocally(c))
        {
            rsp = cmd.createResponse(it, c.getRepairedDataInfo());
        }
        WB r = new WB();
        r.resp = ReadResponse.serializer.serializedSize(rsp, MessagingService.current_version);
        ResultSetBuilder builder = new ResultSetBuilder(stmt.getResultMetadata(), stmt.getSelection().newSelectors(options), false);
        RowCounter counter = new RowCounter();
        long a0 = allocated();
        try (PartitionIterator pi = Transformation.apply(UnfilteredPartitionIterators.filter(rsp.makeIterator(cmd), cmd.nowInSec()), counter))
        {
            while (pi.hasNext())
                try (RowIterator p = pi.next())
                {
                    stmt.processPartition(p, options, builder, nowInSec);
                }
            r.rows = builder.build().size();
        }
        catch (ReadSizeAbortException e)
        {
            r.aborted = true;
        }
        r.alloc = allocated() - a0;
        r.size = builder.getSize();
        r.pulled = counter.rows;
        return r;
    }

    long medianAlloc(String where)
    {
        for (int i = 0; i < 2; i++) wb(where);
        long[] d = new long[5];
        for (int i = 0; i < 5; i++) d[i] = wb(where).alloc;
        Arrays.sort(d);
        line("STAGE4 info allocs [" + where + "] " + Arrays.toString(d));
        return d[2];
    }

    long tableAborts() { return getCurrentColumnFamilyStore().metric.coordinatorReadSizeAborts.table.getCount(); }
    static long clientAborts() { return ClientRequestsMetricsHolder.readMetrics.readSizeAborts.getCount(); }

    static class Net
    {
        boolean ok; int rows = -1; String err; Map<?, Integer> codes; long first = -1;
        public String toString() { return "ok=" + ok + " rows=" + rows + " err=" + err + " codes=" + codes; }
    }

    Net net(String cql, int pageSize)
    {
        Net n = new Net();
        try
        {
            com.datastax.driver.core.ResultSet rs = pageSize > 0 ? executeNetWithPaging(ProtocolVersion.V5, cql, pageSize) : executeNet(ProtocolVersion.V5, cql);
            int c = 0;
            for (com.datastax.driver.core.Row row : rs)
            {
                if (c == 0 && cql.contains("count(*)")) n.first = row.getLong(0);
                c++;
            }
            n.rows = c; n.ok = true;
        }
        catch (com.datastax.driver.core.exceptions.ReadFailureException e)
        {
            n.err = "ReadFailureException"; n.codes = e.getFailuresMap();
        }
        catch (Throwable t)
        {
            n.err = t.getClass().getSimpleName() + ": " + t.getMessage();
        }
        return n;
    }

    static boolean code4(Net n) { return n.codes != null && n.codes.size() == 1 && n.codes.containsValue(4); }

    @Test
    public void guard() throws Throwable
    {
        // 1. setup
        DatabaseDescriptor.setReadThresholdsEnabled(true);
        DatabaseDescriptor.setCoordinatorReadSizeWarnThreshold(null);
        DatabaseDescriptor.setLocalReadSizeWarnThreshold(null);
        DatabaseDescriptor.setLocalReadSizeFailThreshold(null);
        DatabaseDescriptor.setRowIndexReadSizeWarnThreshold(null);
        DatabaseDescriptor.setRowIndexReadSizeFailThreshold(null);
        limit(null);
        createTable("CREATE TABLE %s (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression = {'enabled': false}");
        disableCompaction();
        ByteBuffer v = ByteBuffer.wrap(new byte[PAYLOAD]);
        for (int i = 0; i < N; i++)
            execute("INSERT INTO %s (pk, ck, v) VALUES (1, ?, ?)", i, v);
        flush();
        check("setup_sstables", 1, getCurrentColumnFamilyStore().getLiveSSTables().size());
        Net probe = net("SELECT * FROM " + table() + " WHERE pk = 1 AND ck < 1", 0);
        check("setup_probe_v5_rows", 1, probe.rows);
        line("STAGE4 info probe " + probe);

        // 2. known answer at unset
        check("readback_unset_options", -1L, QueryOptions.forInternalCalls(ConsistencyLevel.ONE, Collections.emptyList()).getCoordinatorReadSizeAbortThresholdBytes());
        long respWhole = -1;
        for (int n : new int[]{ 100, 1000, N })
        {
            WB r = wb(n == N ? "" : " AND ck < " + n);
            line("STAGE4 info known " + n + " " + r);
            check("known_size_" + n, (long) S * n, r.size);
            check("known_rows_" + n, n, r.rows);
            check("known_completes_" + n, false, r.aborted);
            if (n == N) respWhole = r.resp;
        }
        long d100 = medianAlloc(" AND ck < 100"), d2000 = medianAlloc("");
        double a = (d2000 - d100) / (double) (N - 100);
        long delta0 = (long) (d100 - 100 * a);
        line("STAGE4 info a " + a + " delta0 " + delta0 + " respWhole " + respWhole);

        // 3. each F below the data
        long[] fs = { 65536L, 262144L, 1048576L };
        long[] dd = new long[3];
        for (int k = 0; k < 3; k++)
        {
            long F = fs[k], ns = nStar(F), X = ns * S;
            limit(F);
            check("readback_" + F, F, DatabaseDescriptor.getCoordinatorReadSizeFailThreshold().toBytes());
            check("readback_options_" + F, F, QueryOptions.forInternalCalls(ConsistencyLevel.ONE, Collections.emptyList()).getCoordinatorReadSizeAbortThresholdBytes());
            WB a1 = wb(" AND ck < " + ns);
            line("STAGE4 info F=" + F + " ck<n* " + a1);
            check("A_completes_" + F, false, a1.aborted);
            check("A_rows_" + F, ns, a1.rows);
            check("A_size_" + F, X, a1.size);
            checkTrue("A_size_above_F_" + F, a1.size > F, a1.size + " > " + F);
            for (String w : new String[]{ " AND ck < " + (ns + 1), "" })
            {
                String tag = w.isEmpty() ? "whole" : "nplus1";
                WB b = wb(w);
                line("STAGE4 info F=" + F + " " + tag + " " + b);
                check("B_aborts_" + tag + "_" + F, true, b.aborted);
                check("B_size_" + tag + "_" + F, X, b.size);
                check("B_pulled_" + tag + "_" + F, ns + 1, b.pulled);
                if (w.isEmpty()) check("replica_resp_same_" + F, respWhole, b.resp);
            }
            dd[k] = medianAlloc("");
            // client path
            long t0 = tableAborts(), c0 = clientAborts();
            Net ok = net("SELECT * FROM " + table() + " WHERE pk = 1 AND ck < " + ns, 0);
            check("client_A_rows_" + F, ns, ok.rows);
            Net e1 = net("SELECT * FROM " + table() + " WHERE pk = 1 AND ck < " + (ns + 1), 0);
            Net e2 = net("SELECT * FROM " + table() + " WHERE pk = 1", 0);
            line("STAGE4 info client F=" + F + " A " + ok + " | nplus1 " + e1 + " | whole " + e2);
            checkTrue("client_nplus1_code4_" + F, code4(e1), String.valueOf(e1));
            checkTrue("client_whole_code4_" + F, code4(e2), String.valueOf(e2));
            check("client_table_meter_+2_" + F, t0 + 2, tableAborts());
            check("client_request_meter_+2_" + F, c0 + 2, clientAborts());
        }
        double slope = (dd[2] - dd[0]) / (double) (nStar(fs[2]) + 1 - (nStar(fs[0]) + 1));
        double ratio = (dd[1] - dd[0]) / (double) (dd[2] - dd[1]);
        line("STAGE4 info abort allocs " + Arrays.toString(dd) + " slope " + slope + " a " + a + " ratio " + ratio);
        checkTrue("alloc_slope_within_15pct_of_a", Math.abs(slope - a) / a <= 0.15, "slope " + slope + " a " + a);
        checkTrue("alloc_ratio_0.25pm0.03", Math.abs(ratio - 0.25) <= 0.03, "ratio " + ratio);

        // 4. boundary
        limit(100800L);
        WB b1 = wb(" AND ck < 101"), b2 = wb(" AND ck < 102");
        check("boundary_100800_ck101_completes", false, b1.aborted); check("boundary_100800_ck101_rows", 101, b1.rows); check("boundary_100800_ck101_size", 101808, b1.size);
        check("boundary_100800_ck102_aborts", true, b2.aborted); check("boundary_100800_ck102_size", 101808, b2.size);
        limit(100799L);
        WB b3 = wb(" AND ck < 100"), b4 = wb(" AND ck < 101");
        check("boundary_100799_ck100_completes", false, b3.aborted); check("boundary_100799_ck100_size", 100800, b3.size);
        check("boundary_100799_ck101_aborts", true, b4.aborted); check("boundary_100799_ck101_size", 100800, b4.size);

        // 5. above the data, unset
        limit(4194304L);
        WB ab = wb("");
        check("above_completes", false, ab.aborted); check("above_size", 2016000, ab.size); check("above_rows", N, ab.rows);
        check("above_resp_same", respWhole, ab.resp);
        limit(null);
        long t0 = tableAborts(), c0 = clientAborts();
        WB un = wb("");
        Net unNet = net("SELECT * FROM " + table() + " WHERE pk = 1", 0);
        check("unset_completes", false, un.aborted); check("unset_size", 2016000, un.size);
        check("unset_client_rows", N, unNet.rows);
        check("unset_table_meter_unchanged", t0, tableAborts()); check("unset_client_meter_unchanged", c0, clientAborts());
        check("unset_resp_same", respWhole, un.resp);

        // 6. frame
        QueryOptions o = QueryOptions.forInternalCalls(ConsistencyLevel.ONE, Collections.emptyList());
        long[] es = new long[2];
        int[] ns2 = { 100, 200 };
        for (int i = 0; i < 2; i++)
        {
            SelectStatement st = (SelectStatement) QueryProcessor.getStatement("SELECT * FROM " + table() + " WHERE pk = 1 AND ck < " + ns2[i], ClientState.forInternalCalls());
            ResultMessage.Rows rows = st.execute(QueryState.forInternalCalls(), o, Dispatcher.RequestTime.forImmediateExecution());
            es[i] = ResultMessage.codec.encodedSize(rows, ProtocolVersion.V5);
        }
        line("STAGE4 info frame encodedSize ck<100 " + es[0] + " ck<200 " + es[1]);
        check("frame_slope_102000", 102000, es[1] - es[0]);

        // 7. arms
        limit(262144L);
        Net p100 = net("SELECT * FROM " + table() + " WHERE pk = 1", 100);
        Net p1000 = net("SELECT * FROM " + table() + " WHERE pk = 1", 1000);
        line("STAGE4 info C1 paging100 " + p100 + " paging1000 " + p1000);
        check("C1_paging100_rows", N, p100.rows); check("C1_paging100_ok", true, p100.ok);
        checkTrue("C1_paging1000_aborts_code4", code4(p1000), String.valueOf(p1000));
        limit(65536L);
        Net cnt = net("SELECT count(*) FROM " + table() + " WHERE pk = 1", 0);
        line("STAGE4 info C2 count " + cnt + " value " + cnt.first);
        check("C2_count_ok", true, cnt.ok); check("C2_count_value", (long) N, cnt.first);
        DatabaseDescriptor.setReadThresholdsEnabled(false);
        t0 = tableAborts(); c0 = clientAborts();
        WB off = wb("");
        Net offNet = net("SELECT * FROM " + table() + " WHERE pk = 1", 0);
        check("C3_switch_off_completes", false, off.aborted); check("C3_switch_off_rows", N, off.rows);
        check("C3_switch_off_client_rows", N, offNet.rows);
        check("C3_switch_off_table_meter", t0, tableAborts()); check("C3_switch_off_client_meter", c0, clientAborts());
        DatabaseDescriptor.setReadThresholdsEnabled(true);
        String internal = "none";
        try { QueryProcessor.executeInternal("SELECT * FROM " + table() + " WHERE pk = 1"); }
        catch (ReadSizeAbortException e) { internal = "ReadSizeAbortException"; }
        catch (Throwable t) { internal = t.getClass().getSimpleName(); }
        check("C_internal_query_aborts", "ReadSizeAbortException", internal);
        limit(1L);
        c0 = clientAborts();
        Net sys = net("SELECT keyspace_name FROM system_schema.keyspaces", 0);
        limit(null);
        line("STAGE4 info C4 system_schema " + sys);
        checkTrue("C4_system_keyspace_aborts_code4", code4(sys), String.valueOf(sys));
        check("C4_client_meter_+1", c0 + 1, clientAborts());

        line("STAGE4 summary checks " + checks + " mismatches " + mismatches);
        Assert.assertEquals(0, mismatches);
    }
}
