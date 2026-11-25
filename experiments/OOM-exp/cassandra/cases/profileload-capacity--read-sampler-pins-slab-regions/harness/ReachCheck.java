package org.apache.cassandra.metrics;

import java.io.File;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

/**
 * B25 Step A (3): known-answer check of hprof_reach.py's cut 'sampler' (design §2.5). Runs in a test JVM with the U jar on the
 * classpath (never in the node). Real MaxSampler / FrequencySampler instances (anonymous subclasses, as TableMetrics makes them),
 * beginSampling(256, 600000), then insert() directly (same package):
 *   - 10 slices of 10 distinct byte[1048576] held ONLY by the samplers (5 in the MaxSampler queue, 5 in the FrequencySampler summary);
 *   - 5 slices whose arrays are ALSO in the static list KEEP (3 MaxSampler, 2 FrequencySampler);
 *   - 7 arrays only in KEEP.
 * Expected: reachable regions 22, R_s = 10. Everything is built in a separate method so that no frame local of main() is a root.
 * usage: ReachCheck <ready file> <stop file>
 */
public class ReachCheck
{
    static final List<Object> KEEP = new ArrayList<>();
    static MaxSampler<ByteBuffer> MAX;
    static FrequencySampler<ByteBuffer> FREQ;

    static ByteBuffer slice(byte[] a, int off)
    {
        // distinct content per slice: StreamSummary keys by ByteBuffer.equals (content), as distinct partition keys are
        for (int k = 0; k < 12; k++) a[off + k] = (byte) (off * 31 + k);
        ByteBuffer b = ByteBuffer.wrap(a).duplicate();
        b.position(off).limit(off + 12);
        return b.slice();
    }

    static void build()
    {
        MAX = new MaxSampler<ByteBuffer>() { public String toString(ByteBuffer v) { return "x"; } };
        FREQ = new FrequencySampler<ByteBuffer>() { public String toString(ByteBuffer v) { return "x"; } };
        MAX.beginSampling(256, 600_000);
        FREQ.beginSampling(256, 600_000);
        for (int i = 0; i < 10; i++)
        {
            byte[] a = new byte[1048576];
            a[0] = (byte) i;
            if (i < 5) MAX.insert(slice(a, 1000 + i), 1 + i);
            else FREQ.insert(slice(a, 1000 + i), 1);
        }
        for (int i = 0; i < 5; i++)
        {
            byte[] a = new byte[1048576];
            KEEP.add(a);
            if (i < 3) MAX.insert(slice(a, 2000 + i), 10 + i);
            else FREQ.insert(slice(a, 2000 + i), 1);
        }
        for (int i = 0; i < 7; i++)
            KEEP.add(new byte[1048576]);
    }

    public static void main(String[] a) throws Exception
    {
        build();
        File ready = new File(a[0]), stop = new File(a[1]);
        ready.createNewFile();
        while (!stop.exists()) Thread.sleep(100);
        System.out.println("held " + KEEP.size() + " " + (MAX != null) + " " + (FREQ != null));
    }
}
