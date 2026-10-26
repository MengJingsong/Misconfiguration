import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

import org.apache.cassandra.io.compress.BufferType;
import org.apache.cassandra.utils.memory.BufferPool;
import org.apache.cassandra.utils.memory.BufferPools;

/**
 * Positive control for the cluster tier (audit amendment R11): inside the node's own JVM, 400 x 64 KiB buffers are taken from
 * and held in the chunk-cache pool (the same BufferPool code and threshold the hint reader uses), then given back. Triggered by
 * hu-inject.btm (HintsDispatchTrigger.run, every 10 s) when the flag file exists in -Dstage4.flagdir. Counters before/after go
 * to <flagdir>/inject.log. Not a production path: a stand-in for traffic that is known to be pooled.
 */
public class HuControl
{
    static final List<ByteBuffer> held = new ArrayList<>();
    static boolean injected;

    public static boolean flag(String n)
    {
        return new File(System.getProperty("stage4.flagdir", "."), n).exists();
    }

    static String state(BufferPool p)
    {
        return "size=" + p.sizeInBytes() + " used=" + p.usedSizeInBytes() + " ovf=" + p.overflowMemoryInBytes() + " thr=" + p.memoryUsageThreshold();
    }

    static void log(String s)
    {
        try (PrintWriter w = new PrintWriter(new FileWriter(new File(System.getProperty("stage4.flagdir", "."), "inject.log"), true)))
        {
            w.println("ms=" + System.currentTimeMillis() + " " + s);
        }
        catch (Exception e)
        {
            throw new RuntimeException(e);
        }
    }

    public static synchronized void inject()
    {
        if (injected)
            return;
        injected = true;
        BufferPool p = BufferPools.forChunkCache();
        String before = state(p);
        for (int i = 0; i < 400; i++)
            held.add(p.get(64 * 1024, BufferType.OFF_HEAP));
        log("injected 400x65536 before: " + before + " after: " + state(p));
    }

    public static synchronized void release()
    {
        if (!injected || held.isEmpty())
            return;
        BufferPool p = BufferPools.forChunkCache();
        String before = state(p);
        for (ByteBuffer b : held)
            p.put(b);
        held.clear();
        log("released before: " + before + " after: " + state(p));
    }
}
