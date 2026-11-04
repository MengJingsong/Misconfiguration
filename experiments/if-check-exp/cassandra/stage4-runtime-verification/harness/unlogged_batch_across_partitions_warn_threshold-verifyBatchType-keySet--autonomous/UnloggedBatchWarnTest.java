/*
 * Stage-4 harness, unit tier (B2) of unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous.
 * Copy into test/unit/org/apache/cassandra/cql3/ of a cassandra-5.0.9 working tree and run with unit-run.sh.
 * CQLTester's in-process native server, protocol V4 client, so BatchStatement.execute() (verifyBatchSize, verifyBatchType) runs.
 * Arms (B2c/B2e/B2h as amended 2026-10-26): for each threshold in {1, 10, 1000} (batch_size_warn = batch_size_fail = 1000 KiB):
 *   u50   unlogged batch of 50 inserts to 50 distinct keys, then the same again (NoSpamLogger check), then a fresh-table repeat
 *   u5    unlogged batch of 5 inserts to 5 keys
 *   l50   LOGGED batch of 50 inserts
 * Positive control: warn = fail = 1 KiB, threshold 10, the same 50-key batch: expected "Batch too large", count 0.
 * Output: STAGE4 lines to stdout and -Dstage4.out; EXPECTED lines state the prediction (B2f) and whether it held.
 * The test fails only on an instrument or set-up error (a known-answer check), never on a reading.
 */
package org.apache.cassandra.cql3;

import java.io.FileOutputStream;
import java.io.PrintStream;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;
import org.slf4j.LoggerFactory;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.datastax.driver.core.ResultSet;
import com.datastax.driver.core.exceptions.InvalidQueryException;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.statements.BatchStatement;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.transport.ProtocolVersion;
import org.apache.cassandra.utils.NoSpamLogger;

public class UnloggedBatchWarnTest extends CQLTester
{
    static PrintStream out;
    static int savedThreshold, savedWarnKiB, savedFailKiB;
    static ListAppender<ILoggingEvent> appender;
    static ch.qos.logback.classic.Logger batchLogger;
    static final ProtocolVersion V4 = ProtocolVersion.V4;

    @BeforeClass
    public static void setUp() throws Exception
    {
        String f = System.getProperty("stage4.out", "build/test/unlogged-batch-warn.out");
        out = new PrintStream(new FileOutputStream(f, true), true);
        savedThreshold = DatabaseDescriptor.getUnloggedBatchAcrossPartitionsWarnThreshold();
        savedWarnKiB = DatabaseDescriptor.getBatchSizeWarnThresholdInKiB();
        savedFailKiB = DatabaseDescriptor.getBatchSizeFailThresholdInKiB();
        batchLogger = (ch.qos.logback.classic.Logger) LoggerFactory.getLogger(BatchStatement.class);
        appender = new ListAppender<>();
        appender.start();
        batchLogger.addAppender(appender);
        requireNetwork();
    }

    @AfterClass
    public static void tearDown()
    {
        DatabaseDescriptor.getRawConfig().unlogged_batch_across_partitions_warn_threshold = savedThreshold;
        DatabaseDescriptor.setBatchSizeWarnThresholdInKiB(savedWarnKiB);
        DatabaseDescriptor.setBatchSizeFailThresholdInKiB(savedFailKiB);
        if (batchLogger != null && appender != null) batchLogger.detachAppender(appender);
        if (out != null) out.close();
    }

    static void say(String s)
    {
        System.out.println(s);
        out.println(s);
    }

    static boolean expect(String desc, boolean cond)
    {
        say("EXPECTED: " + desc + " - " + (cond ? "yes" : "NO"));
        return cond;
    }

    static void clearNoSpam() throws Exception
    {
        Method m = NoSpamLogger.class.getDeclaredMethod("clearWrappedLoggersForTest");
        m.setAccessible(true);
        m.invoke(null);
    }

    static String batch(String table, boolean logged, int n, int base)
    {
        StringBuilder sb = new StringBuilder(logged ? "BEGIN BATCH\n" : "BEGIN UNLOGGED BATCH\n");
        String v = "x".repeat(100);
        for (int i = 0; i < n; i++)
            sb.append("INSERT INTO ").append(KEYSPACE).append('.').append(table).append(" (k, v) VALUES (").append(base + i).append(", '").append(v).append("');\n");
        return sb.append("APPLY BATCH").toString();
    }

    static long logCount()
    {
        long c = 0;
        for (ILoggingEvent e : new ArrayList<>(appender.list))
            if (e.getLevel() == Level.WARN && e.getFormattedMessage().startsWith("Unlogged batch covering")) c++;
        return c;
    }

    static List<String> unloggedWarnings(ResultSet rs)
    {
        List<String> r = new ArrayList<>();
        for (String w : rs.getExecutionInfo().getWarnings())
            if (w.startsWith("Unlogged batch covering")) r.add(w);
        return r;
    }

    static class Reading
    {
        int warns; long logs; long count; long memtable; String error = "";
    }

    Reading run(String table, boolean logged, int n, int base) throws Throwable
    {
        Reading r = new Reading();
        long l0 = logCount();
        try
        {
            ResultSet rs = executeNet(V4, batch(table, logged, n, base));
            r.warns = unloggedWarnings(rs).size();
        }
        catch (InvalidQueryException e)
        {
            r.error = e.getMessage();
        }
        r.logs = logCount() - l0;
        r.count = executeNet(V4, "SELECT count(*) FROM " + KEYSPACE + "." + table).one().getLong(0);
        ColumnFamilyStore cfs = getColumnFamilyStore(KEYSPACE, table);
        r.memtable = cfs.metric.allMemtablesLiveDataSize.getValue();
        return r;
    }

