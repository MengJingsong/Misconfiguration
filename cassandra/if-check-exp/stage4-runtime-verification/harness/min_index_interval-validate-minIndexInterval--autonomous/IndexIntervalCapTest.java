/*
 * Stage-4 unit tier (B2, as amended 2026-10-26) of
 * min_index_interval-validate-minIndexInterval--autonomous.
 * Not upstream code: copied into the run clone by unit-run.sh and removed afterwards.
 * Every reading is one System.out.println line with prefix "MII ".
 * MII_SHAKE=1 (shakedown, not judged): N = 10,000.
 */
package org.apache.cassandra.io.sstable.indexsummary;

import java.util.Arrays;
import java.util.Comparator;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.dht.IPartitioner;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.schema.TableParams;
import org.apache.cassandra.utils.ByteBufferUtil;

public class IndexIntervalCapTest
{
    private static final boolean SHAKE = "1".equals(System.getenv("MII_SHAKE"));
    private static final int N = SHAKE ? 10_000 : 1_000_000;
    private static final int[] MS = { 1, 16, 128, 512 };
    private static final int[] DOWN_MAX = { 2048, 512 };

    @BeforeClass
    public static void init()
    {
        DatabaseDescriptor.daemonInitialization();
    }

    private static String line(IndexSummary s)
    {
        long alloc = s.getOffsets().size() + s.getEntries().size();
        return "size=" + s.size() + " offHeap=" + s.getOffHeapSize() + " alloc=" + alloc + " level=" + s.getSamplingLevel()
               + " interval=" + s.getEffectiveIndexInterval() + " maxEntries=" + s.getMaxNumberOfEntries();
    }

    private static String validate(TableParams.Builder b)
    {
        try
        {
            b.build().validate();
            return "ok";
        }
        catch (Throwable t)
        {
            return "threw:" + t.getClass().getSimpleName() + ":" + t.getMessage();
        }
    }

    @Test
    public void probe() throws Exception
    {
        IPartitioner p = Murmur3Partitioner.instance;
        System.out.println("MII start shake=" + SHAKE + " N=" + N + " expectedKeySize=" + IndexSummaryBuilder.defaultExpectedKeySize);
        DecoratedKey[] keys = new DecoratedKey[N];
        for (int i = 0; i < N; i++)
            keys[i] = p.decorateKey(ByteBufferUtil.bytes((long) i));
        Arrays.sort(keys, Comparator.naturalOrder());
        System.out.println("MII keys n=" + N + " keyLen=" + keys[0].getKey().remaining());

        IndexSummary s128 = null;
        int size128 = 0;
        for (int m : MS)
        {
            try (IndexSummaryBuilder b = new IndexSummaryBuilder(N, m, 128))
            {
                for (int i = 0; i < N; i++)
                    b.maybeAddEntry(keys[i], i * 100L);
                b.prepareToCommit();
                IndexSummary s = b.build(p);
                System.out.println("MII build m=" + m + " " + line(s));
                if (m == 128)
                {
                    s128 = s;
                    size128 = s.size();
                }
                else
                {
                    s.close();
                }
            }
            catch (Throwable t)
            {
                System.out.println("MII build m=" + m + " error=" + t);
            }
        }

        for (int M : DOWN_MAX)
        {
            int target = (int) Math.ceil(128 * 128 / (double) M);
            try (IndexSummary d = IndexSummaryBuilder.downsample(s128, target, 128, p))
            {
                System.out.println("MII down m=128 M=" + M + " target=" + target + " " + line(d));
            }
            catch (Throwable t)
            {
                System.out.println("MII down m=128 M=" + M + " error=" + t);
            }
        }
        if (s128 != null)
            s128.close();

        System.out.println("MII validate case=0/default result=" + validate(TableParams.builder().minIndexInterval(0)));
        System.out.println("MII validate case=-5/default result=" + validate(TableParams.builder().minIndexInterval(-5)));
        System.out.println("MII validate case=128/127 result=" + validate(TableParams.builder().minIndexInterval(128).maxIndexInterval(127)));
        System.out.println("MII validate case=128/128 result=" + validate(TableParams.builder().minIndexInterval(128).maxIndexInterval(128)));

        for (int M : DOWN_MAX)
            System.out.println("MII calc M=" + M + " level=" + IndexSummaryBuilder.calculateSamplingLevel(128, size128, 1, 128, M));
        System.out.println("MII done");
    }
}
