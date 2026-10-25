/*
 * Stage-4 harness (not upstream): unit tier of
 * sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous (B2, amendments C1-C3 of 2026-10-24).
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
import org.apache.cassandra.schema.TableMetadata;

public class LcsL0ThresholdProbeTest
{
    static final String KS = "LcsL0Probe";
    static final long MIB = 1024L * 1024L;
    static final int[] SIZES = { 1, 5, 160 };
    static final Random RND = new Random(20261024L);

    @BeforeClass
    public static void defineSchema()
    {
        SchemaLoader.prepareServer();
        List<TableMetadata.Builder> t = new ArrayList<>();
        for (int s : SIZES)
            t.add(SchemaLoader.standardCFMD(KS, "n" + s).compaction(lcs(s)));
        t.add(SchemaLoader.standardCFMD(KS, "out5").compaction(lcs(5)));
        t.add(SchemaLoader.standardCFMD(KS, "big5").compaction(lcs(5)));
        t.add(SchemaLoader.standardCFMD(KS, "p1").compaction(lcs(1)));
        t.add(SchemaLoader.standardCFMD(KS, "p160").compaction(lcs(160)));
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

    /** C1: 6 overlapping L0 sstables (~2 MiB) + one L1 sstable over the same range; read the candidate set */
    @Test
    public void phase1CandidateSet()
    {
        for (int s : SIZES)
            for (int rep = 1; rep <= 3; rep++)
            {
                ColumnFamilyStore c = cfs("n" + s);
                for (int i = 0; i < 6; i++)
                    flushRows(c, i, 2000, 1024);
                Set<SSTableReader> before = new HashSet<>(c.getLiveSSTables());
                flushRows(c, 6, 2000, 1024);
                List<SSTableReader> all = new ArrayList<>(c.getLiveSSTables());
                SSTableReader l1 = null;
                for (SSTableReader x : all) if (!before.contains(x)) l1 = x;
                try { l1.mutateLevelAndReload(1); } catch (IOException e) { throw new RuntimeException(e); }
                LeveledManifest m = LeveledManifest.create(c, s, 10, all);
                LeveledManifest.CompactionCandidate cand = m.getCompactionCandidates();
                String tag = "N" + s + ".rep" + rep;
                long l0total = 0; int l0n = 0;
                for (SSTableReader x : all) if (x.getSSTableLevel() == 0) { l0total += x.onDiskLength(); l0n++; }
                out("step3", tag + ".l0sstables", l0n);
                out("step3", tag + ".l0totalBytes", l0total);
                out("step3", tag + ".sizeBytes", s * MIB);
                out("step3", tag + ".l0total/size", String.format("%.3f", l0total / (double) (s * MIB)));
                if (cand == null) { out("step3", tag + ".candidate", "null"); continue; }
                int nl1 = 0; for (SSTableReader x : cand.sstables) if (x.getSSTableLevel() == 1) nl1++;
                out("step3", tag + ".candidateCount", cand.sstables.size());
                out("step3", tag + ".candidateBytes", total(cand.sstables));
                out("step3", tag + ".candidateHasL1", nl1 > 0);
                out("step3", tag + ".candidateOutputLevel", cand.level);
                out("step3", tag + ".candidateMaxSSTableBytes", cand.maxSSTableBytes);
                out("step3", tag + ".manifestNextLevel", m.getNextLevel(cand.sstables));
            }
    }

    /** C3, B2e step 4: execute the size-5 task on 6 L0 sstables; and the oversized partition */
    @Test
    public void step4Outputs()
    {
        for (int rep = 1; rep <= 3; rep++)
        {
            ColumnFamilyStore c = cfs("out5");
            for (int i = 0; i < 6; i++)
                flushRows(c, i, 2000, 1024);
            long in = total(c.getLiveSSTables());
            AbstractCompactionTask t = lcs(c).getNextBackgroundTask(0);
            out("step4", "out5.rep" + rep + ".taskNull", t == null);
            if (t != null) t.execute(ActiveCompactionsTracker.NOOP);
            List<Long> sizes = new ArrayList<>();
            for (SSTableReader x : c.getLiveSSTables()) sizes.add(x.onDiskLength());
            Collections.sort(sizes);
            out("step4", "out5.rep" + rep + ".inputBytes", in);
            out("step4", "out5.rep" + rep + ".outputs", sizes.size());
            out("step4", "out5.rep" + rep + ".outputSizes", sizes);
            out("step4", "out5.rep" + rep + ".outputSum", total(c.getLiveSSTables()));
            out("step4", "out5.rep" + rep + ".sizeKnobBytes", 5 * MIB);

            ColumnFamilyStore b = cfs("big5");
            for (int fl = 0; fl < 2; fl++)
            {
                for (int r = 0; r < 1500; r++)
                {
                    byte[] bb = new byte[4096];
                    RND.nextBytes(bb);
                    UpdateBuilder.create(b.metadata(), "bigpartition").newRow(String.format("c%05d", fl * 1500 + r)).add("val", ByteBuffer.wrap(bb)).applyUnsafe();
                }
                Util.flush(b);
            }
            long bin = total(b.getLiveSSTables());
            AbstractCompactionTask bt = lcs(b).getNextBackgroundTask(0);
            if (bt != null) bt.execute(ActiveCompactionsTracker.NOOP);
            long max = 0;
            for (SSTableReader x : b.getLiveSSTables()) max = Math.max(max, x.onDiskLength());
            out("step4", "big5.rep" + rep + ".inputBytes", bin);
            out("step4", "big5.rep" + rep + ".outputs", b.getLiveSSTables().size());
            out("step4", "big5.rep" + rep + ".maxFile", max);
            out("step4", "big5.rep" + rep + ".sizeKnobBytes", 5 * MIB);
        }
    }

    /** C2, phase 2: 200 L0 sstables of ~1 MiB, no compaction; L0 total for size 1 and 160 */
    @Test
    public void phase2L0Total()
    {
        for (String t : new String[] { "p1", "p160" })
            for (int rep = 1; rep <= 3; rep++)
            {
                ColumnFamilyStore c = cfs(t);
                for (int i = 0; i < 200; i++)
                    flushRows(c, i, 1000, 1024);
                long[] lv = c.getPerLevelSizeBytes();
                int notL0 = 0;
                for (SSTableReader x : c.getLiveSSTables()) if (x.getSSTableLevel() != 0) notL0++;
                String tag = t + ".rep" + rep;
                out("step5", tag + ".sstables", c.getLiveSSTables().size());
                out("step5", tag + ".notL0", notL0);
                out("step5", tag + ".L0bytes", lv[0]);
                out("step5", tag + ".liveBytes", total(c.getLiveSSTables()));
                out("step5", tag + ".L0target", LeveledManifest.maxBytesForLevel(0, 10, (t.equals("p1") ? 1 : 160) * MIB));
                c.truncateBlocking();
                out("control", tag + ".bytesAfterTruncate", total(c.getLiveSSTables()));
            }
    }
}
