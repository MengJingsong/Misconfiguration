/*
 * Stage 4, unit tier U1 and U2, Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE (case 9c/9e). Not upstream.
 * Copy into test/unit/org/apache/cassandra/io/sstable/indexsummary/ of a clone at cassandra-5.0.9:
 *   ant testsome -Dtest.name=org.apache.cassandra.io.sstable.indexsummary.IndexSummaryCapTest -Dtest.jvm.args="-Dstage4.out=<file>"
 *
 * U1: IndexSummaryBuilder.maybeAddEntry():204 at the real limit 2^31 - 1, interval 1 (and 2), level 128.
 * U2: the second site, IndexSummaryBuilder.<init>():108, at its boundary.
 * One K-byte array per key whose first 8 bytes are the key's index (big endian), so keys are in order under the unit
 * configuration's ByteOrderedPartitioner and no gigabytes of random keys are generated. Every check prints
 * "STAGE4 check <name> expected=<..> actual=<..> -> ok|MISMATCH" to stdout and to -Dstage4.out; the test fails at the end of
 * its method if any check mismatched. Builders are closed before the next value (each holds up to about 2 GiB native).
 */
package org.apache.cassandra.io.sstable.indexsummary;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.stream.Collectors;

import org.junit.BeforeClass;
import org.junit.FixMethodOrder;
import org.junit.Test;
import org.junit.runners.MethodSorters;
import org.slf4j.LoggerFactory;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.dht.IPartitioner;
import org.apache.cassandra.io.util.SafeMemoryWriter;

import static org.apache.cassandra.io.sstable.Downsampling.BASE_SAMPLING_LEVEL;
import static org.junit.Assert.assertEquals;

