/*
 * Stage-4 harness (not upstream): unit tier of
 * lcs-maxBytesForLevel-fanoutXsstableSize--autonomous (B2, with amendments F1-F3 of 2026-10-24).
 * Copied into test/unit/org/apache/cassandra/db/compaction/ of a copy-source.sh tree.
 * It only RECORDS readings ("R <section> <key> <value>" lines in $LCS_OUT); predictions are
 * judged by unit-analyze.py, so a failed prediction is never a failed test.
 */
package org.apache.cassandra.db.compaction;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.*;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.BeforeClass;
import org.junit.Test;
import org.slf4j.LoggerFactory;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.UpdateBuilder;
import org.apache.cassandra.Util;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.schema.CompactionParams;
import org.apache.cassandra.schema.KeyspaceParams;

import static org.junit.Assert.*;

public class LeveledManifestCapTest
{
    static final String KS = "LmCap";
    static final long MIB = 1024L * 1024L;
    static final int[] SIZES = { 1, 2, 4 };
    static final int[] FANOUTS = { 2, 10 };
    static final Random RND = new Random(20261024L);

    @BeforeClass
    public static void defineSchema()
    {
        SchemaLoader.prepareServer();
        List<org.apache.cassandra.schema.TableMetadata.Builder> t = new ArrayList<>();
        for (int s : SIZES)
            for (int f : FANOUTS)
                t.add(SchemaLoader.standardCFMD(KS, "s" + s + "f" + f).compaction(lcs(s, f, null)));
        t.add(SchemaLoader.standardCFMD(KS, "l8").compaction(lcs(1, 1, null)));
        t.add(SchemaLoader.standardCFMD(KS, "big").compaction(lcs(1, 10, null)));
        t.add(SchemaLoader.standardCFMD(KS, "mt4").compaction(lcs(1, 10, "4")));
        t.add(SchemaLoader.standardCFMD(KS, "mt32").compaction(lcs(1, 10, "32")));
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1), t.toArray(new org.apache.cassandra.schema.TableMetadata.Builder[0]));
    }

    static CompactionParams lcs(int size, int fanout, String maxThreshold)
    {
        Map<String, String> m = new HashMap<>();
        m.put("sstable_size_in_mb", String.valueOf(size));
        m.put("fanout_size", String.valueOf(fanout));
        if (maxThreshold != null)
            m.put("max_threshold", maxThreshold);
        return CompactionParams.lcs(m);
    }

    static void out(String section, String key, Object value)
    {
        String line = "R " + section + " " + key + " " + value;
        System.out.println(line);
        try (PrintWriter w = new PrintWriter(new FileWriter(System.getenv().getOrDefault("LCS_OUT", "/tmp/lcs-readings.txt"), true)))
        {
            w.println(line);
        }
        catch (IOException e) { throw new RuntimeException(e); }
    }

    static ColumnFamilyStore cfs(String name)
    {
        ColumnFamilyStore c = Keyspace.open(KS).getColumnFamilyStore(name);
        c.truncateBlocking();
        c.disableAutoCompaction();
        return c;
    }

    static LeveledCompactionStrategy lcs(ColumnFamilyStore c)
    {
        return (LeveledCompactionStrategy) c.getCompactionStrategyManager().getStrategies().get(1).get(0);
    }

    /** unique key per (flush, row); same key range in every flush so L0 sstables overlap (BOP) */
    static void flushRows(ColumnFamilyStore c, int flush, int rows, int valBytes)
    {
        for (int r = 0; r < rows; r++)
        {
            byte[] b = new byte[valBytes];
            RND.nextBytes(b);
            UpdateBuilder.create(c.metadata(), String.format("k%06d_%03d", r, flush)).newRow("c").add("val", ByteBuffer.wrap(b)).applyUnsafe();
        }
        Util.flush(c);
    }

    static long liveBytes(ColumnFamilyStore c)
    {
        long n = 0;
        for (SSTableReader s : c.getLiveSSTables())
            n += s.onDiskLength();
        return n;
    }

    static long sum(long[] a)
    {
        long n = 0;
        for (long x : a) n += x;
        return n;
    }

    /** F3: drain = run background tasks of the strategy until none is left (cap 500) */
    static int drain(ColumnFamilyStore c)
    {
        LeveledCompactionStrategy st = lcs(c);
        int tasks = 0;
        while (tasks < 500)
        {
            AbstractCompactionTask t = st.getNextBackgroundTask(0);
            if (t == null) break;
            t.execute(ActiveCompactionsTracker.NOOP);
            tasks++;
        }
        return tasks;
    }

    @Test
    public void arithmetic()
    {
        out("step6", "maxBytesForLevel(3,10,160MiB)", LeveledManifest.maxBytesForLevel(3, 10, 160 * MIB));
        out("step6", "expected(3,10,160MiB)", 1000L * 160 * MIB);
        out("step6", "maxBytesForLevel(0,10,160MiB)", LeveledManifest.maxBytesForLevel(0, 10, 160 * MIB));
        out("step6", "maxBytesForLevel(8,1,1MiB)", LeveledManifest.maxBytesForLevel(8, 1, MIB));
        String r = "no-exception";
        try { LeveledManifest.maxBytesForLevel(8, 1000, 1L << 40); }
        catch (RuntimeException e) { r = "RuntimeException"; }
        out("step6", "maxBytesForLevel(8,1000,2^40)", r);
    }

    /** B2e steps 2, 3 and the truncate control (F3) for every knob combination */
    @Test
    public void ladder()
    {
        for (int s : SIZES)
            for (int f : FANOUTS)
            {
                for (int rep = 1; rep <= 3; rep++)
                {
                    String tag = "s" + s + "f" + f + ".rep" + rep;
                    ColumnFamilyStore c = cfs("s" + s + "f" + f);
                    int flushes = 40;
                    int rows = 1000;
                    String err = "none";
                    try
                    {
                        for (int i = 0; i < flushes; i++)
                            flushRows(c, i, rows, 1024);
                    }
                    catch (RuntimeException e) { err = e.toString(); }
                    long[] lv = c.getPerLevelSizeBytes();
                    long target0 = LeveledManifest.maxBytesForLevel(0, f, s * MIB);
                    out("step2", tag + ".writeError", err);
                    out("step2", tag + ".sstables", c.getLiveSSTables().size());
                    out("step2", tag + ".L0bytes", lv[0]);
                    out("step2", tag + ".sumLevelBytes", sum(lv));
                    out("step2", tag + ".liveBytes", liveBytes(c));
                    out("step2", tag + ".L0target", target0);
                    out("step2", tag + ".L0ratio", String.format("%.3f", lv[0] / (double) target0));
                    out("step2", tag + ".ingestedValueBytes", (long) flushes * rows * 1024);
                    long before = liveBytes(c);
                    int tasks = drain(c);
                    long[] lv2 = c.getPerLevelSizeBytes();
                    long maxFile = 0;
                    for (SSTableReader x : c.getLiveSSTables()) maxFile = Math.max(maxFile, x.onDiskLength());
                    out("step3", tag + ".tasks", tasks);
                    out("step3", tag + ".liveBefore", before);
                    out("step3", tag + ".liveAfter", liveBytes(c));
                    out("step3", tag + ".sumLevelBytesAfter", sum(lv2));
                    out("step3", tag + ".levelBytesAfter", Arrays.toString(lv2));
                    out("step3", tag + ".sstablesAfter", c.getLiveSSTables().size());
                    out("step3", tag + ".maxFileAfter", maxFile);
                    for (int l = 1; l < 9; l++)
                        out("step3", tag + ".L" + l + "ratio", String.format("%.3f", lv2[l] / (double) LeveledManifest.maxBytesForLevel(l, f, s * MIB)));
                    c.truncateBlocking();
                    out("control", tag + ".sumLevelBytesAfterTruncate", sum(c.getPerLevelSizeBytes()));
                }
            }
    }

    /** B2e step 4 with F1 */
    @Test
    public void level8()
    {
        for (int rep = 1; rep <= 3; rep++)
        {
            ColumnFamilyStore c = cfs("l8");
            flushRows(c, 0, 2100, 1024);
            List<SSTableReader> l = new ArrayList<>(c.getLiveSSTables());
            assertEquals(1, l.size());
            try { l.get(0).mutateLevelAndReload(8); } catch (IOException e) { throw new RuntimeException(e); }
            LeveledManifest m = LeveledManifest.create(c, 1, 1, l);
            ch.qos.logback.classic.Logger lg = (ch.qos.logback.classic.Logger) LoggerFactory.getLogger(LeveledManifest.class);
            ListAppender<ILoggingEvent> app = new ListAppender<>();
            app.start();
            lg.addAppender(app);
            Level old = lg.getLevel();
            lg.setLevel(Level.WARN);
            LeveledManifest.CompactionCandidate cand = m.getCompactionCandidates();
            lg.detachAppender(app);
            lg.setLevel(old);
            String tag = "l8.rep" + rep;
            out("step4", tag + ".sstableLevel", l.get(0).getSSTableLevel());
            out("step4", tag + ".L8bytes", m.getAllLevelSizeBytes()[8]);
            out("step4", tag + ".L8target", LeveledManifest.maxBytesForLevel(8, 1, MIB));
            out("step4", tag + ".candidate", cand == null ? "null" : "non-null(" + cand.sstables.size() + ")");
            int warns = 0;
            for (ILoggingEvent e : app.list)
                if (e.getLevel() == Level.WARN && e.getFormattedMessage().contains("maximum supported level"))
                {
                    warns++;
                    out("step4", tag + ".warn", e.getFormattedMessage());
                }
            out("step4", tag + ".warnCount", warns);
            out("step4", tag + ".L8bytesAfter", m.getAllLevelSizeBytes()[8]);
        }
    }

    /** B2e step 5: one ~5 MiB partition, sstable_size_in_mb = 1 */
    @Test
    public void bigPartition()
    {
        for (int rep = 1; rep <= 3; rep++)
        {
            ColumnFamilyStore c = cfs("big");
            for (int fl = 0; fl < 2; fl++)
            {
                for (int r = 0; r < 640; r++)
                {
                    byte[] b = new byte[4096];
                    RND.nextBytes(b);
                    UpdateBuilder.create(c.metadata(), "bigpartition").newRow(String.format("c%05d", fl * 640 + r)).add("val", ByteBuffer.wrap(b)).applyUnsafe();
                }
                for (int r = 0; r < 100; r++)
                    UpdateBuilder.create(c.metadata(), String.format("small%03d_%d", r, fl)).newRow("c").add("val", ByteBuffer.wrap(new byte[100])).applyUnsafe();
                Util.flush(c);
            }
            long inBytes = liveBytes(c);
            int tasks = drain(c);
            long maxFile = 0;
            for (SSTableReader x : c.getLiveSSTables()) maxFile = Math.max(maxFile, x.onDiskLength());
            String tag = "big.rep" + rep;
            out("step5", tag + ".inputBytes", inBytes);
            out("step5", tag + ".tasks", tasks);
            out("step5", tag + ".outputs", c.getLiveSSTables().size());
            out("step5", tag + ".maxFile", maxFile);
            out("step5", tag + ".sizeKnobBytes", MIB);
        }
    }

    /** B2e step 7 (F3): max_threshold bounds the candidate count; it is a count, not a byte cap */
    @Test
    public void maxThresholdControl()
    {
        for (String t : new String[] { "mt4", "mt32" })
            for (int rep = 1; rep <= 3; rep++)
            {
                ColumnFamilyStore c = cfs(t);
                for (int i = 0; i < 40; i++)
                    flushRows(c, i, 200, 1024);
                LeveledManifest.CompactionCandidate cand = lcs(c).manifest.getCompactionCandidates();
                out("step7", t + ".rep" + rep + ".l0sstables", lcs(c).getLevelSize(0));
                out("step7", t + ".rep" + rep + ".candidates", cand == null ? -1 : cand.sstables.size());
                out("step7", t + ".rep" + rep + ".maxThreshold", c.getMaximumCompactionThreshold());
            }
    }
}
