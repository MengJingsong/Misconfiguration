/*
 * Stage-4 harness (not upstream): unit tier B2 of
 * bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous, as amended 2026-10-27 (U1-U4).
 * Prints BFSPEC / BFP / END lines; makes no assertions (selfcheck.py judges every line against B2f/U3).
 * BFM_SHAKE=1 in the environment: N = 10 000 / 20 000, M = 100 000 (shakedown, not judged).
 */
package org.apache.cassandra.utils;

import org.junit.Test;

import org.apache.cassandra.db.BufferDecoratedKey;
import org.apache.cassandra.dht.Murmur3Partitioner.LongToken;
import org.apache.cassandra.utils.IFilter.FilterKey;

public class BloomFpChanceMemoryTest
{
    static final double[] FPS = { 1.0, 0.5, 0.393, 0.2, 0.1, 0.01, 0.001, 0.0001, 0.0000672, 0.0000671 };
    static final double EXTRA = 0.00006; // U2: below probs[20][14]

    // Initialise logging first: the test logback config routes System.out to TEST-<class>.log only after it starts,
    // so a line printed before that would land in ant's output instead (shakedown finding, 2026-10-27).
    static
    {
        org.slf4j.LoggerFactory.getLogger(BloomFpChanceMemoryTest.class).info("BloomFpChanceMemoryTest logging initialised");
    }

    static FilterKey key(int i)
    {
        return new BufferDecoratedKey(new LongToken(0L), ByteBufferUtil.bytes(i));
    }

    static void spec(double fp)
    {
        try
        {
            BloomCalculations.BloomSpecification s = BloomCalculations.computeBloomSpec(20, fp);
            System.out.println("BFSPEC fp=" + fp + " bpe=" + s.bucketsPerElement + " K=" + s.K);
        }
        catch (Throwable t)
        {
            System.out.println("BFSPEC fp=" + fp + " THROWS " + t.getClass().getName() + ": " + t.getMessage());
        }
    }

    @Test
    public void run()
    {
        boolean shake = "1".equals(System.getenv("BFM_SHAKE"));
        int[] ns = shake ? new int[]{ 10_000, 20_000 } : new int[]{ 1_000_000, 2_000_000 };
        int m = shake ? 100_000 : 1_000_000;
        System.out.println("BFMSTART shake=" + shake + " N=" + ns[0] + "," + ns[1] + " M=" + m);
        int nspec = 0, nbfp = 0;
        for (double fp : FPS) { spec(fp); nspec++; }
        spec(EXTRA); nspec++;
        for (int rep = 1; rep <= 2; rep++)
        {
            for (int n : ns)
            {
                for (double fp : FPS)
                {
                    String head = "BFP rep=" + rep + " N=" + n + " fp=" + fp;
                    IFilter f;
                    try
                    {
                        f = FilterFactory.getFilter(n, fp);
                    }
                    catch (Throwable t)
                    {
                        System.out.println(head + " THROWS " + t.getClass().getName() + ": " + t.getMessage());
                        nbfp++;
                        continue;
                    }
                    for (int i = 0; i < n; i++)
                        f.add(key(i));
                    long cnt = 0;
                    for (int j = 0; j < m; j++)
                        if (f.isPresent(key(1_000_000_000 + j)))
                            cnt++;
                    String k = (f instanceof BloomFilter) ? Integer.toString(((BloomFilter) f).hashCount) : "-";
                    System.out.println(head + " class=" + f.getClass().getSimpleName() + " K=" + k
                                       + " offheap=" + f.offHeapSize() + " serialized=" + f.serializedSize(false)
                                       + " fpcount=" + cnt + " absent=" + m);
                    f.close();
                    nbfp++;
                }
            }
        }
        System.out.println("END bfspec=" + nspec + " bfp=" + nbfp);
    }
}
