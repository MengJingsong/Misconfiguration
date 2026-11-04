/*
 * Stage-4 harness, unit tier (B2) of default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous (frozen sha256 in the results file, section 1).
 * Not part of Cassandra. Copied into test/unit/org/apache/cassandra/db/filter/ of a stage-4 working tree by unit-run.sh and run with
 * ant testsome, once per value of SelectStatement.DEFAULT_PAGE_SIZE (the compile-time constant edited in the tree). Asserts nothing:
 * prints DPS lines to build/test/dps-unit.txt (and stdout). Adapted from GroupByRowLimitTest of group-by-row-limit-incrementRowCount-rowsCounted--autonomous.
 *
 *  L  limits string of the built query (client page size unset / 250 / plain aggregate), constant read by reflection (not inlined)
 *  W  white-box counter: the statement's DataLimits.newCounter(..) over a raw read of the first sub-page; counted(), rowsCounted(), isDone()
 *  B  serialised size of the first sub-read's data response (count(v) and, as a control for amendment U1, count(*))
 *  E  end to end: the real AggregationQueryPager over a counting QueryPager wrapper: rows per sub-read, sub-read count, allocated bytes of the
 *     calling thread per sub-read (amendment U3) and over the drain
 *  P  plain aggregate (no GROUP BY): limits, rows of the raw read (negative control)
 */
package org.apache.cassandra.db.filter;

import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;

import org.junit.Test;

import org.apache.cassandra.cql3.CQLStatement;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.cql3.QueryProcessor;
import org.apache.cassandra.cql3.statements.SelectStatement;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.db.ReadCommand;
import org.apache.cassandra.db.ReadExecutionController;
import org.apache.cassandra.db.ReadQuery;
import org.apache.cassandra.db.ReadResponse;
import org.apache.cassandra.net.MessagingService;
import org.apache.cassandra.db.partitions.PartitionIterator;
import org.apache.cassandra.db.partitions.UnfilteredPartitionIterator;
import org.apache.cassandra.db.partitions.UnfilteredPartitionIterators;
import org.apache.cassandra.db.rows.BaseRowIterator;
import org.apache.cassandra.db.rows.Row;
import org.apache.cassandra.db.rows.RowIterator;
import org.apache.cassandra.db.transform.Transformation;
import org.apache.cassandra.service.ClientState;
import org.apache.cassandra.service.pager.AggregationQueryPager;
import org.apache.cassandra.service.pager.PagingState;
import org.apache.cassandra.service.pager.QueryPager;
import org.apache.cassandra.transport.Dispatcher;
import org.apache.cassandra.transport.ProtocolVersion;
import org.apache.cassandra.utils.FBUtilities;

public class DefaultPageSizeProbeTest extends CQLTester
{
    static final int NONE = DataLimits.NO_LIMIT;
    static final int GROUP_ROWS = 200_000;    // rows of the single partition; c1 = i/20000 (10 groups)
    static final int BLOB = 1024;
    static final int[] PS = { -1, 250 };   // -1 = client page size unset (the constant applies)
    static final int REPS = 3;                // the first is discarded
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

    PrintWriter out;

    void say(String s)
    {
        out.println(s);
        out.flush();
        System.out.println(s);
    }

    static String ls(int l) { return l == NONE ? "none" : Integer.toString(l); }

    static class Stats
    {
        List<Integer> rows = new ArrayList<>();
        List<Integer> groups = new ArrayList<>();
        List<Long> alloc = new ArrayList<>();
        void record(int r, int g, long a) { rows.add(r); groups.add(g); alloc.add(a); }
        /** mean allocated bytes over sub-reads with the maximum row count */
        double meanAllocFull() { int m = maxRows(); double t = 0; int n = 0; for (int i = 0; i < rows.size(); i++) if (rows.get(i) == m) { t += alloc.get(i); n++; } return n == 0 ? 0 : t / n; }
        long totalRows() { long n = 0; for (int r : rows) n += r; return n; }
        long totalGroups() { long n = 0; for (int g : groups) n += g; return n; }
        int maxRows() { int m = 0; for (int r : rows) m = Math.max(m, r); return m; }
        int nonEmpty() { int n = 0; for (int r : rows) if (r > 0) n++; return n; }
        int atMax() { int n = 0, m = maxRows(); for (int r : rows) if (r == m) n++; return n; }
    }

    /** Counts rows leaving a sub-page and records the sub-page when it is closed. */
    static class CountingPager implements QueryPager
    {
        final QueryPager inner;
        final Stats st;

        CountingPager(QueryPager inner, Stats st) { this.inner = inner; this.st = st; }

        public PartitionIterator fetchPage(int pageSize, ConsistencyLevel c, ClientState s, Dispatcher.RequestTime t)
        {
            throw new UnsupportedOperationException();
        }

        public ReadExecutionController executionController() { return inner.executionController(); }

