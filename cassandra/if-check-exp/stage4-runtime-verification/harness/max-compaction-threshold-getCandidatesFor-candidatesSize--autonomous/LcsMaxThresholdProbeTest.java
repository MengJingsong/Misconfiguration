/*
 * Stage-4 harness (not upstream): unit tier of
 * max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous (B2, amendments U1-U5 of 2026-10-26).
 * Copied into test/unit/org/apache/cassandra/db/compaction/ of a copy-source.sh tree.
 * Records readings ("R <section> <key> <value>" in $LCS_OUT); unit-analyze.py judges the predictions. It asserts none.
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
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.schema.CompactionParams;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.utils.Pair;

public class LcsMaxThresholdProbeTest
{
    static final String KS = "LcsMaxThr";
    static final long MIB = 1024L * 1024L;
    static final int[] SCHEMA_N = { 4, 8, 32, 64 };
    static final int[] SETTER_N = { 4, 8, 32, 64, 100 };
    static final int[] LARGE_N = { 4, 6, 8, 12, 32, 64, 100 };
    static final Random RND = new Random(20261026L);

    @BeforeClass
    public static void defineSchema()
    {
        SchemaLoader.prepareServer();
        List<TableMetadata.Builder> t = new ArrayList<>();
        for (int n : SCHEMA_N)
            t.add(SchemaLoader.standardCFMD(KS, "s" + n).compaction(lcs(n)));
        for (String s : new String[] { "fs", "fl", "g", "f20" })
            t.add(SchemaLoader.standardCFMD(KS, s).compaction(lcs(32)));
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1), t.toArray(new TableMetadata.Builder[0]));
    }

    static CompactionParams lcs(int maxThreshold)
    {
        Map<String, String> o = new HashMap<>();
        o.put("max_threshold", String.valueOf(maxThreshold));
        return CompactionParams.lcs(o);
    }

    static void out(String section, String key, Object value)
    {
        String line = "R " + section + " " + key + " " + value;
        System.out.println(line);
        try (PrintWriter w = new PrintWriter(new FileWriter(System.getenv().getOrDefault("LCS_OUT", "/tmp/lcsmt-readings.txt"), true)))
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

    /** the unit-test yaml uses ByteOrderedPartitioner: key order is byte order, so bands are lexical bands of "k%06d_%03d" */
    static List<String> l1Keys(int band, int l0Rows)
    {
        List<String> keys = new ArrayList<>();
        int start = band * (l0Rows / 10);
        for (int r = start; r < start + 30; r++)
            for (int s = 0; s < 10; s++)
                keys.add(String.format("k%06d_%03d", r, 900 + s));
        return keys;
    }

    static List<String> groupKeys(int group, int s)
    {
        List<String> keys = new ArrayList<>();
        for (int r = group * 400; r < group * 400 + 300; r++)
            keys.add(String.format("k%06d_%03d", r, 800 + s));
        return keys;
    }

    static void flushKeys(ColumnFamilyStore c, List<String> keys, int valBytes)
    {
        for (String k : keys)
        {
            byte[] b = new byte[valBytes];
            RND.nextBytes(b);
            UpdateBuilder.create(c.metadata(), k).newRow("c").add("val", ByteBuffer.wrap(b)).applyUnsafe();
        }
        Util.flush(c);
    }

    static void flushRows(ColumnFamilyStore c, int flush, int rows, int valBytes)
    {
        List<String> keys = new ArrayList<>(rows);
        for (int r = 0; r < rows; r++) keys.add(String.format("k%06d_%03d", r, flush));
        flushKeys(c, keys, valBytes);
    }

    static long total(Collection<SSTableReader> l)
    {
        long n = 0;
        for (SSTableReader s : l) n += s.onDiskLength();
        return n;
    }

    static SSTableReader newest(ColumnFamilyStore c, Set<SSTableReader> before)
    {
        SSTableReader r = null;
        for (SSTableReader x : c.getLiveSSTables()) if (!before.contains(x)) r = x;
        return r;
    }

    /** 10 disjoint-band L1 sstables first (raised to level 1), then n0 L0 flushes of rows x valBytes spanning the whole range */
    static List<SSTableReader> fixtureF(ColumnFamilyStore c, String tag, int n0, int rows, int valBytes)
    {
        for (int b = 0; b < 10; b++)
        {
            Set<SSTableReader> before = new HashSet<>(c.getLiveSSTables());
            flushKeys(c, l1Keys(b, rows), 1024);
            try { newest(c, before).mutateLevelAndReload(1); } catch (IOException e) { throw new RuntimeException(e); }
        }
        for (int i = 0; i < n0; i++)
            flushRows(c, i, rows, valBytes);
        return new ArrayList<>(c.getLiveSSTables());
    }

    /** 25 groups of 4 overlapping L0 sstables; key bands disjoint between groups */
    static List<SSTableReader> fixtureG(ColumnFamilyStore c)
    {
        for (int g = 0; g < 25; g++)
            for (int s = 0; s < 4; s++)
                flushKeys(c, groupKeys(g, s), 1024);
        return new ArrayList<>(c.getLiveSSTables());
    }

    static boolean overlap(SSTableReader a, SSTableReader b)
    {
        return a.getFirst().compareTo(b.getLast()) <= 0 && b.getFirst().compareTo(a.getLast()) <= 0;
    }

    static void describe(String tag, List<SSTableReader> all)
    {
        List<SSTableReader> l0 = new ArrayList<>(), l1 = new ArrayList<>();
        for (SSTableReader x : all) (x.getSSTableLevel() == 0 ? l0 : l1).add(x);
        int pairs00 = 0, pairs01 = 0, pairs11 = 0;
        for (int i = 0; i < l0.size(); i++)
        {
            for (int j = i + 1; j < l0.size(); j++) if (overlap(l0.get(i), l0.get(j))) pairs00++;
            for (SSTableReader y : l1) if (overlap(l0.get(i), y)) pairs01++;
        }
        for (int i = 0; i < l1.size(); i++)
            for (int j = i + 1; j < l1.size(); j++) if (overlap(l1.get(i), l1.get(j))) pairs11++;
        out("fixture", tag + ".l0sstables", l0.size());
        out("fixture", tag + ".l1sstables", l1.size());
        out("fixture", tag + ".l0bytes", total(l0));
        out("fixture", tag + ".l1bytes", total(l1));
        out("fixture", tag + ".overlapPairsL0L0", pairs00);
        out("fixture", tag + ".overlapPairsL0L1", pairs01);
        out("fixture", tag + ".overlapPairsL1L1", pairs11);
    }

    static void probe(String tag, ColumnFamilyStore c, List<SSTableReader> all, int mib)
    {
        LeveledManifest m = LeveledManifest.create(c, mib, 10, all);
        LeveledManifest.CompactionCandidate cand = m.getCompactionCandidates();
        out("step3", tag + ".knobN", c.getMaximumCompactionThreshold());
        out("step3", tag + ".sstableSizeMiB", mib);
        if (cand == null) { out("step3", tag + ".candidate", "null"); return; }
        int n0 = 0, n1 = 0; long b0 = 0, b1 = 0;
        for (SSTableReader x : cand.sstables)
            if (x.getSSTableLevel() == 0) { n0++; b0 += x.onDiskLength(); } else { n1++; b1 += x.onDiskLength(); }
        out("step3", tag + ".candidateCount", cand.sstables.size());
        out("step3", tag + ".candidateL0", n0);
        out("step3", tag + ".candidateL1", n1);
        out("step3", tag + ".candidateL0Bytes", b0);
        out("step3", tag + ".candidateL1Bytes", b1);
        out("step3", tag + ".candidateBytes", b0 + b1);
        out("step3", tag + ".gateBytes", mib * MIB);
        out("step3", tag + ".gateExceeded", b0 > mib * MIB);
        out("step3", tag + ".outputLevel", cand.level);
    }

    static void stcsControl(String tag, ColumnFamilyStore c, List<SSTableReader> all, int n)
    {
        List<SSTableReader> l0 = new ArrayList<>();
        for (SSTableReader x : all) if (x.getSSTableLevel() == 0) l0.add(x);
        List<Pair<SSTableReader, Long>> pairs = SizeTieredCompactionStrategy.createSSTableAndLengthPairs(l0);
        List<List<SSTableReader>> buckets = SizeTieredCompactionStrategy.getBuckets(pairs, 1.5, 0.5, 50L * MIB);
        List<SSTableReader> best = SizeTieredCompactionStrategy.mostInterestingBucket(buckets, 2, n);
        out("control", tag + ".stcs.N" + n + ".buckets", buckets.size());
        out("control", tag + ".stcs.N" + n + ".count", best.size());
        out("control", tag + ".stcs.N" + n + ".bytes", total(best));
    }

    /** schema path: max_threshold in the table options (N = 4, 8, 32, 64), small class, 100 L0 + 10 L1 */
    @Test
    public void smallSchema()
    {
        for (int n : SCHEMA_N)
            for (int rep = 1; rep <= 2; rep++)
            {
                ColumnFamilyStore c = cfs("s" + n);
                List<SSTableReader> all = fixtureF(c, "s" + n, 100, 1000, 1024);
                String tag = "small.schemaN" + n + ".rep" + rep;
                describe(tag, all);
                probe(tag + ".gate160", c, all, 160);
                probe(tag + ".gate1", c, all, 1);
                if (rep == 1) stcsControl("small.schemaN" + n, c, all, n);
            }
    }

    /** setter path (JMX): one small fixture, N in 4, 8, 32, 64, 100; STCS-in-L0 on and off; gate 160 and 1 MiB; 20-sstable variant */
    @Test
    public void smallSetter()
    {
        ColumnFamilyStore c = cfs("fs");
        List<SSTableReader> all = fixtureF(c, "fs", 100, 1000, 1024);
        describe("small.setter", all);
        for (int n : SETTER_N)
        {
            c.setMaximumCompactionThreshold(n);
            for (boolean off : new boolean[] { false, true })
            {
                DatabaseDescriptor.setDisableSTCSInL0(off);
                String tag = "small.setterN" + n + ".stcsL0" + (off ? "Off" : "On");
                probe(tag + ".gate160", c, all, 160);
                if (!off) probe("small.setterN" + n + ".gate1", c, all, 1);
            }
            DatabaseDescriptor.setDisableSTCSInL0(false);
            stcsControl("small.setter", c, all, n);
        }
        c.setMaximumCompactionThreshold(32);
        ColumnFamilyStore d = cfs("f20");
        List<SSTableReader> a20 = fixtureF(d, "f20", 20, 1000, 1024);
        describe("small20", a20);
        for (int n : new int[] { 4, 8, 32 })
        {
            d.setMaximumCompactionThreshold(n);
            probe("small20.setterN" + n + ".gate160", d, a20, 160);
        }
    }

    /** large class (about 20 MiB each), 100 L0 + 10 L1: the L1 gate is crossed inside the N range */
    @Test
    public void largeSetter()
    {
        ColumnFamilyStore c = cfs("fl");
        List<SSTableReader> all = fixtureF(c, "fl", 100, 20000, 1024);
        describe("large.setter", all);
        for (int n : LARGE_N)
        {
            c.setMaximumCompactionThreshold(n);
            probe("large.setterN" + n + ".stcsL0On.gate160", c, all, 160);
            DatabaseDescriptor.setDisableSTCSInL0(true);
            probe("large.setterN" + n + ".stcsL0Off.gate160", c, all, 160);
            DatabaseDescriptor.setDisableSTCSInL0(false);
            stcsControl("large.setter", c, all, n);
        }
        c.truncateBlocking();
    }

    /** B2h(iii): 25 groups of 4 overlapping L0 sstables, no L1 */
    @Test
    public void groups()
    {
        ColumnFamilyStore c = cfs("g");
        List<SSTableReader> all = fixtureG(c);
        describe("groups", all);
        for (int n : SETTER_N)
        {
            c.setMaximumCompactionThreshold(n);
            probe("groups.setterN" + n + ".gate160", c, all, 160);
            probe("groups.setterN" + n + ".gate1", c, all, 1);
        }
    }

    /** instrument control: truncate empties the table */
    @Test
    public void truncateControl()
    {
        ColumnFamilyStore c = cfs("fs");
        flushRows(c, 0, 100, 1024);
        out("control", "truncate.before", total(c.getLiveSSTables()));
        c.truncateBlocking();
        out("control", "truncate.after", total(c.getLiveSSTables()));
    }
}
