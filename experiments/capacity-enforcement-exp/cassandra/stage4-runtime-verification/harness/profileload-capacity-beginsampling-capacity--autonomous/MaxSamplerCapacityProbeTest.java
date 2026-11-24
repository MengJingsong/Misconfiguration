package org.apache.cassandra.metrics;

import java.lang.reflect.Field;
import java.util.Random;
import com.google.common.collect.MinMaxPriorityQueue;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.utils.ObjectSizes;

public class MaxSamplerCapacityProbeTest
{
    static final int N = 50_000;
    static final int[] CAPS = { -5, 0, 1, 10, 256, 1024, 10_000, 100_000 };

    @BeforeClass
    public static void init() { DatabaseDescriptor.daemonInitialization(); }

    static MaxSampler<String> newSampler()
    {
        return new MaxSampler<String>() { public String toString(String v) { return v; } };
    }

    static MinMaxPriorityQueue<?> queue(MaxSampler<?> s) throws Exception
    {
        Field f = MaxSampler.class.getDeclaredField("queue"); f.setAccessible(true);
        return (MinMaxPriorityQueue<?>) f.get(s);
    }

    static void setField(MaxSampler<?> s, int v) throws Exception
    {
        Field f = MaxSampler.class.getDeclaredField("capacity"); f.setAccessible(true); f.setInt(s, v);
    }

    static void run(MaxSampler<String> s, boolean asc, int n)
    {
        Random r = new Random(42);
        for (int i = 0; i < n; i++)
            s.insert("k" + i, asc ? i + 1 : 1 + r.nextInt(1_000_000));
    }

    @Test
    public void probe() throws Exception
    {
        for (boolean asc : new boolean[]{ true, false })
            for (int cap : CAPS)
            {
                MaxSampler<String> s = newSampler();
                s.beginSampling(cap, 3_600_000L);
                run(s, asc, N);
                MinMaxPriorityQueue<?> q = queue(s);
                long bytes = ObjectSizes.measureDeep(q);
                int expected = Math.min(Math.max(1, cap), N);
                System.out.println(String.format("RESULT order=%s cap=%d N=%d size=%d expected=%d bytes=%d bytesPerEntry=%.1f",
                                  asc ? "ASC" : "RND", cap, N, q.size(), expected, bytes, (double) bytes / q.size()));
                Assert.assertEquals(expected, q.size());
            }
    }

    // Control: which line bounds the container. Field (line 48) forced huge after begin(10): bound must still be 10.
    @Test
    public void fieldVersusMaximumSize() throws Exception
    {
        MaxSampler<String> s = newSampler();
        s.beginSampling(10, 3_600_000L);
        setField(s, Integer.MAX_VALUE);
        run(s, false, N);
        System.out.println(String.format("RESULT control=fieldHuge cap=10 size=%d", queue(s).size()));
        Assert.assertEquals(10, queue(s).size());
    }

    // Baseline: no beginSampling -> inactive, nothing retained.
    @Test
    public void inactiveBaseline() throws Exception
    {
        MaxSampler<String> s = newSampler();
        run(s, true, N);
        System.out.println(String.format("RESULT control=inactive queue=%s", queue(s)));
        Assert.assertNull(queue(s));
    }
}
