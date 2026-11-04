/*
 * Stage-4 harness (not upstream): unit tier B2 of
 * bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous, as amended 2026-10-27 (U1-U5).
 * Prints BFSTART / BFMARK / BFP / END lines; makes no assertions (selfcheck.py judges every line against B2f/U4/U5).
 * BFG_SHAKE=1 in the environment: N = 10 000 / 20 000 (shakedown, not judged).
 * Written for this case; the logging-initialisation idea is taken from
 * harness/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/BloomFpChanceMemoryTest.java.
 */
package org.apache.cassandra.utils;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.Util;
import org.apache.cassandra.config.DatabaseDescriptor;

public class BloomFpChanceSizeTest
{
    static final double[] FPS = { 0.001, 0.01, 0.1, 0.39, 0.5, 0.9999, 1.0 };

    // Initialise logging first, so System.out goes to TEST-<class>.log from the first line.
    static
    {
        org.slf4j.LoggerFactory.getLogger(BloomFpChanceSizeTest.class).info("BloomFpChanceSizeTest logging initialised");
    }

    @BeforeClass
    public static void setUp()
    {
        DatabaseDescriptor.daemonInitialization();
    }

    @Test
    public void run()
    {
        boolean shake = "1".equals(System.getenv("BFG_SHAKE"));
        int[] ns = shake ? new int[]{ 10_000, 20_000 } : new int[]{ 1_000_000, 2_000_000 };
        System.out.println("BFSTART shake=" + shake + " N=" + ns[0] + "," + ns[1] + " thread=" + Thread.currentThread().getName()
                           + " partitioner=" + DatabaseDescriptor.getPartitioner().getClass().getSimpleName());
        int cells = 0;
        for (int rep = 1; rep <= 2; rep++)
        {
            for (int n : ns)
            {
                for (double fp : FPS)
                {
                    String cell = "rep=" + rep + " N=" + n + " fp=" + fp;
                    System.out.println("BFMARK begin " + cell);
                    IFilter f = FilterFactory.getFilter((long) n, fp);
                    System.out.println("BFMARK end " + cell);
                    for (int i = 0; i < n; i++)
                        f.add(Util.dk(String.valueOf(i)));
                    String k = (f instanceof BloomFilter) ? Integer.toString(((BloomFilter) f).hashCount) : "-";
                    System.out.println("BFP " + cell + " class=" + f.getClass().getSimpleName() + " K=" + k
                                       + " offheap=" + f.offHeapSize() + " serialized=" + f.serializedSize(false));
                    f.close();
                    cells++;
                }
            }
        }
        System.out.println("END cells=" + cells);
    }
}
