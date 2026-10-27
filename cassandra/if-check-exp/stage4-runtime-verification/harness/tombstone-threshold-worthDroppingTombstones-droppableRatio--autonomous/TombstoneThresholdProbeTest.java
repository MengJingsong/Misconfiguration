/*
 * Stage 4, unit tier of tombstone-threshold-worthDroppingTombstones-droppableRatio--autonomous (B2 as amended, 2026-10-26).
 * Harness file, not upstream code. Runs inside the tree's CQLTester; writes STAGE4 lines to -Dstage4.out.
 * Package org.apache.cassandra.db.compaction so the protected worthDroppingTombstones / tombstoneThreshold are reachable.
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

public class TombstoneThresholdProbeTest extends CQLTester
{
    static final int N = 10000;
    static final double[] FS = { 0.1, 0.3, 0.6, 0.9 };
    static final String[] XS = { "0.0", "0.2", "0.5", "0.9", "1.5" };
    PrintWriter out;

    void p(String s) { out.println("STAGE4 " + s); out.flush(); }

    static String opts(String x, String interval, String unchecked)
    {
        return "{'class':'SizeTieredCompactionStrategy','enabled':'false','tombstone_threshold':'" + x
               + "','tombstone_compaction_interval':'" + interval + "','unchecked_tombstone_compaction':'" + unchecked + "'}";
    }

    long gcb() { return System.currentTimeMillis() / 1000 + 3600; }

    long bytes(ColumnFamilyStore cfs)
    {
        long b = 0;
        for (SSTableReader r : cfs.getLiveSSTables()) b += r.onDiskLength();
        return b;
    }

    /** fresh table, N partitions, first f*N with TTL 1, flushed, expired; returns the cfs */
    ColumnFamilyStore build(double f) throws Throwable
    {
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob) WITH gc_grace_seconds = 0 AND compaction = " + opts("0.2", "0", "true"));
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        cfs.disableAutoCompaction();
        Random rnd = new Random(42);
        int ttl = (int) Math.round(f * N);
        for (int i = 0; i < N; i++)
        {
            byte[] b = new byte[100];
            rnd.nextBytes(b);
            if (i < ttl) execute("UPDATE %s USING TTL 1 SET v = ? WHERE k = ?", ByteBuffer.wrap(b), i);
            else execute("UPDATE %s SET v = ? WHERE k = ?", ByteBuffer.wrap(b), i);
        }
        flush();
        Thread.sleep(2500);
        Assert.assertEquals("one sstable", 1, cfs.getLiveSSTables().size());
        return cfs;
    }

    SizeTieredCompactionStrategy strat(ColumnFamilyStore cfs, SSTableReader sst)
    {
        for (List<AbstractCompactionStrategy> l : cfs.getCompactionStrategyManager().getStrategies())
            for (AbstractCompactionStrategy s : l)
                if (s instanceof SizeTieredCompactionStrategy && ((SizeTieredCompactionStrategy) s).sstables.contains(sst))
                    return (SizeTieredCompactionStrategy) s;
        throw new AssertionError("no STCS holds the sstable");
    }

    void cell(ColumnFamilyStore cfs, double f, String gate, String x) throws Throwable
    {
        SSTableReader sst = cfs.getLiveSSTables().iterator().next();
        SizeTieredCompactionStrategy s = strat(cfs, sst);
        long g = gcb();
        double r = sst.getEstimatedDroppableTombstoneRatio(g);
        boolean worth = s.worthDroppingTombstones(sst, g);
        double thr = s.tombstoneThreshold;
        AbstractCompactionTask t = s.getNextBackgroundTask(g);
        boolean task = t != null;
        if (t != null) t.transaction.abort();
        p(String.format("cell f=%.1f gate=%s X=%s thr=%s r=%.6f worth=%b task=%b sstables=%d", f, gate, x, thr, r, worth, task, cfs.getLiveSSTables().size()));
        Assert.assertEquals("strategy threshold equals X after ALTER", Float.parseFloat(x), thr, 0.0);
    }

    @Test
    public void probe() throws Throwable
    {
        out = new PrintWriter(new FileWriter(System.getProperty("stage4.out", "/tmp/stage4-td.out")), true);
        p("start " + System.currentTimeMillis());
        for (double f : FS)
        {
            ColumnFamilyStore cfs = build(f);
            p(String.format("info f=%.1f r=%.6f bytes=%d", f, cfs.getLiveSSTables().iterator().next().getEstimatedDroppableTombstoneRatio(gcb()), bytes(cfs)));
            for (String x : XS)
            {
                alterTable("ALTER TABLE %s WITH compaction = " + opts(x, "0", "true"));
                cell(cfs, f, "open", x);
            }
            if (f == 0.6)
            {
                for (String x : XS)
                {
                    alterTable("ALTER TABLE %s WITH compaction = " + opts(x, "86400", "true"));
                    cell(cfs, f, "interval", x);
                }
                for (String x : XS)
                {
                    alterTable("ALTER TABLE %s WITH compaction = " + opts(x, "0", "false"));
                    cell(cfs, f, "nooverlap", x);
                }
                cfs.setNeverPurgeTombstones(true);
                for (String x : XS)
                {
                    alterTable("ALTER TABLE %s WITH compaction = " + opts(x, "0", "true"));
                    cell(cfs, f, "neverpurge", x);
                }
                cfs.setNeverPurgeTombstones(false);
                // second, overlapping sstable: 2000 other keys, no TTL
                Random rnd = new Random(7);
                for (int i = 0; i < 2000; i++)
                {
                    byte[] b = new byte[100];
                    rnd.nextBytes(b);
                    execute("UPDATE %s SET v = ? WHERE k = ?", ByteBuffer.wrap(b), 1000000 + i);
                }
                flush();
                Thread.sleep(500);
                for (String x : XS)
                {
                    alterTable("ALTER TABLE %s WITH compaction = " + opts(x, "0", "false"));
                    // two sstables now: evaluate the big (first) one
                    SSTableReader big = null;
                    for (SSTableReader r : cfs.getLiveSSTables()) if (big == null || r.onDiskLength() > big.onDiskLength()) big = r;
                    SizeTieredCompactionStrategy s = strat(cfs, big);
                    long g = gcb();
                    p(String.format("cell f=%.1f gate=overlap X=%s thr=%s r=%.6f worth=%b task=n/a sstables=%d", f, x, s.tombstoneThreshold,
                                    big.getEstimatedDroppableTombstoneRatio(g), s.worthDroppingTombstones(big, g), cfs.getLiveSSTables().size()));
                }
            }
        }
        // byte step
        for (double f : FS)
            for (String x : new String[]{ "0.2", "0.9" })
            {
                ColumnFamilyStore cfs = build(f);
                alterTable("ALTER TABLE %s WITH compaction = " + opts(x, "0", "true"));
                SSTableReader sst = cfs.getLiveSSTables().iterator().next();
                SizeTieredCompactionStrategy s = strat(cfs, sst);
                long g = gcb();
                double r = sst.getEstimatedDroppableTombstoneRatio(g);
                long before = bytes(cfs);
                AbstractCompactionTask t = s.getNextBackgroundTask(g);
                boolean task = t != null;
                if (t != null) t.execute(ActiveCompactionsTracker.NOOP);
                p(String.format("bytes f=%.1f X=%s r=%.6f task=%b before=%d after=%d", f, x, r, task, before, bytes(cfs)));
            }
        // positive control: forced compaction at X = 1.5
        for (double f : FS)
        {
            ColumnFamilyStore cfs = build(f);
            alterTable("ALTER TABLE %s WITH compaction = " + opts("1.5", "0", "true"));
            SSTableReader sst = cfs.getLiveSSTables().iterator().next();
            SizeTieredCompactionStrategy s = strat(cfs, sst);
            boolean worth = s.worthDroppingTombstones(sst, gcb());
            long before = bytes(cfs);
            cfs.forceMajorCompaction();
            p(String.format("control f=%.1f X=1.5 worth=%b before=%d after=%d", f, worth, before, bytes(cfs)));
        }
        p("end " + System.currentTimeMillis());
        out.close();
    }
}