@FixMethodOrder(MethodSorters.NAME_ASCENDING)
public class IndexSummaryCapTest
{
    static final long LIMIT = Integer.MAX_VALUE;
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
        info("partitioner " + partitioner.getClass().getSimpleName() + "; defaultExpectedKeySize " + IndexSummaryBuilder.defaultExpectedKeySize);
    }

    static void info(String s)
    {
        String l = "STAGE4 [cap] info " + s;
        System.out.println(l);
        if (out != null)
            out.println(l);
    }

    void check(String name, Object expected, Object actual)
    {
        boolean ok = expected.equals(actual);
        if (!ok)
            mismatches++;
        String l = "STAGE4 [cap] check " + name + " expected=" + expected + " actual=" + actual + " -> " + (ok ? "ok" : "MISMATCH");
        System.out.println(l);
        if (out != null)
            out.println(l);
    }

    void done(String t)
    {
        info(t + " done, mismatches " + mismatches);
        assertEquals("mismatches in " + t, 0, mismatches);
    }

    static Object field(Object o, String name) throws Exception
    {
        Field f = o.getClass().getDeclaredField(name);
        f.setAccessible(true);
        return f.get(o);
    }

    static byte[] keyBytes(int K, long i)
    {
        byte[] b = new byte[K];
        ByteBuffer.wrap(b).putLong(0, i);
        return b;
    }

    static ListAppender<ILoggingEvent> capture()
    {
        Logger l = (Logger) LoggerFactory.getLogger(IndexSummaryBuilder.class);
        ListAppender<ILoggingEvent> a = new ListAppender<>();
        a.start();
        l.addAppender(a);
        return a;
    }

    static void release(ListAppender<ILoggingEvent> a)
    {
        ((Logger) LoggerFactory.getLogger(IndexSummaryBuilder.class)).detachAppender(a);
    }

    static long count(ListAppender<ILoggingEvent> a, Level level, String text)
    {
        return a.list.stream().filter(e -> e.getLevel() == level && e.getFormattedMessage().contains(text)).count();
    }

    /** One U1 value: N keys of K bytes at the given interval; predicted n* = floor(LIMIT / (K + 8)) entries kept. */
    void u1(int K, long N, int interval) throws Exception
    {
        String tag = "U1 K=" + K + " N=" + N + " interval=" + interval;
        long nStar = LIMIT / (K + 8);
        long coverage = (N + interval - 1) / interval;              // samples wanted at full sampling
        long kept = Math.min(coverage, nStar);
        boolean refuse = coverage > nStar;
        ListAppender<ILoggingEvent> app = capture();
        byte[] kb = new byte[K];
        long refusedAt = -1, lenAtRefusal = -1, capAtRefusal = -1;
        boolean unchangedAfter = true;
        try (IndexSummaryBuilder b = new IndexSummaryBuilder(N, interval, BASE_SAMPLING_LEVEL))
        {
            SafeMemoryWriter entries = (SafeMemoryWriter) field(b, "entries");
            for (long i = 0; i < N; i++)
            {
                ByteBuffer.wrap(kb).putLong(0, i);
                DecoratedKey key = partitioner.decorateKey(ByteBuffer.wrap(kb));
                long errBefore = refusedAt < 0 ? count(app, Level.ERROR, "Memory capacity of index summary exceeded") : 1;
                b.maybeAddEntry(key, i);
                if (refusedAt < 0 && count(app, Level.ERROR, "Memory capacity of index summary exceeded") > errBefore)
                {
                    refusedAt = (Long) field(b, "keysWritten") - 1;
                    lenAtRefusal = entries.length();
                    capAtRefusal = entries.capacity();
                }
                else if (refusedAt >= 0 && i == refusedAt + 1)
                    unchangedAfter = entries.length() == lenAtRefusal && entries.capacity() == capAtRefusal;
            }
            long errors = count(app, Level.ERROR, "Memory capacity of index summary exceeded");
            long nextSample = (Long) field(b, "nextSamplePosition");
            b.prepareToCommit();
            try (IndexSummary s = b.build(partitioner))
            {
                info(tag + ": n*=" + nStar + " size=" + s.size() + " entriesLength=" + s.getEntriesLength() + " entries.size=" + s.getEntries().size()
                     + " offsets.size=" + s.getOffsets().size() + " offHeap=" + s.getOffHeapSize() + " maxNumberOfEntries=" + s.getMaxNumberOfEntries()
                     + " ERROR events=" + errors + " refusedAt keysWritten=" + refusedAt + " nextSamplePosition=" + nextSample + " minIndexInterval=" + s.getMinIndexInterval());
                check(tag + " entries kept = min(coverage, n*)", kept, (long) s.size());
                check(tag + " entriesLength = kept x (K + 8)", kept * (K + 8), s.getEntriesLength());
                check(tag + " entriesLength <= 2^31 - 1", true, s.getEntriesLength() <= LIMIT);
                check(tag + " trimmed entries region = entriesLength", s.getEntriesLength(), s.getEntries().size());
                check(tag + " offsets region = 4 x size", 4L * s.size(), s.getOffsets().size());
                check(tag + " off-heap = kept x (K + 12)", kept * (K + 12), s.getOffHeapSize());
                check(tag + " maxNumberOfEntries = ceil(N / interval)", coverage, (long) s.getMaxNumberOfEntries());
                check(tag + " ERROR events", refuse ? 1L : 0L, errors);
                if (refuse)
                {
                    check(tag + " refusal at keysWritten = n* x interval", nStar * interval, refusedAt);
                    check(tag + " nextSamplePosition stays at the refused key", nStar * interval, nextSample);
                    check(tag + " entries length and capacity unchanged by the next key", true, unchangedAfter);
                    check(tag + " length at the refusal = n* x (K + 8)", nStar * (K + 8), lenAtRefusal);
                }
                long lastIdx = (kept - 1) * interval;
                check(tag + " last entry is key " + lastIdx, ByteBuffer.wrap(keyBytes(K, lastIdx)), ByteBuffer.wrap(s.getKey(s.size() - 1)));
                DecoratedKey lastKey = partitioner.decorateKey(ByteBuffer.wrap(keyBytes(K, N - 1)));
                int bs = s.binarySearch(lastKey);
                check(tag + " binarySearch(last key) (scan from the last entry when uncovered)",
                      refuse || interval > 1 || N - 1 != lastIdx ? -(s.size() + 1) : s.size() - 1, bs);
            }
        }
        finally
        {
            release(app);
        }
    }

    @Test
    public void u1_realLimit() throws Exception
    {
        u1(3000, 1_000_000, 1);
        u1(30_000, 80_000, 1);
        u1(65_535, 40_000, 1);
        u1(30_000, 71_563, 1);
        u1(30_000, 71_564, 1);
        u1(30_000, 160_000, 2);
        done("u1_realLimit");
    }

    void u2(long E, long expectedKeys, int wantInterval, long wantCapacity, boolean wantWarn) throws Exception
    {
        String tag = "U2 E=" + E + " expectedKeys=" + expectedKeys;
        long old = IndexSummaryBuilder.defaultExpectedKeySize;
        IndexSummaryBuilder.defaultExpectedKeySize = E;
        ListAppender<ILoggingEvent> app = capture();
        try (IndexSummaryBuilder b = new IndexSummaryBuilder(expectedKeys, 1, BASE_SAMPLING_LEVEL))
        {
            int interval = (Integer) field(b, "minIndexInterval");
            long cap = ((SafeMemoryWriter) field(b, "entries")).capacity();
            long warns = count(app, Level.WARN, "is too low for");
            List<String> msgs = app.list.stream().filter(e -> e.getLevel() == Level.WARN).map(ILoggingEvent::getFormattedMessage).collect(Collectors.toList());
            b.maybeAddEntry(partitioner.decorateKey(ByteBuffer.wrap(keyBytes(16, 0))), 0);
            try (IndexSummary s = b.build(partitioner))
            {
                info(tag + ": interval " + interval + " entries capacity " + cap + " WARN " + msgs + " built minIndexInterval " + s.getMinIndexInterval());
                check(tag + " effective interval", wantInterval, interval);
                check(tag + " entries capacity (the reservation)", wantCapacity, cap);
                check(tag + " capacity <= 2^31 - 1", true, cap <= LIMIT);
                check(tag + " WARN lines", wantWarn ? 1L : 0L, warns);
                check(tag + " built summary interval", wantInterval, s.getMinIndexInterval());
            }
        }
        finally
        {
            release(app);
            IndexSummaryBuilder.defaultExpectedKeySize = old;
        }
    }

    @Test
    public void u2_secondSite() throws Exception
    {
        u2(64, 29_826_161L, 1, 2_147_483_592L, false);
        u2(64, 29_826_162L, 2, 1_073_741_832L, true);
        u2(3000, 1_000_000L, 2, 1_504_000_000L, true);
        done("u2_secondSite");
    }
}
