/*
 * Stage-4 harness (not upstream) for cases/DEFAULT_SMALLEST_SSTABLE_BYTES-shouldSwitchWriterInCurrentLocation-getEstimatedOnDiskBytesWritten--autonomous.md.
 * Builds a one-sstable input, drives SplittingSizeTieredCompactionWriter (and MaxSSTableSizeWriter, the positive control) directly,
 * and writes per-call and per-output files for the analyzers. Helper code adapted from the closed sibling harness (WriterHarnessBase).
 */
package org.apache.cassandra.db.compaction.writers;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Random;
import java.util.Set;

import org.apache.cassandra.Util;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.db.Directories;
import org.apache.cassandra.db.compaction.AbstractCompactionStrategy;
import org.apache.cassandra.db.compaction.CompactionController;
import org.apache.cassandra.db.compaction.CompactionIterator;
import org.apache.cassandra.db.compaction.OperationType;
import org.apache.cassandra.db.lifecycle.LifecycleTransaction;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.utils.FBUtilities;

import static org.apache.cassandra.db.compaction.OperationType.COMPACTION;
import static org.apache.cassandra.utils.TimeUUID.Generator.nextTimeUUID;

public abstract class SplitWriterHarnessBase extends CQLTester
{
    protected static final int ROWS_PER_PARTITION = 10;
    protected static final int BLOB = 1024;

    protected static String outDir()
    {
        String o = System.getenv("STAGE4_OUT");
        if (o == null) throw new IllegalStateException("STAGE4_OUT not set");
        new java.io.File(o).mkdirs();
        return o;
    }

    protected static int partitions()
    {
        String p = System.getenv("STAGE4_PARTS");
        return p == null ? 20000 : Integer.parseInt(p);
    }

    protected static void note(String line) throws Exception
    {
        System.out.println("STAGE4 " + line);
        try (PrintWriter w = new PrintWriter(new FileWriter(outDir() + "/arms.txt", true)))
        {
            w.println(line);
        }
    }

    protected ColumnFamilyStore newInputTable(boolean compressed) throws Throwable
    {
        createTable("CREATE TABLE %s (k int, t int, v blob, PRIMARY KEY (k, t)) WITH compaction = {'class': 'SizeTieredCompactionStrategy'}"
                    + (compressed ? "" : " AND compression = {'enabled': 'false'}"));
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        cfs.disableAutoCompaction();
        return cfs;
    }

    /** partitions k in [first, first+count), ROWS_PER_PARTITION rows each of BLOB distinct seeded random bytes */
    protected void populate(int first, int count) throws Throwable
    {
        for (int i = first; i < first + count; i++)
        {
            Random r = new Random(0xC0FFEEL + i);
            for (int j = 0; j < ROWS_PER_PARTITION; j++)
            {
                byte[] b = new byte[BLOB];
                r.nextBytes(b);
                execute("INSERT INTO %s (k, t, v) VALUES (?, ?, ?)", i, j, ByteBuffer.wrap(b));
            }
        }
    }

    protected void flushToOneSSTable(ColumnFamilyStore cfs) throws Throwable
    {
        Util.flush(cfs);
        if (cfs.getLiveSSTables().size() > 1)
            cfs.forceMajorCompaction();
        if (cfs.getLiveSSTables().size() != 1)
            throw new IllegalStateException("expected one input sstable: " + cfs.getLiveSSTables());
    }

    protected LifecycleTransaction openTxn(ColumnFamilyStore cfs)
    {
        LifecycleTransaction txn = cfs.getTracker().tryModify(cfs.getLiveSSTables(), OperationType.COMPACTION);
        if (txn == null) throw new IllegalStateException("tryModify returned null");
        return txn;
    }

    protected interface Rec
    {
        String csv();
        int calls();
        String extra();
    }

    /** SplittingSizeTieredCompactionWriter that logs every shouldSwitchWriterInCurrentLocation call */
    protected static class RecSplit extends SplittingSizeTieredCompactionWriter implements Rec
    {
        final StringBuilder sb = new StringBuilder("call,operand,returned,ratio_idx_before,ratio_idx_after,target_before,target_after\n");
        int n = 0;
        final Field fRatios, fIdx, fTgt, fTotal;

        RecSplit(ColumnFamilyStore cfs, Directories dirs, LifecycleTransaction txn, Set<SSTableReader> originals, long smallest) throws Exception
        {
            super(cfs, dirs, txn, originals, smallest);
            fRatios = SplittingSizeTieredCompactionWriter.class.getDeclaredField("ratios");
            fIdx = SplittingSizeTieredCompactionWriter.class.getDeclaredField("currentRatioIndex");
            fTgt = SplittingSizeTieredCompactionWriter.class.getDeclaredField("currentBytesToWrite");
            fTotal = SplittingSizeTieredCompactionWriter.class.getDeclaredField("totalSize");
            for (Field f : new Field[]{ fRatios, fIdx, fTgt, fTotal }) f.setAccessible(true);
        }

