package stage4;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.util.HashMap;
import java.util.Map;

/**
 * Helper for batch-alloc.btm (batch_size_fail_threshold, case 9d as amended by R7): bytes the calling thread allocated
 * between start(tag) and end(tag, extra), one line per outermost start/end pair. Observation only. A nested start of the
 * same tag on the same thread (a bridge method, a re-entry) only counts depth, so a pair is measured once.
 * Lines go to the file named by -Dstage4.byteman.out, flushed per line:
 *   <tag> thread=<name> bytes=<allocated> ms=<epoch ms> <extra>
 *   <tag> thread=<name> ms=<epoch ms> <extra>          (line(), no measurement)
 * Compiled into a jar on the boot class path (the node runs from build/apache-cassandra-*.jar).
 */
public final class Alloc
{
    private static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    private static final ThreadLocal<Map<String, long[]>> OPEN = ThreadLocal.withInitial(HashMap::new);
    private static PrintWriter out;

    private static long now() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    public static void start(String tag)
    {
        long[] s = OPEN.get().get(tag);
        if (s != null) { s[1]++; return; }
        OPEN.get().put(tag, new long[]{ now(), 1 });
    }

    public static void end(String tag, String extra)
    {
        long n = now();
        long[] s = OPEN.get().get(tag);
        if (s == null) { write(tag + " thread=" + Thread.currentThread().getName() + " bytes=-1 ms=" + System.currentTimeMillis() + " " + extra); return; }
        if (--s[1] > 0) return;
        OPEN.get().remove(tag);
        write(tag + " thread=" + Thread.currentThread().getName() + " bytes=" + (n - s[0]) + " ms=" + System.currentTimeMillis() + " " + extra);
    }

    public static void line(String tag, String extra)
    {
        write(tag + " thread=" + Thread.currentThread().getName() + " ms=" + System.currentTimeMillis() + " " + extra);
    }

    private static synchronized void write(String s)
    {
        try
        {
            if (out == null)
                out = new PrintWriter(new FileWriter(System.getProperty("stage4.byteman.out", "batch-alloc.trace"), true));
            out.println(s);
            out.flush();
        }
        catch (IOException e)
        {
            System.err.println("stage4.Alloc: " + e);
        }
    }
}
