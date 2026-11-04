/*
 * Stage 4, unit tier (B2) of prepared_statements_cache_size-loadpreparedstatements-preparedbytesloaded--autonomous. Not upstream.
 * Copy into test/unit/org/apache/cassandra/cql3/ of a copy of cassandra-5.0.9 and run, one JVM per cell (unit-run.sh):
 *   ant testsome -Dtest.name=org.apache.cassandra.cql3.PstmtPreloadThresholdTest \
 *     -Dtest.jvm.args="-Dcassandra.config=file://<yaml> -Dstage4.out=<file> -Dstage4.arm=<A|B> -Dstage4.factor=<f>"
 * Arm A = the unmodified copy; arm B = the copy with the literal 1.1 in SystemKeyspace.loadPreparedStatements patched to 1000.0.
 * The rows of system.prepared_statements are written DIRECTLY (SystemKeyspace.writePreparedStatement), not through PREPARE, because
 * eviction deletes a row (QueryProcessor.evictPreparedStatement) so a PREPARE workload never leaves more than ~1 x cap on disk.
 */
package org.apache.cassandra.cql3;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.util.Map;

import org.junit.Test;
import org.slf4j.LoggerFactory;

import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.SystemKeyspace;
import org.apache.cassandra.service.ClientState;
import org.apache.cassandra.utils.MD5Digest;
import org.apache.cassandra.utils.ObjectSizes;

public class PstmtPreloadThresholdTest extends CQLTester
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
        for (int i = 0; i < 3; i++)
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

    static long sumPstmntSize()
    {
        long sum = 0;
        for (QueryHandler.Prepared p : QueryProcessor.instance.getPreparedStatements().values())
            sum += Math.max(0, p.pstmntSize);
        return sum;
    }

    String q(String tag)
    {
        return "SELECT v FROM " + KEYSPACE + "." + currentTable() + " WHERE k = ? /* " + tag + " */";
    }

    @Test
    public void run() throws Throwable
    {
        String arm = System.getProperty("stage4.arm", "?");
        double factor = Double.parseDouble(System.getProperty("stage4.factor", "3"));
        String label = arm + "-cap" + DatabaseDescriptor.getPreparedStatementsCacheSizeMiB() + "-f" + (int) factor + "-r" + System.getProperty("stage4.rep", "1");
        long mib = DatabaseDescriptor.getPreparedStatementsCacheSizeMiB();
        long cap = mib * 1024 * 1024;
        createTable("CREATE TABLE %s (k text PRIMARY KEY, v int)");
        ClientState cs = ClientState.forInternalCalls();
        ColumnFamilyStore pcfs = Keyspace.open("system").getColumnFamilyStore("prepared_statements");
        com.sun.management.ThreadMXBean tmx = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
        line("STAGE4 run label=" + label + " cap_mib=" + mib + " cap_bytes=" + cap + " maxMemory=" + Runtime.getRuntime().maxMemory()
             + " threshold_if_1.1=" + (long) (cap * 1.1));

        // calibration: pstmntSize of one statement as the preload callback computes it (parseAndPrepare(query, cs, false) -> measure=true)
        QueryHandler.Prepared cal = QueryProcessor.parseAndPrepare(q("cal"), cs, false);
        long s = cal.pstmntSize;
        check(label + " pstmntSize-populated", s > 0, "pstmntSize=" + s);
        QueryProcessor.clearPreparedStatements(false);

        int n = (int) Math.ceil(factor * cap / s);
        long ts = System.currentTimeMillis() * 1000;
        for (int i = 0; i < n; i++)
        {
            String query = q("u" + i);
            SystemKeyspace.writePreparedStatement(null, MD5Digest.compute(query), query, ts + i);
        }
        pcfs.forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
        long rowsBefore = execute("SELECT count(*) FROM system.prepared_statements").one().getLong("count");
        check(label + " rows-on-disk==n", rowsBefore == n, "rows=" + rowsBefore + " n=" + n);
        check(label + " cache-empty", QueryProcessor.preparedStatementsCount() == 0, "count=" + QueryProcessor.preparedStatementsCount());
        line("STAGE4 plan label=" + label + " s=" + s + " n=" + n + " offered_pstmntSize=" + (long) n * s + " offered/cap=" + String.format("%.2f", (double) n * s / cap));

        ListAppender<ILoggingEvent> app = new ListAppender<>();
        app.start();
        ch.qos.logback.classic.Logger lg = (ch.qos.logback.classic.Logger) LoggerFactory.getLogger(SystemKeyspace.class);
        lg.addAppender(app);

        long h0 = usedAfterGc();
        long m0 = pcfs.metric.allMemtablesOnHeapDataSize.getValue();
        long ev0 = QueryProcessor.metrics.preparedStatementsEvicted.getCount();
        long a0 = tmx.getThreadAllocatedBytes(Thread.currentThread().getId());
        long t0 = System.nanoTime();
        int loaded = QueryProcessor.instance.preloadPreparedStatements(100);
        long ms = (System.nanoTime() - t0) / 1000000;
        long a1 = tmx.getThreadAllocatedBytes(Thread.currentThread().getId());
        lg.detachAppender(app);
        boolean warn = false;
        for (ILoggingEvent e : app.list)
            if (e.getFormattedMessage().contains("Detected prepared statement cache filling up"))
                warn = true;

        long evicted = QueryProcessor.metrics.preparedStatementsEvicted.getCount() - ev0;
        int count = QueryProcessor.preparedStatementsCount();
        long sum = sumWeights();
        long sumP = sumPstmntSize();
        long deep = ObjectSizes.measureDeep(QueryProcessor.instance.getPreparedStatements());
        long m1 = pcfs.metric.allMemtablesOnHeapDataSize.getValue();
        long h1 = usedAfterGc();
        long rowsAfter = execute("SELECT count(*) FROM system.prepared_statements").one().getLong("count");
        line("STAGE4 final label=" + label + " arm=" + arm + " cap=" + cap + " n=" + n + " s=" + s + " warn=" + warn + " loaded=" + loaded + " ms=" + ms
             + " allocMB=" + (a1 - a0) / 1048576 + " count=" + count + " evicted=" + evicted + " sumWeights=" + sum + " sumPstmntSize=" + sumP
             + " measureDeepMap=" + deep + " rowsAfter=" + rowsAfter + " memtableBefore=" + m0 + " memtableAfter=" + m1 + " memtableDelta=" + (m1 - m0)
             + " liveHeapBefore=" + h0 + " liveHeapAfter=" + h1 + " liveDelta=" + (h1 - h0)
             + " liveDeltaMinusMemtable=" + ((h1 - h0) - (m1 - m0)));
        check(label + " sum<=cap", sum <= cap, "sum=" + sum + " cap=" + cap);
        check(label + " count+evicted==loaded", count + evicted == loaded, "count=" + count + " evicted=" + evicted + " loaded=" + loaded);
        check(label + " loaded-bound", arm.equals("B") ? loaded == n : (loaded <= n), "loaded=" + loaded + " n=" + n);
        line("STAGE4 done label=" + label + " mismatches=" + mismatches);
    }
}
