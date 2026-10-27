/*
 * Stage-4 harness (not upstream): unit tier of max-threshold-getEstimatedTasks-l0SstableCount--autonomous (B2, amendments U1-U4 of 2026-10-26).
 * Copied into test/unit/org/apache/cassandra/db/compaction/ of a copy-source.sh tree.
 * Records readings ("R <section> <key> <value>" lines in $MT_OUT); asserts no prediction. unit-analyze.py judges them.
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
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.schema.CompactionParams;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.TableMetadata;

public class MaxThresholdEstimateProbeTest
{
    static final String KS = "MtProbe";
    static final Random RND = new Random(20261026L);
    static final int[] SEQ = { 4, 32, 128, 32, 4, 128, 32 };   // U3: three readings at 32 give the noise

    @BeforeClass
    public static void defineSchema()
    {
        SchemaLoader.prepareServer();
        List<TableMetadata.Builder> t = new ArrayList<>();
        t.add(SchemaLoader.standardCFMD(KS, "l0").compaction(CompactionParams.lcs(Collections.emptyMap())));
        for (int s : new int[] { 1, 160 })
        {
            t.add(SchemaLoader.standardCFMD(KS, "byte" + s).compaction(lcs(s)));
            t.add(SchemaLoader.standardCFMD(KS, "out" + s).compaction(lcs(s)));
        }
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
        try (PrintWriter w = new PrintWriter(new FileWriter(System.getenv().getOrDefault("MT_OUT", "/tmp/mt-readings.txt"), true)))
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

    static LeveledCompactionStrategy lcsOf(ColumnFamilyStore c)
    {
        return (LeveledCompactionStrategy) c.getCompactionStrategyManager().getStrategies().get(1).get(0);
    }

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

    static int dataFiles(ColumnFamilyStore c)
    {
        int n = 0;
        File dir = new File(c.getDirectories().getDirectoryForNewSSTables().path());
        String[] names = dir.list();
        if (names != null) for (String f : names) if (f.endsWith("-Data.db")) n++;
        return n;
    }

    static long heap()
    {
        Runtime rt = Runtime.getRuntime();
        for (int i = 0; i < 3; i++) { System.gc(); try { Thread.sleep(100); } catch (InterruptedException e) { } }
        return rt.totalMemory() - rt.freeMemory();
    }

    /** B2c-B2e: 200 one-row L0 sstables, compaction off; max_threshold {4,32,128,32,4,128,32}; STCS-in-L0 on, then off */
    @Test
    public void estimateVsMaxThreshold()
    {
        ColumnFamilyStore c = cfs("l0");
        for (int i = 0; i < 200; i++)
            flushRows(c, i, 1, 100);
        int l0 = 0;
        for (SSTableReader x : c.getLiveSSTables()) if (x.getSSTableLevel() == 0) l0++;
        out("step2", "liveSSTables", c.getLiveSSTables().size());
        out("step2", "l0SSTables", l0);
        out("step2", "minThreshold", c.getMinimumCompactionThreshold());
        out("step2", "defaultMaxThreshold", c.getMaximumCompactionThreshold());
        LeveledCompactionStrategy s = lcsOf(c);
        try
        {
            for (boolean disabled : new boolean[] { false, true })
            {
                DatabaseDescriptor.setDisableSTCSInL0(disabled);
                int k = 0;
                for (int mt : SEQ)
                {
                    c.setMaximumCompactionThreshold(mt);
                    String tag = (disabled ? "off" : "on") + ".seq" + (k++) + ".mt" + mt;
                    out("step3", tag + ".maxThreshold", c.getMaximumCompactionThreshold());
                    out("step3", tag + ".estimate", s.getEstimatedRemainingTasks());
                    out("step3", tag + ".sumOnDiskLength", total(c.getLiveSSTables()));
                    out("step3", tag + ".liveDiskSpaceUsed", c.metric.liveDiskSpaceUsed.getCount());
                    out("step3", tag + ".dataFiles", dataFiles(c));
                    out("step3", tag + ".liveSSTables", c.getLiveSSTables().size());
                    out("step3", tag + ".heapUsed", heap());
                }
            }
        }
        finally
        {
            DatabaseDescriptor.setDisableSTCSInL0(false);
        }
    }

    /** U4 (a): 200 L0 sstables of ~1 MiB at sstable_size_in_mb 1 and 160; byte term of the estimate (STCS-in-L0 off) */
    @Test
    public void controlByteTerm()
    {
        try
        {
            DatabaseDescriptor.setDisableSTCSInL0(true);
            for (int size : new int[] { 1, 160 })
            {
                ColumnFamilyStore c = cfs("byte" + size);
                for (int i = 0; i < 200; i++)
                    flushRows(c, i, 1000, 1024);
                out("ctlA", "size" + size + ".l0bytes", total(c.getLiveSSTables()));
                out("ctlA", "size" + size + ".sstables", c.getLiveSSTables().size());
                out("ctlA", "size" + size + ".estimateByteTermOnly", lcsOf(c).getEstimatedRemainingTasks());
                c.truncateBlocking();
            }
        }
        finally
        {
            DatabaseDescriptor.setDisableSTCSInL0(false);
        }
    }

    /** U4 (b): 6 overlapping L0 sstables of ~2 MiB compacted once at sstable_size_in_mb 1 and 160; the output file sizes */
    @Test
    public void controlOutputFileSize()
    {
        for (int size : new int[] { 1, 160 })
        {
            ColumnFamilyStore c = cfs("out" + size);
            for (int i = 0; i < 6; i++)
                flushRows(c, i, 2000, 1024);
            long in = total(c.getLiveSSTables());
            AbstractCompactionTask t = lcsOf(c).getNextBackgroundTask(0);
            out("ctlB", "size" + size + ".taskNull", t == null);
            if (t != null) t.execute(ActiveCompactionsTracker.NOOP);
            List<Long> sizes = new ArrayList<>();
            for (SSTableReader x : c.getLiveSSTables()) sizes.add(x.onDiskLength());
            Collections.sort(sizes);
            out("ctlB", "size" + size + ".inputBytes", in);
            out("ctlB", "size" + size + ".outputs", sizes.size());
            out("ctlB", "size" + size + ".outputSizes", sizes);
            out("ctlB", "size" + size + ".maxOutput", sizes.isEmpty() ? 0 : sizes.get(sizes.size() - 1));
            c.truncateBlocking();
            out("ctlB", "size" + size + ".bytesAfterTruncate", total(c.getLiveSSTables()));
        }
    }
}
