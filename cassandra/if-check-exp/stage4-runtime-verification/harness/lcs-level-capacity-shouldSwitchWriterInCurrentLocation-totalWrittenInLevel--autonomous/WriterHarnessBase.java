/*
 * Stage-4 harness (not upstream). Shared by the two MajorLeveledCompactionWriter cases; the file is identical in both
 * harness folders. Builds a one-sstable input, drives MajorLeveledCompactionWriter directly, and writes per-call and
 * per-output files for the analyzers.
 */
package org.apache.cassandra.db.compaction.writers;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

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

public abstract class WriterHarnessBase extends CQLTester
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

    /** STCS input table; the writer is driven directly, so the strategy only matters for building the input. */
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

    /** one wide partition: rows t in [0, rows) each of rowBytes seeded random bytes */
    protected void populateWide(int key, int rows, int rowBytes) throws Throwable
    {
        Random r = new Random(0xBEEFL + key);
        for (int j = 0; j < rows; j++)
        {
            byte[] b = new byte[rowBytes];
            r.nextBytes(b);
            execute("INSERT INTO %s (k, t, v) VALUES (?, ?, ?)", key, j, ByteBuffer.wrap(b));
        }
    }

    /** flush, and make sure exactly one sstable is live (as the upstream helper does) */
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

    /** MajorLeveledCompactionWriter that logs every shouldSwitchWriterInCurrentLocation call */
    protected static class RecWriter extends MajorLeveledCompactionWriter
    {
        final StringBuilder sb = new StringBuilder("call,operand,returned,level_before,level_after,twil_before,twil_after\n");
        int n = 0;
        final Field lvl, tw;

        RecWriter(ColumnFamilyStore cfs, Directories dirs, LifecycleTransaction txn, java.util.Set<SSTableReader> originals, long max) throws Exception
        {
            super(cfs, dirs, txn, originals, max);
            lvl = MajorLeveledCompactionWriter.class.getDeclaredField("currentLevel");
            tw = MajorLeveledCompactionWriter.class.getDeclaredField("totalWrittenInLevel");
            lvl.setAccessible(true);
            tw.setAccessible(true);
        }

        private int level() { try { return lvl.getInt(this); } catch (Exception e) { throw new RuntimeException(e); } }
        private long twil() { try { return tw.getLong(this); } catch (Exception e) { throw new RuntimeException(e); } }

        @Override
        protected boolean shouldSwitchWriterInCurrentLocation(DecoratedKey key)
        {
            long op = sstableWriter.currentWriter().getEstimatedOnDiskBytesWritten();
            int lb = level();
            long tb = twil();
            boolean r = super.shouldSwitchWriterInCurrentLocation(key);
            sb.append(n++).append(',').append(op).append(',').append(r ? 1 : 0).append(',').append(lb).append(',')
              .append(level()).append(',').append(tb).append(',').append(twil()).append('\n');
            return r;
        }
    }

    /** mirrors CompactionAwareWriterTest.compact; returns the number of partitions appended */
    protected int compact(ColumnFamilyStore cfs, LifecycleTransaction txn, CompactionAwareWriter writer)
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
        writer.finish();
        return written;
    }

    /**
     * Runs the writer over the txn with maxSize, writes calls-&lt;tag&gt;.csv and files-&lt;tag&gt;.csv, notes the arm.
     * Returns the output sstables in creation order.
     */
    protected List<SSTableReader> runArm(String tag, ColumnFamilyStore cfs, LifecycleTransaction txn, long maxSize, String extra) throws Throwable
    {
        long inLen = txn.originals().iterator().next().onDiskLength();
        RecWriter w = new RecWriter(cfs, cfs.getDirectories(), txn, txn.originals(), maxSize);
        int parts = compact(cfs, txn, w);
        try (PrintWriter p = new PrintWriter(new FileWriter(outDir() + "/calls-" + tag + ".csv")))
        {
            p.print(w.sb);
        }
        List<SSTableReader> out = new ArrayList<>(cfs.getLiveSSTables());
        out.sort((a, b) -> a.getFirst().compareTo(b.getFirst())); // outputs are non-overlapping and sorted: key order = creation order
        long sum = 0, rows = 0;
        try (PrintWriter p = new PrintWriter(new FileWriter(outDir() + "/files-" + tag + ".csv")))
        {
            p.println("idx,data_file_bytes,on_disk_length,level,rows");
            int i = 0;
            for (SSTableReader s : out)
            {
                long fl = new java.io.File(s.getFilename()).length();
                p.println((i++) + "," + fl + "," + s.onDiskLength() + "," + s.getSSTableLevel() + "," + s.getTotalRows());
                sum += fl;
                rows += s.getTotalRows();
            }
        }
        note("ARM " + tag + " maxSize=" + maxSize + " inputBytes=" + inLen + " partitionsAppended=" + parts + " outputs=" + out.size()
             + " outputBytes=" + sum + " outputRows=" + rows + " calls=" + w.n + " " + extra);
        return out;
    }
}
