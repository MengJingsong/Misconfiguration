package org.apache.cassandra.utils;

import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.util.Arrays;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.dht.Range;
import org.apache.cassandra.dht.Token;

/**
 * Unit tier probe for repair-session-space-histogram-add-values--autonomous (B2). Standalone main, compiled against the tree's build/classes/main.
 * It sits in package org.apache.cassandra.utils because MerkleTree.histogramOf*PerLeaf and TreeRangeIterator are package-private.
 *
 *   direct <n> [n ...]            HistogramBuilder alone: add n values, read the private values.length by reflection.
 *   tree <S> <RF> <D> [reps]      Budget -> depth exactly as ValidationManager.createMerkleTrees (lines 62-80, int arithmetic included),
 *                                 tree via MerkleTrees.addMerkleTree + init, then histogramOfRowCountPerLeaf() with thread-allocated bytes.
 *   known <n>                     known-answer driver for the JFR instrument check: one builder with n adds (no other work).
 * Output: one RESULT line per measurement (key=value), nothing is judged here.
 */
public class HistogramBudgetProbe
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

    static long alloc() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    static int valuesLength(HistogramBuilder b) throws Exception
    {
        Field f = HistogramBuilder.class.getDeclaredField("values");
        f.setAccessible(true);
        return ((long[]) f.get(b)).length;
    }

    static long arrayBytes(int len) { return 16L + 8L * len; }

    public static void main(String[] a) throws Exception
    {
        String mode = a[0];
        if (mode.equals("direct") || mode.equals("known"))
        {
            for (int i = 1; i < a.length; i++)
            {
                long n = Long.parseLong(a[i]);
                System.gc();
                long before = alloc();
                HistogramBuilder b = new HistogramBuilder();
                for (long k = 0; k < n; k++) b.add(k);
                long used = alloc() - before;
                int len = valuesLength(b);
                System.out.println("RESULT mode=" + mode + " n=" + n + " values_length=" + len + " array_bytes=" + arrayBytes(len) + " thread_alloc=" + used);
            }
            return;
        }
        if (!mode.equals("tree")) throw new IllegalArgumentException(mode);
        int S = Integer.parseInt(a[1]), RF = Integer.parseInt(a[2]), D = Integer.parseInt(a[3]);
        int reps = a.length > 4 ? Integer.parseInt(a[4]) : 3;
        DatabaseDescriptor.daemonInitialization();
        DatabaseDescriptor.setRepairSessionSpaceInMiB(S);
        DatabaseDescriptor.setRepairSessionMaxTreeDepth(D);
        Murmur3Partitioner p = Murmur3Partitioner.instance;

        // ValidationManager.java:62-63 (int * int, then / int, widened to long afterwards), :70-79 with rangeOwningRatio = 1, numPartitions >= 2^depth
        long availableBytes = (DatabaseDescriptor.getRepairSessionSpaceInMiB() * 1048576) / RF;
        int rangeAvailableBytes = Math.max(1, (int) (1.0 * availableBytes));
        int estimatedMaxDepth = MerkleTree.estimatedMaxDepthForBytes(p, rangeAvailableBytes, 32);
        int maxDepth = Math.min(estimatedMaxDepth, DatabaseDescriptor.getRepairSessionMaxTreeDepth());
        long numPartitions = 1L << 30;
        int depth = (int) Math.min(Math.ceil(Math.log(numPartitions) / Math.log(2)), maxDepth);

        Token min = p.getMinimumToken();
        Range<Token> full = new Range<>(min, min);
        MerkleTrees trees = new MerkleTrees(p);
        MerkleTree tree = trees.addMerkleTree((int) Math.pow(2, depth), full);
        tree.init();
        long leaves = tree.size();
        long treeDeep = ObjectSizes.measureDeep(tree);
        long[] hist = new long[reps], ctl = new long[reps];
        for (int r = 0; r < reps + 1; r++)
        {
            System.gc();
            long b0 = alloc();
            tree.histogramOfRowCountPerLeaf();
            long used = alloc() - b0;
            System.gc();
            long b1 = alloc();
            long cnt = 0;
            try (MerkleTree.TreeRangeIterator it = tree.rangeIterator())
            {
                for (MerkleTree.TreeRange tr : it) cnt++; // iteration only: TreeRange.node is private, so no partitionsInRange() here
            }
            long used2 = alloc() - b1;
            if (r > 0) { hist[r - 1] = used; ctl[r - 1] = used2; } // r = 0 is the warm-up
        }
        Arrays.sort(hist); Arrays.sort(ctl);
        // the builder the tree method used saw `leaves` values: build the same count directly to read its capacity
        HistogramBuilder b = new HistogramBuilder();
        for (long k = 0; k < leaves; k++) b.add(k);
        int len = valuesLength(b);
        System.out.println("RESULT mode=tree S=" + S + " RF=" + RF + " D=" + D + " availableBytes=" + availableBytes + " rangeAvailableBytes=" + rangeAvailableBytes
                           + " estimatedMaxDepth=" + estimatedMaxDepth + " depth=" + depth + " leaves=" + leaves + " tree_measureDeep=" + treeDeep
                           + " hash_array_bytes=" + ObjectSizes.measureDeep(new byte[32]) + " tree_bytes_per_leaf=" + (treeDeep / Math.max(1, leaves)) + " values_length=" + len + " array_bytes=" + arrayBytes(len)
                           + " hist_alloc_median=" + hist[reps / 2] + " iter_only_alloc_median=" + ctl[reps / 2]
                           + " hist_alloc_all=" + Arrays.toString(hist));
    }
}
