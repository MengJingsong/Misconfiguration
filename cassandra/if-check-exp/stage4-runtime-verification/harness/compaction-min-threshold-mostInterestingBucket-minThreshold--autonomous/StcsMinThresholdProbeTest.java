/*
 * Stage-4 harness (not upstream): unit tier of compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous (B2 + amendments U1-U3, 2026-10-26).
 * Copied into test/unit/org/apache/cassandra/db/compaction/ of a copy-source.sh tree.
 * Records readings ("R <section> <key> <value>" lines in $SM_OUT); asserts no prediction. unit-analyze.py judges them.
 */
package org.apache.cassandra.db.compaction;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.*;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.UpdateBuilder;
import org.apache.cassandra.Util;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.schema.CompactionParams;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.utils.Pair;

public class StcsMinThresholdProbeTest
{
    static final String KS = "SmProbe";
    static final Random RND = new Random(20261026L);
    static final int[] NS = { 3, 7, 15, 31, 40 };
    static final int[] MS = { 2, 4, 8, 16, 32 };
    static final long MIN_SSTABLE_SIZE = 50L * 1024 * 1024;

    @BeforeClass
    public static void defineSchema()
    {
        SchemaLoader.prepareServer();
        List<TableMetadata.Builder> t = new ArrayList<>();
        for (String n : new String[] { "grid", "ctl", "ovw" })
            t.add(SchemaLoader.standardCFMD(KS, n).compaction(CompactionParams.stcs(Collections.emptyMap())));
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1), t.toArray(new TableMetadata.Builder[0]));
    }

    static void out(String section, String key, Object value)
    {
        String line = "R " + section + " " + key + " " + value;
        System.out.println(line);
        try (PrintWriter w = new PrintWriter(new FileWriter(System.getenv().getOrDefault("SM_OUT", "/tmp/sm-readings.txt"), true)))
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

    static SizeTieredCompactionStrategy stcsOf(ColumnFamilyStore c)
    {
        return (SizeTieredCompactionStrategy) c.getCompactionStrategyManager().getStrategies().get(1).get(0);
    }

    /** one flush of `rows` rows of `valBytes`; keys are k<row>_<keyTag> (keyTag = flush index for unique keys, constant for overwrites) */
    static void flushRows(ColumnFamilyStore c, int keyTag, int rows, int valBytes)
    {
        for (int r = 0; r < rows; r++)
        {
            byte[] b = new byte[valBytes];
            RND.nextBytes(b);
            UpdateBuilder.create(c.metadata(), String.format("k%06d_%03d", r, keyTag)).newRow("c").add("val", ByteBuffer.wrap(b)).applyUnsafe();
        }
        Util.flush(c);
    }

    static long total(Collection<SSTableReader> l)
    {
        long n = 0;
        for (SSTableReader s : l) n += s.onDiskLength();
        return n;
    }

    static int dataFiles(ColumnFamilyStore c)
    {
        int n = 0;
        for (String d : new String[] { c.getDirectories().getDirectoryForNewSSTables().path() })
        {
            String[] names = new File(d).list();
            if (names != null) for (String f : names) if (f.endsWith("-Data.db")) n++;
        }
        return n;
    }

    /** way (i): the static call as filed. Returns the bucket (possibly empty) and records buckets / size / bytes */
    static List<SSTableReader> staticWay(String sec, String tag, List<SSTableReader> live, int m, int max)
    {
        List<List<SSTableReader>> buckets = SizeTieredCompactionStrategy.getBuckets(SizeTieredCompactionStrategy.createSSTableAndLengthPairs(live), 1.5, 0.5, MIN_SSTABLE_SIZE);
        List<SSTableReader> ret = SizeTieredCompactionStrategy.mostInterestingBucket(buckets, m, max);
        out(sec, tag + ".static.buckets", buckets.size());
        out(sec, tag + ".static.returned", ret.size());
        out(sec, tag + ".static.returnedBytes", total(ret));
        out(sec, tag + ".static.uncompactedBytes", total(live) - total(ret));
        return ret;
    }

    /** way (ii): the real strategy path; the transaction is aborted unless `execute` */
    static AbstractCompactionTask realWay(String sec, String tag, ColumnFamilyStore c, int m, int max, boolean execute)
    {
        c.setCompactionThresholds(m, max);
        out(sec, tag + ".real.thresholds", c.getMinimumCompactionThreshold() + "/" + c.getMaximumCompactionThreshold());
        SizeTieredCompactionStrategy s = stcsOf(c);
        AbstractCompactionTask t = s.getNextBackgroundTask(0);
        out(sec, tag + ".real.taskNull", t == null);
        out(sec, tag + ".real.estimatedRemaining", s.getEstimatedRemainingTasks());
        if (t != null)
        {
            Set<SSTableReader> in = t.transaction.originals();
            out(sec, tag + ".real.inputs", in.size());
            out(sec, tag + ".real.inputBytes", total(in));
            if (!execute) t.transaction.abort();
        }
        else
        {
            out(sec, tag + ".real.inputs", 0);
            out(sec, tag + ".real.inputBytes", 0);
        }
        return t;
    }

    /** B2c-B2e (U1): N flushes of ~1 MiB; M in MS, max 32; both ways */
    @Test
    public void grid()
    {
        for (int n : NS)
        {
            ColumnFamilyStore c = cfs("grid");
            for (int i = 0; i < n; i++)
                flushRows(c, i, 1000, 1024);
            List<SSTableReader> live = new ArrayList<>(c.getLiveSSTables());
            out("grid", "N" + n + ".live", live.size());
            out("grid", "N" + n + ".totalBytes", total(live));
            out("grid", "N" + n + ".dataFiles", dataFiles(c));
            for (int m : MS)
            {
                String tag = "N" + n + ".M" + m;
                staticWay("grid", tag, live, m, 32);
                realWay("grid", tag, c, m, 32, false);
                out("grid", tag + ".liveAfter", c.getLiveSSTables().size());
            }
        }
    }

    /** B2h (U3): positive control, max_threshold sweep at M = 4 */
    @Test
    public void maxControl()
    {
        for (int n : new int[] { 7, 40 })
        {
            ColumnFamilyStore c = cfs("ctl");
            for (int i = 0; i < n; i++)
                flushRows(c, i, 1000, 1024);
            List<SSTableReader> live = new ArrayList<>(c.getLiveSSTables());
            out("ctl", "N" + n + ".live", live.size());
            for (int max : new int[] { 4, 8, 32 })
            {
                String tag = "N" + n + ".max" + max;
                staticWay("ctl", tag, live, 4, max);
                realWay("ctl", tag, c, 4, max, false);
            }
        }
    }

    /** U2: real disk bytes: 7 flushes of the same 1,000 keys; M = 8 (no task) then M = 4 (task executed) */
    @Test
    public void overwriteBytes()
    {
        for (int m : new int[] { 8, 4 })
        {
            ColumnFamilyStore c = cfs("ovw");
            for (int i = 0; i < 7; i++)
                flushRows(c, 0, 1000, 1024);
            long before = total(c.getLiveSSTables());
            int filesBefore = dataFiles(c);
            out("ovw", "M" + m + ".sstablesBefore", c.getLiveSSTables().size());
            out("ovw", "M" + m + ".bytesBefore", before);
            out("ovw", "M" + m + ".filesBefore", filesBefore);
            AbstractCompactionTask t = realWay("ovw", "M" + m, c, m, 32, true);
            if (t != null) t.execute(ActiveCompactionsTracker.NOOP);
            long after = total(c.getLiveSSTables());
            out("ovw", "M" + m + ".sstablesAfter", c.getLiveSSTables().size());
            out("ovw", "M" + m + ".bytesAfter", after);
            out("ovw", "M" + m + ".filesAfter", dataFiles(c));
            out("ovw", "M" + m + ".ratio", String.format("%.4f", after / (double) before));
            c.truncateBlocking();
            out("ovw", "M" + m + ".bytesAfterTruncate", total(c.getLiveSSTables()));
        }
    }
}