        public PartitionIterator fetchPageInternal(int pageSize, ReadExecutionController ec)
        {
            final int before = inner.maxRemaining();
            final int[] rows = { 0 };
            final long a0 = TMX.getThreadAllocatedBytes(Thread.currentThread().getId());
            PartitionIterator it = inner.fetchPageInternal(pageSize, ec);
            Transformation<BaseRowIterator<Row>> t = new Transformation<BaseRowIterator<Row>>()
            {
                protected BaseRowIterator<Row> applyToPartition(BaseRowIterator<Row> p) { return Transformation.apply((RowIterator) p, this); }
                protected Row applyToRow(Row r) { rows[0]++; return r; }
                protected void onClose() { st.record(rows[0], before - inner.maxRemaining(), TMX.getThreadAllocatedBytes(Thread.currentThread().getId()) - a0); }
            };
            return Transformation.apply(it, t);
        }

        public boolean isExhausted() { return inner.isExhausted(); }
        public int maxRemaining() { return inner.maxRemaining(); }
        public PagingState state() { return inner.state(); }
        public boolean isTopK() { return inner.isTopK(); }
        public QueryPager withUpdatedLimit(DataLimits newLimits) { return new CountingPager(inner.withUpdatedLimit(newLimits), st); }
    }

    /** A single-partition SELECT yields a Group of one command; a range SELECT yields the command itself. */
    static ReadCommand cmdOf(ReadQuery rq)
    {
        if (rq instanceof org.apache.cassandra.db.SinglePartitionReadCommand.Group)
        {
            org.apache.cassandra.db.SinglePartitionReadCommand.Group g = (org.apache.cassandra.db.SinglePartitionReadCommand.Group) rq;
            if (g.queries.size() != 1) throw new IllegalStateException("group of " + g.queries.size());
            return g.queries.get(0);
        }
        return (ReadCommand) rq;
    }

    SelectStatement stmt(String cql)
    {
        CQLStatement s = QueryProcessor.getStatement(cql, ClientState.forInternalCalls());
        return (SelectStatement) s;
    }

    QueryOptions opts(int pageSize)
    {
        return QueryOptions.create(ConsistencyLevel.ONE, Collections.emptyList(), false, pageSize, null, null, ProtocolVersion.CURRENT, KEYSPACE);
    }

    /**
     * E: drain the real pager, one fresh pager per top-level page built from the previous page's PagingState, as the request path does
     * (a client page = one request). Returns {rowsTotal, subpages, maxRowsPerSubpage, groupsTotal, allocBytes, pages, lastSubpageRows, rowsSeen}
     */
    long[] endToEnd(String cql, int p, boolean groupBy) throws Throwable
    {
        SelectStatement ss = stmt(cql);
        Stats st = new Stats();
        PagingState ps = null;
        long rowsSeen = 0;
        int pages = 0;
        long a0 = TMX.getThreadAllocatedBytes(Thread.currentThread().getId());
        while (true)
        {
            ReadQuery rq = ss.getQuery(opts(p), FBUtilities.nowInSeconds());
            QueryPager sub = rq.getPager(ps, ProtocolVersion.CURRENT);
            QueryPager pager = groupBy ? new AggregationQueryPager(new CountingPager(sub, st), rq.limits()) : new CountingPager(sub, st);
            try (ReadExecutionController ec = pager.executionController();
                 PartitionIterator it = pager.fetchPageInternal(p, ec))
            {
                while (it.hasNext())
                    try (RowIterator ri = it.next())
                    {
                        while (ri.hasNext()) { ri.next(); rowsSeen++; }
                    }
            }
            pages++;
            if (pager.isExhausted() || !groupBy)
                break;
            ps = pager.state();
        }
        long a1 = TMX.getThreadAllocatedBytes(Thread.currentThread().getId());
        int last = st.rows.isEmpty() ? -1 : st.rows.get(st.rows.size() - 1);
        return new long[]{ st.totalRows(), st.rows.size(), st.maxRows(), st.totalGroups(), a1 - a0, pages, last, rowsSeen, st.nonEmpty(), st.atMax(), (long) st.meanAllocFull() };
    }

    /** W: the statement's counter over a raw local read; returns {counted, rowsCounted, isDone?1:0, rowsDrained} */
    long[] whiteBox(String cql, int p) throws Throwable
    {
        SelectStatement ss = stmt(cql);
        long now = FBUtilities.nowInSeconds();
        ReadQuery rq = ss.getQuery(opts(p), now);
        ReadCommand cmd = cmdOf(rq).withUpdatedLimit(DataLimits.NONE);
        DataLimits.Counter c = rq.limits().newCounter(now, false, cmd.selectsFullPartition(), cmd.metadata().enforceStrictLiveness());
        long n = 0;
        try (ReadExecutionController ec = cmd.executionController();
             UnfilteredPartitionIterator raw = cmd.executeLocally(ec);
             PartitionIterator it = c.applyTo(UnfilteredPartitionIterators.filter(raw, now)))
        {
            while (it.hasNext())
                try (RowIterator ri = it.next())
                {
                    while (ri.hasNext()) { ri.next(); n++; }
                }
        }
        return new long[]{ c.counted(), c.rowsCounted(), c.isDone() ? 1 : 0, n };
    }

