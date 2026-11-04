/*
 * Stage-4 unit tier (B2, as amended 2026-10-26) of
 * bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous.
 * Not upstream code: copied into the run clone by unit-run.sh and removed afterwards.
 * Every reading is one System.out.println line with prefix "BFP ".
 * BFP_SHAKE=1 (shakedown, not judged): N = 10,000 and 40,000 with 10,000 absent keys.
 */
package org.apache.cassandra.utils;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.schema.TableParams;

public class BloomFpChanceCapTest
{
    private static final boolean SHAKE = "1".equals(System.getenv("BFP_SHAKE"));
    private static final long[] NS = SHAKE ? new long[]{ 10_000L, 40_000L } : new long[]{ 1_000_000L, 4_000_000L };
    private static final long ABSENT = SHAKE ? 10_000L : 1_000_000L;
    private static final double[] ACCEPTED = { 1.0, 0.1, 0.01, 0.001, 0.0001, 0.00007 };
    private static final double[] BOUNDARY = { 6.71e-05, 6.0e-05, 1.0000001, 0, -0.1 };

    @BeforeClass
    public static void init()
    {
        DatabaseDescriptor.daemonInitialization();
    }

    private static DecoratedKey key(long i)
    {
        return Murmur3Partitioner.instance.decorateKey(ByteBufferUtil.bytes(i));
    }

    private static String validate(double fp)
    {
        try
        {
            TableParams.builder().bloomFilterFpChance(fp).build().validate();
            return "ok";
        }
        catch (Throwable t)
        {
            return "threw:" + t.getClass().getSimpleName() + ":" + t.getMessage();
        }
    }

    @Test
    public void probe()
    {
        System.out.println("BFP start shake=" + SHAKE + " absent=" + ABSENT + " min=" + BloomCalculations.minSupportedBloomFilterFpChance());
        for (long n : NS)
        {
            for (double fp : ACCEPTED)
            {
                try
                {
                    IFilter filter = FilterFactory.getFilter(n, fp);
                    String hc = filter instanceof BloomFilter ? Integer.toString(((BloomFilter) filter).hashCount) : "-";
                    long off = filter.offHeapSize();
                    long ser = filter.serializedSize(false);
                    for (long i = 0; i < n; i++)
                        filter.add(key(i));
                    long fpCount = 0;
                    for (long i = n; i < n + ABSENT; i++)
                        if (filter.isPresent(key(i)))
                            fpCount++;
                    long missing = 0;   // a Bloom filter has no false negatives; checked on the first 1000 inserted keys
                    for (long i = 0; i < Math.min(n, 1000); i++)
                        if (!filter.isPresent(key(i)))
                            missing++;
                    System.out.println("BFP filter N=" + n + " fp=" + fp + " class=" + filter.getClass().getSimpleName()
                                       + " hashCount=" + hc + " offHeap=" + off + " serialized=" + ser
                                       + " fpCount=" + fpCount + " falseNeg=" + missing + " validate=" + validate(fp));
                    filter.close();
                }
                catch (Throwable t)
                {
                    System.out.println("BFP filter N=" + n + " fp=" + fp + " error=" + t.getClass().getSimpleName() + ":" + t.getMessage());
                }
            }
        }
        for (double fp : BOUNDARY)
        {
            String v = validate(fp);
            if (v.equals("ok"))
                System.out.println("BFP reject fp=" + fp + " threw=none msg=-");
            else
            {
                String[] p = v.split(":", 3);
                System.out.println("BFP reject fp=" + fp + " threw=" + p[1] + " msg=" + p[2]);
            }
        }
        for (long n : NS)
        {
            try
            {
                IFilter f = FilterFactory.getFilter(n, 6.0e-05);
                System.out.println("BFP direct N=" + n + " fp=6.0E-5 threw=none msg=offHeap " + f.offHeapSize());
                f.close();
            }
            catch (Throwable t)
            {
                System.out.println("BFP direct N=" + n + " fp=6.0E-5 threw=" + t.getClass().getSimpleName() + " msg=" + t.getMessage());
            }
        }
        System.out.println("BFP done");
    }
}
