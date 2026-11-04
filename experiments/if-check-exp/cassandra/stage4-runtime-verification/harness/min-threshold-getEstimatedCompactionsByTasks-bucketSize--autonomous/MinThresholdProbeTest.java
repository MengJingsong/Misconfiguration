/*
 * Stage 4, unit tier of min-threshold-getEstimatedCompactionsByTasks-bucketSize--autonomous (B2 as amended, 2026-10-27).
 * Harness file, not upstream code. Runs inside the tree's CQLTester; writes STAGE4 lines to -Dstage4.out.
 * Package org.apache.cassandra.db.compaction so the protected sstables / sizeTieredOptions / transaction are reachable.
 */
package org.apache.cassandra.db.compaction;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.Random;

import org.junit.Assert;
import org.junit.Test;

import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.io.sstable.format.SSTableReader;

public class MinThresholdProbeTest extends CQLTester
{
    PrintWriter out;
    int key = 0;
    Random rnd = new Random(42);

    void p(String s) { out.println("STAGE4 " + s); out.flush(); }

    /** fresh table with n flushed sstables of ~1 MiB (1000 rows x 1 KiB), auto compaction off */
    ColumnFamilyStore build(int n) throws Throwable
    {
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob) WITH compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false','min_threshold':'4','max_threshold':'32'}");
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        cfs.disableAutoCompaction();
        for (int f = 0; f < n; f++)
        {
            for (int i = 0; i < 1000; i++)
            {
                byte[] b = new byte[1024];
                rnd.nextBytes(b);
                execute("INSERT INTO %s (k, v) VALUES (?, ?)", key++, ByteBuffer.wrap(b));
            }
            flush();
        }
        Assert.assertEquals("sstables", n, cfs.getLiveSSTables().size());
        return cfs;
    }

    SizeTieredCompactionStrategy strat(ColumnFamilyStore cfs)
    {
        SizeTieredCompactionStrategy found = null;
        for (List<AbstractCompactionStrategy> l : cfs.getCompactionStrategyManager().getStrategies())
            for (AbstractCompactionStrategy s : l)
                if (s instanceof SizeTieredCompactionStrategy && !((SizeTieredCompactionStrategy) s).sstables.isEmpty())
                {
                    Assert.assertNull("one STCS holds the sstables", found);
                    found = (SizeTieredCompactionStrategy) s;
                }
        Assert.assertNotNull(found);
        return found;
    }

    long bytes(ColumnFamilyStore cfs)
    {
        long b = 0;
        for (SSTableReader r : cfs.getLiveSSTables()) b += r.onDiskLength();
        return b;
    }

    long heap()
    {
        System.gc(); System.gc();
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    long gcb() { return System.currentTimeMillis() / 1000; }

    void cell(ColumnFamilyStore cfs, int n, int min) throws Throwable
    {
        cfs.setMinimumCompactionThreshold(min);
        SizeTieredCompactionStrategy s = strat(cfs);
        long before = bytes(cfs);
        AbstractCompactionTask t = s.getNextBackgroundTask(gcb());
        int est = s.getEstimatedRemainingTasks();
        boolean task = t != null;
        int taskSize = task ? t.transaction.originals().size() : 0;
        if (t != null) t.transaction.abort();
        int csm = cfs.getCompactionStrategyManager().getEstimatedRemainingTasks();
        Object gauge = cfs.metric.pendingCompactions.getValue();
        p(String.format("cell n=%d min=%d max=%d est=%d csm=%d gauge=%s task=%b taskSstables=%d sstables=%d bytes=%d live=%d total=%d heap=%d",
                        n, min, cfs.getMaximumCompactionThreshold(), est, csm, gauge, task, taskSize, cfs.getLiveSSTables().size(),
                        bytes(cfs), cfs.metric.liveDiskSpaceUsed.getCount(), cfs.metric.totalDiskSpaceUsed.getCount(), heap()));
        Assert.assertEquals("bytes unchanged by the call", before, bytes(cfs));
    }

    @Test
    public void probe() throws Throwable
    {
        out = new PrintWriter(new FileWriter(System.getProperty("stage4.out", "/tmp/stage4-mt.out")), true);
        p("start " + System.currentTimeMillis());
        // warm-up (not a reading): the first call in a JVM allocates once (shakedown: +2 MiB heap in the first cell); run one throwaway
        // table through the same calls so the recorded cells compare like with like
        {
            ColumnFamilyStore w = build(8);
            for (int m : new int[]{ 2, 9 })
            {
                w.setMinimumCompactionThreshold(m);
                SizeTieredCompactionStrategy ws = strat(w);
                AbstractCompactionTask wt = ws.getNextBackgroundTask(gcb());
                if (wt != null) wt.transaction.abort();
                w.getCompactionStrategyManager().getEstimatedRemainingTasks();
                heap();
            }
            p("warmup done (not a reading)");
        }
        // sweep n=8 and n=40
        for (int n : new int[]{ 8, 40 })
        {
            ColumnFamilyStore cfs = build(n);
            SizeTieredCompactionStrategy s = strat(cfs);
            List<List<SSTableReader>> b = SizeTieredCompactionStrategy.getBuckets(
                SizeTieredCompactionStrategy.createSSTableAndLengthPairs(cfs.getLiveSSTables()),
                s.sizeTieredOptions.bucketHigh, s.sizeTieredOptions.bucketLow, s.sizeTieredOptions.minSSTableSize);
            p(String.format("buckets n=%d count=%d sizes=%s", n, b.size(), b.stream().map(List::size).collect(java.util.stream.Collectors.toList())));
            // I2: validation (min above max) cannot be set
            String thrown = "none";
            try { cfs.setMinimumCompactionThreshold(33); } catch (RuntimeException e) { thrown = "RuntimeException"; }
            p(String.format("validate min=33 max=%d -> %s min-now=%d", cfs.getMaximumCompactionThreshold(), thrown, cfs.getMinimumCompactionThreshold()));
            for (int min : (n == 8 ? new int[]{ 2, 4, 8, 9 } : new int[]{ 2, 4, 9 }))
                cell(cfs, n, min);
            // repeat the sweep in reverse order: the estimate must depend on min only, not on history
            for (int min : (n == 8 ? new int[]{ 9, 8, 4, 2 } : new int[]{ 9, 4, 2 }))
                cell(cfs, n, min);
        }
        // positive control 1 (B2h): run the (4,8) compaction; sstables 8 -> 1
        {
            ColumnFamilyStore cfs = build(8);
            cfs.setMinimumCompactionThreshold(4);
            SizeTieredCompactionStrategy s = strat(cfs);
            long before = bytes(cfs);
            int cnt = cfs.getLiveSSTables().size();
            AbstractCompactionTask t = s.getNextBackgroundTask(gcb());
            int in = t.transaction.originals().size();
            t.execute(ActiveCompactionsTracker.NOOP);
            p(String.format("control-exec n=8 min=4 inputs=%d sstables-before=%d sstables-after=%d bytes-before=%d bytes-after=%d total-after=%d",
                            in, cnt, cfs.getLiveSSTables().size(), before, bytes(cfs), cfs.metric.totalDiskSpaceUsed.getCount()));
        }
        // positive control 2 (B2h): max_threshold 4 vs 32 with 40 sstables; task width and input bytes (the temporary-space bound)
        {
            ColumnFamilyStore cfs = build(40);
            cfs.setMinimumCompactionThreshold(4);
            for (int max : new int[]{ 4, 32, 4 })
            {
                cfs.setMaximumCompactionThreshold(max);
                SizeTieredCompactionStrategy s = strat(cfs);
                AbstractCompactionTask t = s.getNextBackgroundTask(gcb());
                long inBytes = 0;
                for (SSTableReader r : t.transaction.originals()) inBytes += r.onDiskLength();
                p(String.format("control-max n=40 min=4 max=%d est=%d inputs=%d input-bytes=%d", max, s.getEstimatedRemainingTasks(), t.transaction.originals().size(), inBytes));
                t.transaction.abort();
            }
        }
        p("end " + System.currentTimeMillis());
        out.close();
    }
}
