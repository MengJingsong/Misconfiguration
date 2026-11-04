/*
 * Stage-4 harness (not upstream): unit tier of bucket-low-bucket-high-getBuckets-oldAverageSize--autonomous (B2 + amendments A2, U1-U3, 2026-10-26).
 * Copied into test/unit/org/apache/cassandra/db/compaction/ of a copy-source.sh tree.
 * Records readings ("R <section> <key> <value>" lines in $SB_OUT); asserts no prediction. unit-analyze.py judges them.
 */
package org.apache.cassandra.db.compaction;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.LockSupport;

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

public class StcsBucketProbeTest
{
    static final String KS = "SbProbe";
    static final Random RND = new Random(20261026L);
    static final long MIB = 1L << 20;
    static final double[][] SETTINGS = { { 0.9, 1.1 }, { 0.5, 1.5 }, { 0.01, 100.0 } };   // narrow, default, wide
    static final String[] TABLES = { "nar", "def", "wid", "ctl" };
    static final double[][] TABLE_SETTING = { SETTINGS[0], SETTINGS[1], SETTINGS[2], SETTINGS[2] };
    static final int FLUSHES = 12;
    static final int BASE_ROWS = 5000;
    static final double GROWTH = 1.15;

    @BeforeClass
    public static void defineSchema()
    {
        SchemaLoader.prepareServer();
        List<TableMetadata.Builder> t = new ArrayList<>();
        for (int i = 0; i < TABLES.length; i++)
        {
            Map<String, String> o = new HashMap<>();
            o.put("min_threshold", "4");
            o.put("max_threshold", "32");
            o.put("min_sstable_size", "0");
            o.put("bucket_low", String.valueOf(TABLE_SETTING[i][0]));
            o.put("bucket_high", String.valueOf(TABLE_SETTING[i][1]));
            t.add(SchemaLoader.standardCFMD(KS, TABLES[i]).compaction(CompactionParams.stcs(o)));
        }
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1), t.toArray(new TableMetadata.Builder[0]));
    }

    static void out(String section, String key, Object value)
    {
        String line = "R " + section + " " + key + " " + value;
        System.out.println(line);
        try (PrintWriter w = new PrintWriter(new FileWriter(System.getenv().getOrDefault("SB_OUT", "/tmp/sb-readings.txt"), true)))
        {
            w.println(line);
        }
        catch (IOException e) { throw new RuntimeException(e); }
    }

    static String tag(double[] s) { return s[0] == 0.9 ? "narrow" : s[0] == 0.5 ? "default" : "wide"; }

    /** B2c/B2f (i): static getBuckets on synthetic lists. */
    @Test
    public void synthetic()
    {
        List<Pair<String, Long>> geo = new ArrayList<>(), eq = new ArrayList<>();
        for (int i = 0; i < 32; i++)
        {
            geo.add(Pair.create("g" + i, (long) Math.floor(MIB * Math.pow(1.3, i))));
            eq.add(Pair.create("e" + i, 100 * MIB));
        }
        long gt = 0;
        long gmax = 0;
        for (Pair<String, Long> p : geo) { gt += p.right; gmax = Math.max(gmax, p.right); }
        out("syn", "geo.total", gt);
        out("syn", "geo.max", gmax);
        for (String lname : new String[] { "geo", "eq" })
        {
            List<Pair<String, Long>> l = lname.equals("geo") ? geo : eq;
            for (long minSize : new long[] { 0, 50 * MIB })
            {
                for (double[] s : SETTINGS)
                {
                    List<List<String>> b = SizeTieredCompactionStrategy.getBuckets(l, s[1], s[0], minSize);
                    Map<String, Long> size = new HashMap<>();
                    for (Pair<String, Long> p : l) size.put(p.left, p.right);
                    long bestBytes = -1; int bestFiles = 0;
                    List<Integer> counts = new ArrayList<>();
                    for (List<String> bk : b)
                    {
                        long sum = 0;
                        for (String n : bk) sum += size.get(n);
                        counts.add(bk.size());
                        if (sum > bestBytes) { bestBytes = sum; bestFiles = bk.size(); }
                    }
                    Collections.sort(counts, Collections.reverseOrder());
                    String k = lname + ".min" + (minSize / MIB) + "." + tag(s);
                    out("syn", k + ".buckets", b.size());
                    out("syn", k + ".counts", counts);
                    out("syn", k + ".largestFiles", bestFiles);
                    out("syn", k + ".largestBytes", bestBytes);
                }
            }
        }
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

    static void flushRows(ColumnFamilyStore c, int keyTag, int rows, int valBytes)
    {
        for (int r = 0; r < rows; r++)
        {
            byte[] b = new byte[valBytes];
            RND.nextBytes(b);
            UpdateBuilder.create(c.metadata(), String.format("k%07d_%03d", r, keyTag)).newRow("c").add("val", ByteBuffer.wrap(b)).applyUnsafe();
        }
        Util.flush(c);
    }

    static long total(Collection<SSTableReader> l)
    {
        long n = 0;
        for (SSTableReader s : l) n += s.onDiskLength();
        return n;
    }

    static long dataBytes(ColumnFamilyStore c)
    {
        long n = 0;
        File d = new File(c.getDirectories().getDirectoryForNewSSTables().path());
        File[] fs = d.listFiles();
        if (fs != null) for (File f : fs) if (f.getName().endsWith("-Data.db")) n += f.length();
        return n;
    }

    static class Peak extends Thread
    {
        final ColumnFamilyStore c;
        volatile boolean stop;
        final AtomicLong peak = new AtomicLong();
        final AtomicLong samples = new AtomicLong();
        Peak(ColumnFamilyStore c) { this.c = c; setDaemon(true); }
        public void run()
        {
            while (!stop)
            {
                long b = dataBytes(c);
                if (b > peak.get()) peak.set(b);
                samples.incrementAndGet();
                LockSupport.parkNanos(2_000_000L);
            }
        }
    }

    /** B2c-B2e (U1-U3): real sstables, one table per setting, plus the max_threshold 4 control on the wide setting. */
    @Test
    public void real()
    {
        for (int ti = 0; ti < TABLES.length; ti++)
        {
            String name = TABLES[ti];
            double[] s = TABLE_SETTING[ti];
            ColumnFamilyStore c = cfs(name);
            for (int i = 0; i < FLUSHES; i++)
                flushRows(c, i, (int) Math.round(BASE_ROWS * Math.pow(GROWTH, i)), 1024);
            List<SSTableReader> live = new ArrayList<>(c.getLiveSSTables());
            live.sort(Comparator.comparingLong(SSTableReader::onDiskLength));
            StringBuilder sz = new StringBuilder();
            for (SSTableReader r : live) sz.append(r.onDiskLength()).append(',');
            out(name, "setting", tag(s) + (name.equals("ctl") ? "+max4" : ""));
            out(name, "live", live.size());
            out(name, "sizes", sz);
            out(name, "totalBytes", total(live));
            out(name, "dataBytes", dataBytes(c));
            if (name.equals("ctl")) c.setCompactionThresholds(4, 4);
            out(name, "thresholds", c.getMinimumCompactionThreshold() + "/" + c.getMaximumCompactionThreshold());
            int max = c.getMaximumCompactionThreshold();

            // way (i): the static calls as the strategy makes them
            List<List<SSTableReader>> buckets = SizeTieredCompactionStrategy.getBuckets(SizeTieredCompactionStrategy.createSSTableAndLengthPairs(live), s[1], s[0], 0);
            List<Integer> counts = new ArrayList<>();
            for (List<SSTableReader> b : buckets) counts.add(b.size());
            Collections.sort(counts, Collections.reverseOrder());
            out(name, "static.buckets", buckets.size());
            out(name, "static.counts", counts);
            List<SSTableReader> ret = SizeTieredCompactionStrategy.mostInterestingBucket(buckets, 4, max);
            out(name, "static.returned", ret.size());
            out(name, "static.returnedBytes", total(ret));

            // way (ii): the real strategy path, executed
            SizeTieredCompactionStrategy st = stcsOf(c);
            AbstractCompactionTask t = st.getNextBackgroundTask(0);
            out(name, "real.taskNull", t == null);
            out(name, "real.estimatedRemaining", st.getEstimatedRemainingTasks());
            if (t == null)
            {
                out(name, "real.inputs", 0);
                out(name, "real.inputBytes", 0);
            }
            else
            {
                Set<SSTableReader> in = t.transaction.originals();
                long inBytes = total(in);
                out(name, "real.inputs", in.size());
                out(name, "real.inputBytes", inBytes);
                long start = dataBytes(c);
                Peak p = new Peak(c);
                p.start();
                t.execute(ActiveCompactionsTracker.NOOP);
                p.stop = true;
                try { p.join(); } catch (InterruptedException e) { throw new RuntimeException(e); }
                out(name, "real.startBytes", start);
                out(name, "real.peakBytes", p.peak.get());
                out(name, "real.peakExtra", p.peak.get() - start);
                out(name, "real.samples", p.samples.get());
                out(name, "real.endBytes", dataBytes(c));
                out(name, "real.sstablesAfter", c.getLiveSSTables().size());
            }
            c.truncateBlocking();
            out(name, "bytesAfterTruncate", total(c.getLiveSSTables()));
        }
    }
}
