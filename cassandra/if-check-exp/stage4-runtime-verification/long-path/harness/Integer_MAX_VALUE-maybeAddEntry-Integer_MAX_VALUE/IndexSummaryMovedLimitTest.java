/*
 * Stage 4, unit tier U3, Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE (case 9c/9e). Not upstream.
 * Copy into test/unit/org/apache/cassandra/io/sstable/indexsummary/ of a clone at cassandra-5.0.9:
 *   ant testsome -Dtest.name=org.apache.cassandra.io.sstable.indexsummary.IndexSummaryMovedLimitTest -Dtest.jvm.args="-Dstage4.out=<file>"
 *
 * The moved limit the cluster tier uses: a Byteman rule adds (2^31 - 1 - L) to what getEntrySize(DecoratedKey) returns (its only
 * caller is the check at IndexSummaryBuilder.java:204), so the comparison reads entries.length() + K + 8 <= L. One method per L,
 * each with that L's rule (the same offsets as moved-limit-<L>.btm); offset 0 shows the rule changes nothing else.
 * 1,000-byte keys, interval 1, level 128.
 */
package org.apache.cassandra.io.sstable.indexsummary;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.ByteBuffer;

import org.junit.BeforeClass;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.slf4j.LoggerFactory;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.dht.IPartitioner;
import org.jboss.byteman.contrib.bmunit.BMRule;
import org.jboss.byteman.contrib.bmunit.BMUnitRunner;

import static org.apache.cassandra.io.sstable.Downsampling.BASE_SAMPLING_LEVEL;
import static org.junit.Assert.assertEquals;

@RunWith(BMUnitRunner.class)
public class IndexSummaryMovedLimitTest
{
    static final int K = 1000;
    static PrintWriter out;
    static IPartitioner partitioner;
    int mismatches = 0;

    @BeforeClass
    public static void setUp() throws IOException
    {
        DatabaseDescriptor.daemonInitialization();
        partitioner = DatabaseDescriptor.getPartitioner();
        String f = System.getProperty("stage4.out");
        if (f != null)
            out = new PrintWriter(new FileWriter(f, true), true);
    }

    void check(String name, Object expected, Object actual)
    {
        boolean ok = expected.equals(actual);
        if (!ok)
            mismatches++;
        String l = "STAGE4 [moved] check " + name + " expected=" + expected + " actual=" + actual + " -> " + (ok ? "ok" : "MISMATCH");
        System.out.println(l);
        if (out != null)
            out.println(l);
    }

    void run(long L, long N) throws Exception
    {
        long nStar = Math.min(N, L / (K + 8));
        Logger lg = (Logger) LoggerFactory.getLogger(IndexSummaryBuilder.class);
        ListAppender<ILoggingEvent> app = new ListAppender<>();
        app.start();
        lg.addAppender(app);
        byte[] kb = new byte[K];
        try (IndexSummaryBuilder b = new IndexSummaryBuilder(N, 1, BASE_SAMPLING_LEVEL))
        {
            for (long i = 0; i < N; i++)
            {
                ByteBuffer.wrap(kb).putLong(0, i);
                b.maybeAddEntry(partitioner.decorateKey(ByteBuffer.wrap(kb)), i);
            }
            long errors = app.list.stream().filter(e -> e.getLevel() == Level.ERROR && e.getFormattedMessage().contains("Memory capacity of index summary exceeded")).count();
            b.prepareToCommit();
            try (IndexSummary s = b.build(partitioner))
            {
                String tag = "U3 L=" + L + " N=" + N;
                String l = "STAGE4 [moved] info " + tag + ": size=" + s.size() + " entriesLength=" + s.getEntriesLength() + " offHeap=" + s.getOffHeapSize() + " ERROR events=" + errors;
                System.out.println(l);
                if (out != null)
                    out.println(l);
                check(tag + " entries kept = min(N, floor(L / 1008))", nStar, (long) s.size());
                check(tag + " entriesLength = kept x 1008 <= L", true, s.getEntriesLength() == nStar * (K + 8) && s.getEntriesLength() <= L);
                check(tag + " off-heap = kept x 1012", nStar * (K + 12), s.getOffHeapSize());
                check(tag + " ERROR events", N > L / (K + 8) ? 1L : 0L, errors);
            }
        }
        finally
        {
            lg.detachAppender(app);
        }
        assertEquals(0, mismatches);
    }

    @Test
    @BMRule(name = "moved limit 8 MiB", targetClass = "org.apache.cassandra.io.sstable.indexsummary.IndexSummaryBuilder",
            targetMethod = "getEntrySize(org.apache.cassandra.db.DecoratedKey)", targetLocation = "AT EXIT",
            action = "return $! + 2139095039;")
    public void movedLimit8MiB() throws Exception
    {
        run(8L << 20, 10_403);
    }

    @Test
    @BMRule(name = "moved limit 32 MiB", targetClass = "org.apache.cassandra.io.sstable.indexsummary.IndexSummaryBuilder",
            targetMethod = "getEntrySize(org.apache.cassandra.db.DecoratedKey)", targetLocation = "AT EXIT",
            action = "return $! + 2113929215;")
    public void movedLimit32MiB() throws Exception
    {
        run(32L << 20, 41_610);
    }

    @Test
    @BMRule(name = "moved limit 128 MiB", targetClass = "org.apache.cassandra.io.sstable.indexsummary.IndexSummaryBuilder",
            targetMethod = "getEntrySize(org.apache.cassandra.db.DecoratedKey)", targetLocation = "AT EXIT",
            action = "return $! + 2013265919;")
    public void movedLimit128MiB() throws Exception
    {
        run(128L << 20, 166_440);
    }

    @Test
    @BMRule(name = "moved limit offset 0", targetClass = "org.apache.cassandra.io.sstable.indexsummary.IndexSummaryBuilder",
            targetMethod = "getEntrySize(org.apache.cassandra.db.DecoratedKey)", targetLocation = "AT EXIT",
            action = "return $! + 0;")
    public void movedLimitOffset0() throws Exception
    {
        run(Integer.MAX_VALUE, 41_610);
    }
}