    /** B: serialised size of the data response of the first sub-read of the command built for this statement. Returns {bytes, rows}. */
    long[] firstReadBytes(String cql, int p) throws Throwable
    {
        SelectStatement ss = stmt(cql);
        ReadQuery rq = ss.getQuery(opts(p), FBUtilities.nowInSeconds());
        ReadCommand cmd = cmdOf(rq);
        try (ReadExecutionController ec = cmd.executionController();
             UnfilteredPartitionIterator it = cmd.executeLocally(ec))
        {
            ReadResponse resp = cmd.createResponse(it, ec.getRepairedDataInfo());
            long sz = ReadResponse.serializer.serializedSize(resp, MessagingService.current_version);
            return new long[]{ sz };
        }
    }

    static String pl(int p) { return p < 0 ? "unset" : Integer.toString(p); }

    String limitsOf(String cql, int p)
    {
        return "'" + stmt(cql).getQuery(opts(p), FBUtilities.nowInSeconds()).limits().toString() + "'";
    }

    @Test
    public void probe() throws Throwable
    {
        new java.io.File("build/test").mkdirs();
        out = new PrintWriter("build/test/dps-unit.txt");
        int constant = SelectStatement.class.getField("DEFAULT_PAGE_SIZE").getInt(null);   // reflection: the value stored in SelectStatement.class
        say("DPS START constant=" + constant + " rows=" + GROUP_ROWS + " bytes_per_value=" + BLOB + " heap_max=" + Runtime.getRuntime().maxMemory());
        Random rnd = new Random(39);
        String[] vals = new String[64];
        for (int k = 0; k < vals.length; k++)
        {
            StringBuilder sb = new StringBuilder(BLOB);
            for (int j = 0; j < BLOB; j++) sb.append((char) ('a' + rnd.nextInt(26)));
            vals[k] = sb.toString();
        }
        String s = createTable("CREATE TABLE %s (pk int, c1 int, c2 int, v text, PRIMARY KEY (pk, c1, c2))");
        for (int i = 0; i < GROUP_ROWS; i++)
            execute("INSERT INTO " + KEYSPACE + "." + s + " (pk, c1, c2, v) VALUES (1, ?, ?, ?)", i / 20_000, i % 20_000, vals[i & 63]);
        flush(KEYSPACE, s);
        say("DPS DATA S=" + s);
        String t = KEYSPACE + "." + s;
        String q = "SELECT pk, c1, count(v) FROM " + t + " WHERE pk = 1 GROUP BY pk, c1";
        String qstar = "SELECT pk, c1, count(*) FROM " + t + " WHERE pk = 1 GROUP BY pk, c1";
        String qp = "SELECT count(v) FROM " + t + " WHERE pk = 1";

        // L: limits strings
        say("DPS L constant=" + constant + " gb_unset=" + limitsOf(q, -1) + " gb_250=" + limitsOf(q, 250) + " plain_unset=" + limitsOf(qp, -1) + " plain_250=" + limitsOf(qp, 250));

        for (int p : PS)
        {
            long[] w = whiteBox(q, p);
            long[] bb = firstReadBytes(q, p);
            long[] bs = firstReadBytes(qstar, p);
            say("DPS W p=" + pl(p) + " groups=" + w[0] + " rowsCounted=" + w[1] + " isDone=" + (w[2] == 1) + " rowsDrained=" + w[3] + " firstReadBytes=" + bb[0] + " firstReadBytesCountStar=" + bs[0]);
            for (int rep = 1; rep <= REPS; rep++)
            {
                System.gc();
                long[] e = endToEnd(q, p, true);
                say("DPS E p=" + pl(p) + " rep=" + rep + (rep == 1 ? " (warm-up)" : "")
                    + " rows=" + e[0] + " subpages=" + e[1] + " maxRowsPerSubpage=" + e[2] + " groups=" + e[3]
                    + " allocBytes=" + e[4] + " pages=" + e[5] + " lastSubpageRows=" + e[6] + " rowsSeen=" + e[7] + " nonEmpty=" + e[8] + " atMax=" + e[9] + " meanAllocFullSubread=" + e[10]);
            }
        }
        // P: plain aggregate, no GROUP BY: no row limit, one raw read of all rows (negative control)
        for (int p : new int[]{ -1, 250 })
        {
            long[] w = whiteBox(qp, p);
            say("DPS P p=" + pl(p) + " limits=" + limitsOf(qp, p) + " rowsCounted=" + w[1] + " isDone=" + (w[2] == 1) + " rowsDrained=" + w[3]);
        }
        say("DPS END");
        out.close();
    }
}
