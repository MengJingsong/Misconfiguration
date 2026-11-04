package org.apache.cassandra.db.compaction.unified;

import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.compaction.ShardManagerNoDisks;
import org.apache.cassandra.db.compaction.ShardTracker;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.dht.Range;
import org.apache.cassandra.dht.Splitter;
import org.apache.cassandra.dht.Token;

/**
 * Stage-4 unit probe for max_shard_split-getnumshards-count--autonomous (B2). Every reading is a "STAGE4 ..." line on stdout.
 * Cells: sstable_growth {0, 0.333, 1} x target {1MiB, 1GiB} x base {1, 4, 2047, 2048, 4096} x densities (B2c); control: min_sstable_size = 100MiB; tracker heap.
 */
public class ShardCapProbeTest
{
    @BeforeClass
    public static void setUpClass() { DatabaseDescriptor.daemonInitialization(); }

    static Controller ctl(String growth, String target, int base, String min)
    {
        Map<String, String> o = new HashMap<>();
        o.put(Controller.SSTABLE_GROWTH_OPTION, growth);
        o.put(Controller.TARGET_SSTABLE_SIZE_OPTION, target);
        o.put(Controller.BASE_SHARD_COUNT_OPTION, Integer.toString(base));
        o.put(Controller.MIN_SSTABLE_SIZE_OPTION, min);
        Controller.validateOptions(o);
        return Controller.fromOptions(null, o);
    }

    static void p(String s) { System.out.println("STAGE4 " + s); System.out.flush(); }

    @Test
    public void sweep()
    {
        p("MAX_SHARD_SPLIT=" + (long) Controller.MAX_SHARD_SPLIT + " MAX_SHARD_SHIFT=" + Controller.MAX_SHARD_SHIFT);
        String[] growths = { "0", "0.333", "1" };
        String[] targets = { "1MiB", "1GiB" };
        long[] tbytes = { 1L << 20, 1L << 30 };
        int[] bases = { 1, 4, 2047, 2048, 4096 };
        for (String g : growths)
            for (int ti = 0; ti < targets.length; ti++)
                for (int b : bases)
                {
                    Controller c = ctl(g, targets[ti], b, "0MiB");
                    double K = Math.scalb(1.0, 20) * Math.sqrt(0.5) * tbytes[ti] * b;
                    double[] ds = { K / 4, K / 2, K * 0.99, K * 1.01, 2 * K, Math.scalb(K, 10), Math.scalb(K, 40),
                                    Double.MAX_VALUE, Double.POSITIVE_INFINITY, Double.NaN, 0 };
                    String[] names = { "K/4", "K/2", "0.99K", "1.01K", "2K", "2^10K", "2^40K", "MAX_VALUE", "+Inf", "NaN", "0" };
                    for (int i = 0; i < ds.length; i++)
                    {
                        int r1 = c.getNumShards(ds[i]);
                        int r2 = c.getNumShards(ds[i]); // repeated: no state
                        p("shards growth=" + g + " target=" + targets[ti] + " base=" + b + " d=" + names[i] + " dval=" + ds[i] + " K=" + K
                          + " shards=" + r1 + " repeat=" + r2 + " cap=" + ((long) b << 20));
                    }
                }
        // positive control: min_sstable_size = 100MiB, base 4, growth 0, target 1GiB -> below baseShardCount the count follows density/min
        for (String min : new String[]{ "100MiB", "0MiB" })
        {
            Controller c = ctl("0", "1GiB", 4, min);
            for (double d : new double[]{ 0, 50e6, 150e6 * 1, 220e6, 450e6, 1000e6 })
                p("control-min min=" + min + " base=4 target=1GiB growth=0 d=" + d + " shards=" + c.getNumShards(d));
        }
    }

    static long heap() throws Exception
    {
        for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(100); }
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    @Test
    public void trackerHeap() throws Exception
    {
        Murmur3Partitioner part = Murmur3Partitioner.instance;
        ColumnFamilyStore.VersionedLocalRanges lr = new ColumnFamilyStore.VersionedLocalRanges(0, 1);
        lr.add(new Splitter.WeightedRange(1.0, new Range<>(part.getMinimumToken(), part.getMaximumToken())));
        ShardManagerNoDisks sm = new ShardManagerNoDisks(lr);
        int K = 20000;
        for (int rep = 0; rep < 3; rep++)
            for (int shards : new int[]{ 4, 1 << 10, 1 << 20 })
            {
                long h0 = heap();
                List<ShardTracker> keep = new ArrayList<>(K);
                for (int i = 0; i < K; i++) keep.add(sm.boundaries(shards));
                long h1 = heap();
                // exercise one advance through a mid-ring token
                ShardTracker t = keep.get(0);
                Token mid = part.getToken(java.nio.ByteBuffer.wrap(new byte[]{ 1, 2, 3, 4, 5, 6, 7, 8 }));
                boolean adv = t.advanceTo(mid);
                p("tracker rep=" + rep + " shards=" + shards + " count=" + t.count() + " trackers=" + K + " heapDelta=" + (h1 - h0)
                  + " perTracker=" + ((h1 - h0) / (double) K) + " advance=" + adv + " shardIndex=" + t.shardIndex());
                keep.clear();
            }
    }
}
