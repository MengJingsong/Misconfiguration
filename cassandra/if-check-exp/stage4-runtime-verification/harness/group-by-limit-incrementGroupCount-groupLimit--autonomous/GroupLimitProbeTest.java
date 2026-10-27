/*
 * Stage-4 harness, unit tier (B2) of group-by-limit-incrementGroupCount-groupLimit--autonomous (frozen sha256 in the results file, section 1).
 * Not part of Cassandra. Copied into test/unit/org/apache/cassandra/db/filter/ of a stage-4 working tree by unit-run.sh and run with
 * ant testsome. Asserts nothing about the result: it prints L79 lines to build/test/l79-unit.txt (and stdout).
 *
 * Instruments (audit amendment A8 / B2d):
 *  W  white-box counter: the statement's own DataLimits.newCounter(..) applied to a raw (unlimited) local read; after the pass
 *     counter.counted() (groups), rowsCounted(), isDone() are read (one sub-page of P rows).
 *  E  end to end: the statement's real AggregationQueryPager over a counting QueryPager wrapper: rows per sub-page (rows that left
 *     the counter), groups counted per sub-page (drop of maxRemaining()), number of sub-pages, and exact allocated bytes of the
 *     calling thread (com.sun.management.ThreadMXBean), around the whole drain. The local read runs on the calling thread.
 *  C  control: SELECT * ... LIMIT L (no GROUP BY) read through its pager with page size L.
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
import org.apache.cassandra.db.SinglePartitionReadCommand;
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

public class GroupLimitProbeTest extends CQLTester
{
    static final int NONE = DataLimits.NO_LIMIT;
    static final int S_ROWS = 1_000_000;      // rows of the single partition of S (read as slices ck < r)
    static final int[] RS = { 1000, 100_000, 1_000_000 };
    static final int M_PARTS = 1000;          // dataset M: M_PARTS partitions x M_ROWS rows
    static final int M_ROWS = 1000;
    static final int BLOB = 100;
    static final int[] GS = { 1, 10, 1000 };
    static final int[] PS = { 100, 10_000 };
    static final int REPS = 3;                // the first is discarded
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

    PrintWriter out;

    static List<java.lang.management.MemoryPoolMXBean> heapPools()
    {
        List<java.lang.management.MemoryPoolMXBean> r = new ArrayList<>();
        for (java.lang.management.MemoryPoolMXBean p : ManagementFactory.getMemoryPoolMXBeans())
            if (p.getType() == java.lang.management.MemoryType.HEAP)       // eden, survivor and old pools of whichever collector the test JVM runs (CMS in the unit-test JVM options)
                r.add(p);
        return r;
    }

    static void resetPeaks() { for (java.lang.management.MemoryPoolMXBean p : heapPools()) p.resetPeakUsage(); }

    static long peakPools() { long n = 0; for (java.lang.management.MemoryPoolMXBean p : heapPools()) n += p.getPeakUsage().getUsed(); return n; }

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
        void record(int r, int g) { rows.add(r); groups.add(g); }
        long totalRows() { long n = 0; for (int r : rows) n += r; return n; }
        long totalGroups() { long n = 0; for (int g : groups) n += g; return n; }
        int maxRows() { int m = 0; for (int r : rows) m = Math.max(m, r); return m; }
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
            PartitionIterator it = inner.fetchPageInternal(pageSize, ec);
            Transformation<BaseRowIterator<Row>> t = new Transformation<BaseRowIterator<Row>>()
            {
                protected BaseRowIterator<Row> applyToPartition(BaseRowIterator<Row> p) { return Transformation.apply((RowIterator) p, this); }
                protected Row applyToRow(Row r) { rows[0]++; return r; }
                protected void onClose() { st.record(rows[0], before - inner.maxRemaining()); }
            };
            return Transformation.apply(it, t);
        }

        public boolean isExhausted() { return inner.isExhausted(); }
        public int maxRemaining() { return inner.maxRemaining(); }
        public PagingState state() { return inner.state(); }
        public boolean isTopK() { return inner.isTopK(); }
        public QueryPager withUpdatedLimit(DataLimits newLimits) { return new CountingPager(inner.withUpdatedLimit(newLimits), st); }
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
     * (a client page = one request). Returns {rowsTotal, subpages, maxRowsPerSubpage, groupsTotal, allocBytes, pages, lastSubpageRows, rowsSeen, peakPools}
     */
    long[] endToEnd(String cql, int p, boolean groupBy) throws Throwable
    {
        SelectStatement ss = stmt(cql);
        Stats st = new Stats();
        PagingState ps = null;
        long rowsSeen = 0;
        int pages = 0;
        resetPeaks();
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
        long peak = peakPools();
        int last = st.rows.isEmpty() ? -1 : st.rows.get(st.rows.size() - 1);
        return new long[]{ st.totalRows(), st.rows.size(), st.maxRows(), st.totalGroups(), a1 - a0, pages, last, rowsSeen, peak };
    }

    /** W: the statement's counter over a raw local read; returns {counted, rowsCounted, isDone?1:0, rowsDrained} */
    long[] whiteBox(String cql, int p) throws Throwable
    {
        SelectStatement ss = stmt(cql);
        long now = FBUtilities.nowInSeconds();
        ReadQuery rq = ss.getQuery(opts(p), now);
        ReadCommand base = rq instanceof SinglePartitionReadCommand.Group ? ((SinglePartitionReadCommand.Group) rq).queries.get(0) : (ReadCommand) rq;
        ReadCommand cmd = base.withUpdatedLimit(DataLimits.NONE);
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

    @Test
    public void probe() throws Throwable
    {
        new java.io.File("build/test").mkdirs();
        out = new PrintWriter("build/test/l79-unit.txt");
        say("L79 START sRows=" + S_ROWS + " mParts=" + M_PARTS + " mRows=" + M_ROWS + " blob=" + BLOB + " heap_max=" + Runtime.getRuntime().maxMemory());
        Random rnd = new Random(79);
        String s = createTable("CREATE TABLE %s (pk int, ck int, v blob, PRIMARY KEY (pk, ck))");   // S: one partition, one group (read as slices)
        String m = createTable("CREATE TABLE %s (pk int, ck int, v blob, PRIMARY KEY (pk, ck))");   // M: M_PARTS groups of M_ROWS rows
        byte[] b = new byte[BLOB];
        for (int i = 0; i < S_ROWS; i++)
        {
            rnd.nextBytes(b);
            execute("INSERT INTO " + KEYSPACE + "." + s + " (pk, ck, v) VALUES (1, ?, ?)", i, ByteBuffer.wrap(b.clone()));
            if ((i + 1) % 200_000 == 0) flush(KEYSPACE, s);
        }
        for (int pk = 0; pk < M_PARTS; pk++)
            for (int ck = 0; ck < M_ROWS; ck++)
            {
                rnd.nextBytes(b);
                execute("INSERT INTO " + KEYSPACE + "." + m + " (pk, ck, v) VALUES (?, ?, ?)", pk, ck, ByteBuffer.wrap(b.clone()));
            }
        flush(KEYSPACE, s);
        flush(KEYSPACE, m);
        say("L79 DATA S=" + s + " M=" + m);

        // M first (its white-box L=1 P=100 is the instrument / first-trigger check), then S
        for (int p : PS)
            for (int g : GS)
            {
                String q = "SELECT pk, count(*) FROM " + KEYSPACE + "." + m + " GROUP BY pk LIMIT " + g;
                long[] w = whiteBox(q, p);
                say("L79 W ds=M r=" + M_ROWS + " g=" + g + " P=" + p + " groups=" + w[0] + " rowsCounted=" + w[1] + " isDone=" + (w[2] == 1) + " rowsDrained=" + w[3]);
                for (int rep = 1; rep <= REPS; rep++)
                {
                    System.gc();
                    long[] e = endToEnd(q, p, true);
                    say("L79 E ds=M r=" + M_ROWS + " g=" + g + " P=" + p + " rep=" + rep + (rep == 1 ? " (warm-up)" : "")
                        + " rows=" + e[0] + " subpages=" + e[1] + " maxRowsPerSubpage=" + e[2] + " groups=" + e[3]
                        + " allocBytes=" + e[4] + " pages=" + e[5] + " lastSubpageRows=" + e[6] + " rowsSeen=" + e[7] + " peakPools=" + e[8]);
                }
            }
        for (int r : RS)
            for (int p : PS)
                for (int g : GS)
                {
                    String q = "SELECT pk, count(*) FROM " + KEYSPACE + "." + s + " WHERE pk = 1 AND ck < " + r + " GROUP BY pk LIMIT " + g;
                    long[] w = whiteBox(q, p);
                    say("L79 W ds=S r=" + r + " g=" + g + " P=" + p + " groups=" + w[0] + " rowsCounted=" + w[1] + " isDone=" + (w[2] == 1) + " rowsDrained=" + w[3]);
                    for (int rep = 1; rep <= REPS; rep++)
                    {
                        System.gc();
                        long[] e = endToEnd(q, p, true);
                        say("L79 E ds=S r=" + r + " g=" + g + " P=" + p + " rep=" + rep + (rep == 1 ? " (warm-up)" : "")
                            + " rows=" + e[0] + " subpages=" + e[1] + " maxRowsPerSubpage=" + e[2] + " groups=" + e[3]
                            + " allocBytes=" + e[4] + " pages=" + e[5] + " lastSubpageRows=" + e[6] + " rowsSeen=" + e[7] + " peakPools=" + e[8]);
                    }
                }
        // C: positive control, no GROUP BY, rows read bounded by LIMIT n
        String t = KEYSPACE + "." + s;
        for (int n : new int[]{ 100, 1000, 10_000 })
            for (int rep = 1; rep <= REPS; rep++)
            {
                System.gc();
                long[] e = endToEnd("SELECT * FROM " + t + " WHERE pk = 1 LIMIT " + n, n, false);
                say("L79 C ds=S n=" + n + " rep=" + rep + (rep == 1 ? " (warm-up)" : "") + " rows=" + e[0] + " allocBytes=" + e[4] + " subpages=" + e[1] + " peakPools=" + e[8]);
            }
        say("L79 END");
        out.close();
    }
}