    static void print(String arm, String what, Reading r)
    {
        say("STAGE4 reading arm=" + arm + " " + what + " client_warnings=" + r.warns + " log_warns=" + r.logs + " count=" + r.count
            + " memtable_live_bytes=" + r.memtable + (r.error.isEmpty() ? "" : " error=\"" + r.error + "\""));
    }

    @Test
    public void unloggedBatchWarning() throws Throwable
    {
        say("STAGE4 info default threshold=" + savedThreshold + " warn_kib=" + savedWarnKiB + " fail_kib=" + savedFailKiB + " heap_max=" + Runtime.getRuntime().maxMemory());
        long[] memtable50 = new long[3];
        int[] thresholds = { 1, 10, 1000 };
        for (int ti = 0; ti < thresholds.length; ti++)
        {
            int t = thresholds[ti];
            DatabaseDescriptor.getRawConfig().unlogged_batch_across_partitions_warn_threshold = t;
            DatabaseDescriptor.setBatchSizeWarnThresholdInKiB(1000);
            DatabaseDescriptor.setBatchSizeFailThresholdInKiB(1000);
            Assert.assertEquals("knob read back", t, DatabaseDescriptor.getUnloggedBatchAcrossPartitionsWarnThreshold());
            say("STAGE4 arm t" + t + " begin threshold=" + DatabaseDescriptor.getUnloggedBatchAcrossPartitionsWarnThreshold()
                + " warn_kib=" + DatabaseDescriptor.getBatchSizeWarnThresholdInKiB() + " fail_kib=" + DatabaseDescriptor.getBatchSizeFailThresholdInKiB());
            clearNoSpam();
            System.gc();
            long heap0 = Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory();
            String t50 = createTable("CREATE TABLE %s (k int PRIMARY KEY, v text)");
            Reading a = run(t50, false, 50, 0);
            print("t" + t, "u50-first", a);
            Reading a2 = run(t50, false, 50, 1000);
            print("t" + t, "u50-second-within-a-minute", a2);
            long heap1 = Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory();
            say("STAGE4 heap arm=t" + t + " used_before=" + heap0 + " used_after=" + heap1 + " (coarse, no GC after)");
            memtable50[ti] = a.memtable;
            boolean warnsExpected = 50 > t;
            if (ti == 0)
            {
                // first-trigger check: at threshold 1 the 50-key batch must warn, or the instrument cannot see the branch
                boolean fired = expect("first trigger: threshold 1, 50 keys -> client warning present and one log line", a.warns == 1 && a.logs == 1);
                Assert.assertTrue("first-trigger check failed: the warning branch did not fire", fired);
            }
            expect("t" + t + " u50: client warnings " + (warnsExpected ? "1" : "0") + " (50 keys " + (warnsExpected ? ">" : "<=") + " " + t + ")", a.warns == (warnsExpected ? 1 : 0));
            expect("t" + t + " u50: log lines " + (warnsExpected ? "1" : "0"), a.logs == (warnsExpected ? 1 : 0));
            expect("t" + t + " u50: count(*) = 50", a.count == 50);
            expect("t" + t + " u50 second batch within a minute: client warnings " + (warnsExpected ? "1" : "0") + ", log lines 0 (NoSpamLogger)",
                   a2.warns == (warnsExpected ? 1 : 0) && a2.logs == 0 && a2.count == 100);
            clearNoSpam();
            String t5 = createTable("CREATE TABLE %s (k int PRIMARY KEY, v text)");
            Reading b = run(t5, false, 5, 0);
            print("t" + t, "u5", b);
            boolean w5 = 5 > t;
            expect("t" + t + " u5: client warnings " + (w5 ? "1" : "0") + ", count 5", b.warns == (w5 ? 1 : 0) && b.count == 5);
            clearNoSpam();
            String tl = createTable("CREATE TABLE %s (k int PRIMARY KEY, v text)");
            Reading c = run(tl, true, 50, 0);
            print("t" + t, "l50-logged", c);
            expect("t" + t + " l50 (LOGGED): no unlogged warning, count 50", c.warns == 0 && c.logs == 0 && c.count == 50);
            say("STAGE4 arm t" + t + " end");
        }
        long lo = Math.min(memtable50[0], Math.min(memtable50[1], memtable50[2]));
        long hi = Math.max(memtable50[0], Math.max(memtable50[1], memtable50[2]));
        expect("memtable live bytes after the first 50-key batch equal within 5% across thresholds (" + memtable50[0] + ", " + memtable50[1] + ", " + memtable50[2] + ")",
               lo > 0 && hi <= lo * 1.05);

        // positive control: the size check, reachable only above the warn threshold (amendment A1)
        DatabaseDescriptor.getRawConfig().unlogged_batch_across_partitions_warn_threshold = 10;
        DatabaseDescriptor.setBatchSizeWarnThresholdInKiB(1);
        DatabaseDescriptor.setBatchSizeFailThresholdInKiB(1);
        say("STAGE4 arm control begin threshold=10 warn_kib=" + DatabaseDescriptor.getBatchSizeWarnThresholdInKiB() + " fail_kib=" + DatabaseDescriptor.getBatchSizeFailThresholdInKiB());
        clearNoSpam();
        String tc = createTable("CREATE TABLE %s (k int PRIMARY KEY, v text)");
        Reading k = run(tc, false, 50, 0);
        print("control", "u50-size-control", k);
        expect("control: 50-key batch rejected with \"Batch too large\", count 0", k.error.contains("Batch too large") && k.count == 0);
        say("STAGE4 arm control end");
    }
}