        private int idx() { try { return fIdx.getInt(this); } catch (Exception e) { throw new RuntimeException(e); } }
        private long tgt() { try { return fTgt.getLong(this); } catch (Exception e) { throw new RuntimeException(e); } }
        double[] ratios() { try { return (double[]) fRatios.get(this); } catch (Exception e) { throw new RuntimeException(e); } }
        long totalSize() { try { return fTotal.getLong(this); } catch (Exception e) { throw new RuntimeException(e); } }

        @Override
        protected boolean shouldSwitchWriterInCurrentLocation(DecoratedKey key)
        {
            long op = sstableWriter.currentWriter().getEstimatedOnDiskBytesWritten();
            int ib = idx();
            long tb = tgt();
            boolean r = super.shouldSwitchWriterInCurrentLocation(key);
            sb.append(n++).append(',').append(op).append(',').append(r ? 1 : 0).append(',').append(ib).append(',')
              .append(idx()).append(',').append(tb).append(',').append(tgt()).append('\n');
            return r;
        }

        public String csv() { return sb.toString(); }
        public int calls() { return n; }
        public String extra()
        {
            double[] rs = ratios();
            return "totalSize=" + totalSize() + " ratiosLength=" + rs.length + " ratios=" + Arrays.toString(rs).replace(" ", "");
        }
    }

    /** MaxSSTableSizeWriter (positive control) with the same recording */
    protected static class RecMax extends MaxSSTableSizeWriter implements Rec
    {
        final StringBuilder sb = new StringBuilder("call,operand,returned\n");
        int n = 0;
        final long max;

        RecMax(ColumnFamilyStore cfs, Directories dirs, LifecycleTransaction txn, Set<SSTableReader> originals, long max)
        {
            super(cfs, dirs, txn, originals, max, 0);
            this.max = max;
        }

        @Override
        protected boolean shouldSwitchWriterInCurrentLocation(DecoratedKey key)
        {
            long op = sstableWriter.currentWriter().getEstimatedOnDiskBytesWritten();
            boolean r = super.shouldSwitchWriterInCurrentLocation(key);
            sb.append(n++).append(',').append(op).append(',').append(r ? 1 : 0).append('\n');
            return r;
        }

        public String csv() { return sb.toString(); }
        public int calls() { return n; }
        public String extra() { return "maxSSTableSize=" + max; }
    }

    /** mirrors CompactionAwareWriterTest.compact; returns the finished output sstables via out[0] and the number of partitions appended */
    protected int compact(ColumnFamilyStore cfs, LifecycleTransaction txn, CompactionAwareWriter writer, Collection<SSTableReader>[] out)
    {
        assert txn.originals().size() == 1;
        int written = 0;
        long nowInSec = FBUtilities.nowInSeconds();
        try (AbstractCompactionStrategy.ScannerList scanners = cfs.getCompactionStrategyManager().getScanners(txn.originals());
             CompactionController controller = new CompactionController(cfs, txn.originals(), cfs.gcBefore(nowInSec));
             CompactionIterator ci = new CompactionIterator(COMPACTION, scanners.scanners, controller, nowInSec, nextTimeUUID()))
        {
            while (ci.hasNext())
                if (writer.append(ci.next()))
                    written++;
        }
        out[0] = writer.finish();
        return written;
    }

    @SuppressWarnings("unchecked")
    protected List<SSTableReader> runArm(String tag, ColumnFamilyStore cfs, LifecycleTransaction txn, CompactionAwareWriter w, String kind, String param, String extra) throws Throwable
    {
        long inLen = txn.originals().iterator().next().onDiskLength();
        Collection<SSTableReader>[] fin = new Collection[1];
        int parts = compact(cfs, txn, w, fin);
        Rec rec = (Rec) w;
        try (PrintWriter p = new PrintWriter(new FileWriter(outDir() + "/calls-" + tag + ".csv")))
        {
            p.print(rec.csv());
        }
        List<SSTableReader> out = new ArrayList<>(fin[0]);
        out.sort((a, b) -> a.getFirst().compareTo(b.getFirst())); // outputs are non-overlapping and ordered by key = creation order
        long sum = 0, rows = 0;
        try (PrintWriter p = new PrintWriter(new FileWriter(outDir() + "/files-" + tag + ".csv")))
        {
            p.println("idx,data_file_bytes,on_disk_length,rows");
            int i = 0;
            for (SSTableReader s : out)
            {
                long fl = new java.io.File(s.getFilename()).length();
                p.println((i++) + "," + fl + "," + s.onDiskLength() + "," + s.getTotalRows());
                sum += fl;
                rows += s.getTotalRows();
            }
        }
        note("ARM " + tag + " kind=" + kind + " param=" + param + " inputBytes=" + inLen + " partitionsAppended=" + parts + " outputs=" + out.size()
             + " outputBytes=" + sum + " outputRows=" + rows + " calls=" + rec.calls() + " liveAfter=" + cfs.getLiveSSTables().size() + " " + rec.extra() + " " + extra);
        return out;
    }
}
