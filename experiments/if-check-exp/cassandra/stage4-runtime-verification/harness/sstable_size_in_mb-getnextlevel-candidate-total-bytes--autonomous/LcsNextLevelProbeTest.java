/*
 * Stage-4 harness (not upstream): unit tier of
 * sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous (B2, amendments N1-N3 of 2026-10-24).
 * Copied into test/unit/org/apache/cassandra/db/compaction/ of a copy-source.sh tree.
 * Records readings ("R <section> <key> <value>" in $LCS_OUT); unit-analyze.py judges the predictions.
 */
package org.apache.cassandra.db.compaction;

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
import org.apache.cassandra.schema.MockSchema;
import org.apache.cassandra.schema.TableMetadata;

public class LcsNextLevelProbeTest
{
    static final String KS = "LcsNextProbe";
    static final long MIB = 1024L * 1024L;
    static final int[] SIZES = { 1, 5, 20, 160 };
    static final Random RND = new Random(20261024L);

    @BeforeClass
    public static void defineSchema()
    {
        SchemaLoader.prepareServer();
        List<TableMetadata.Builder> t = new ArrayList<>();
        for (int s : SIZES)
            t.add(SchemaLoader.standardCFMD(KS, "n" + s).compaction(lcs(s)));
        for (int s : SIZES)
            t.add(SchemaLoader.standardCFMD(KS, "m" + s).compaction(lcs(s)));
        t.add(SchemaLoader.standardCFMD(KS, "big5").compaction(lcs(5)));
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1), t.toArray(new TableMetadata.Builder[0]));
    }

    static CompactionParams lcs(int size)
    {
        return CompactionParams.lcs(Collections.singletonMap("sstable_size_in_mb", String.valueOf(size)));
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

    /** unique key per (flush,row); same key range in every flush so all sstables overlap (BOP unit yaml) */
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

    static long total(Collection<SSTableReader> l)
    {
        long n = 0;
        for (SSTableReader s : l) n += s.onDiskLength();
        return n;
    }

    static int gen = 1000;

    static int nextLevel(ColumnFamilyStore c, int n, Collection<SSTableReader> l)
    {
        return LeveledManifest.create(c, n, 10, Collections.<SSTableReader>emptyList()).getNextLevel(l);
    }

    /** N1: the strict "<" boundary with exact on-disk sizes (MockSchema sstables), plus mixed-level and all-L1 inputs */
    @Test
    public void boundary()
    {
        for (int s : SIZES)
        {
            ColumnFamilyStore c = Keyspace.open(KS).getColumnFamilyStore("m" + s);
            c.disableAutoCompaction();
            long n = s * MIB;
            for (long delta : new long[] { -1, 0, 1 })
            {
                SSTableReader one = MockSchema.sstableWithLevel(gen++, (int) (n + delta), 0, c);
                out("boundary", "N" + s + ".single[" + delta + "].totalBytes", one.onDiskLength());
                out("boundary", "N" + s + ".single[" + delta + "].nextLevel", nextLevel(c, s, Collections.singletonList(one)));
                int third = (int) ((n + delta) / 3);
                List<SSTableReader> three = Arrays.asList(MockSchema.sstableWithLevel(gen++, third, 0, c),
                                                         MockSchema.sstableWithLevel(gen++, third, 0, c),
                                                         MockSchema.sstableWithLevel(gen++, (int) (n + delta - 2L * third), 0, c));
                out("boundary", "N" + s + ".three[" + delta + "].totalBytes", total(three));
                out("boundary", "N" + s + ".three[" + delta + "].nextLevel", nextLevel(c, s, three));
            }
            SSTableReader a0 = MockSchema.sstableWithLevel(gen++, 1000, 0, c);
            SSTableReader a1 = MockSchema.sstableWithLevel(gen++, 1000, 1, c);
            SSTableReader b1 = MockSchema.sstableWithLevel(gen++, 1000, 1, c);
            out("boundary", "N" + s + ".mixedL0L1.nextLevel", nextLevel(c, s, Arrays.asList(a0, a1)));
            out("boundary", "N" + s + ".allL1.nextLevel", nextLevel(c, s, Arrays.asList(a1, b1)));
            out("boundary", "N" + s + ".maxSSTableBytes", lcs(c).getMaxSSTableBytes());
        }
    }

    /** B2c/B2e sets A and B (real flushes); Set B is then compacted once (N3) */
    @Test
    public void sets()
    {
        for (int s : SIZES)
            for (String set : new String[] { "A", "B" })
                for (int rep = 1; rep <= 3; rep++)
                {
                    int basis = s == 160 ? 20 : s; // N=160 reuses the N=20 sets (far below the limit)
                    double factor = set.equals("A") ? 0.8 : 1.5;
                    int rows = (int) Math.round(factor * basis * MIB / 3 / 1075.0);
                    ColumnFamilyStore c = cfs("n" + s);
                    for (int i = 0; i < 3; i++)
                        flushRows(c, i, rows, 1024);
                    List<SSTableReader> readers = new ArrayList<>(c.getLiveSSTables());
                    long tot = total(readers);
                    String tag = "N" + s + ".set" + set + ".rep" + rep;
                    out("sets", tag + ".sstables", readers.size());
                    out("sets", tag + ".totalBytes", tot);
                    out("sets", tag + ".sizeBytes", s * MIB);
                    out("sets", tag + ".total/size", String.format("%.3f", tot / (double) (s * MIB)));
                    out("sets", tag + ".nextLevel", lcs(c).manifest.getNextLevel(readers));
                    if (set.equals("B"))
                    {
                        AbstractCompactionTask t = lcs(c).getNextBackgroundTask(0);
                        out("sets", tag + ".taskNull", t == null);
                        if (t != null) t.execute(ActiveCompactionsTracker.NOOP);
                        List<Long> sizes = new ArrayList<>();
                        List<Integer> levels = new ArrayList<>();
                        for (SSTableReader x : c.getLiveSSTables()) { sizes.add(x.onDiskLength()); levels.add(x.getSSTableLevel()); }
                        out("sets", tag + ".outputs", sizes.size());
                        out("sets", tag + ".outputSizes", sizes);
                        out("sets", tag + ".outputLevels", levels);
                        out("sets", tag + ".outputSum", total(c.getLiveSSTables()));
                    }
                }
    }

    /** B2e step 5: one 15 MiB partition at N = 5 */
    @Test
    public void bigPartition()
    {
        for (int rep = 1; rep <= 3; rep++)
        {
            ColumnFamilyStore b = cfs("big5");
            for (int fl = 0; fl < 2; fl++)
            {
                for (int r = 0; r < 1900; r++)
                {
                    byte[] bb = new byte[4096];
                    RND.nextBytes(bb);
                    UpdateBuilder.create(b.metadata(), "bigpartition").newRow(String.format("c%05d", fl * 1900 + r)).add("val", ByteBuffer.wrap(bb)).applyUnsafe();
                }
                for (int r = 0; r < 100; r++)
                    UpdateBuilder.create(b.metadata(), String.format("small%03d_%d", r, fl)).newRow("c").add("val", ByteBuffer.wrap(new byte[100])).applyUnsafe();
                Util.flush(b);
            }
            long bin = total(b.getLiveSSTables());
            AbstractCompactionTask bt = lcs(b).getNextBackgroundTask(0);
            if (bt != null) bt.execute(ActiveCompactionsTracker.NOOP);
            long max = 0;
            for (SSTableReader x : b.getLiveSSTables()) max = Math.max(max, x.onDiskLength());
            out("big", "big5.rep" + rep + ".inputBytes", bin);
            out("big", "big5.rep" + rep + ".outputs", b.getLiveSSTables().size());
            out("big", "big5.rep" + rep + ".maxFile", max);
            out("big", "big5.rep" + rep + ".sizeKnobBytes", 5 * MIB);
        }
    }

    /** B2h positive control as filed: the SAME input (3 flushes, ~30 MiB) compacted once at every N; file count must grow as N shrinks */
    @Test
    public void sameInputControl()
    {
        for (int s : SIZES)
            for (int rep = 1; rep <= 3; rep++)
            {
                ColumnFamilyStore c = cfs("n" + s);
                for (int i = 0; i < 3; i++)
                    flushRows(c, i, 9500, 1024);
                long in = total(c.getLiveSSTables());
                AbstractCompactionTask t = lcs(c).getNextBackgroundTask(0);
                if (t != null) t.execute(ActiveCompactionsTracker.NOOP);
                List<Long> sizes = new ArrayList<>();
                for (SSTableReader x : c.getLiveSSTables()) sizes.add(x.onDiskLength());
                String tag = "same.N" + s + ".rep" + rep;
                out("same", tag + ".inputBytes", in);
                out("same", tag + ".outputs", sizes.size());
                out("same", tag + ".maxFile", Collections.max(sizes));
                out("same", tag + ".outputSum", total(c.getLiveSSTables()));
            }
    }
}
