package stage4;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;

/**
 * Helper for ec.btm (cluster tier B3d, amendment of 2026-10-26): per call of ByteSourceInverse.readBytes(ByteSource,int), the bytes
 * the calling thread allocated between entry and exit, the result length and the first caller outside ByteSourceInverse.
 * Observation only. Lines go to the file named by -Dstage4.byteman.out, flushed per line:
 *   rb thread=<name> bytes=<allocated by the whole call, the source's own allocation included> len=<result length> caller=<Class.method:line> ms=<epoch ms>
 *   rbexc thread=<name> bytes=<allocated> caller=<..> ms=<..>      (the call threw)
 * A rule on ensureCapacity itself was tried in the shakedown and dropped: Byteman's per-trigger allocation inside the per-byte call dwarfed
 * the buffer (9 MB per call, 94 percent of JFR weight); the ensureCapacity part is therefore taken from the mirror of the doubling code.
 * Calls are not nested (readBytes(ByteSource) calls the two-argument form, which is the only traced method). Compiled into a jar on
 * the boot class path (the node runs from build/apache-cassandra-*.jar).
 */
public final class Ec
{
    private static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    private static final ThreadLocal<long[]> OPEN = ThreadLocal.withInitial(() -> new long[]{ -1 });
    private static PrintWriter out;

    public static void start()
    {
        long[] o = OPEN.get();
        o[0] = TMX.getThreadAllocatedBytes(Thread.currentThread().getId());
    }

    public static void end(int len, boolean threw)
    {
        long n = TMX.getThreadAllocatedBytes(Thread.currentThread().getId());
        long[] o = OPEN.get();
        long s = o[0];
        String caller = "?";
        boolean seen = false;
        for (StackTraceElement e : new Throwable().getStackTrace())
        {
            boolean inv = e.getClassName().endsWith("ByteSourceInverse");
            if (inv) { seen = true; continue; }
            if (!seen) continue;     // the helper, Byteman and reflection frames above readBytes
            String c = e.getClassName();
            caller = c.substring(c.lastIndexOf('.') + 1) + "." + e.getMethodName() + ":" + e.getLineNumber();
            break;
        }
        write((threw ? "rbexc" : "rb") + " thread=" + Thread.currentThread().getName() + " bytes=" + (s < 0 ? -1 : n - s)
              + (threw ? "" : " len=" + len) + " caller=" + caller + " ms=" + System.currentTimeMillis());
    }

    private static synchronized void write(String s)
    {
        try
        {
            if (out == null)
                out = new PrintWriter(new FileWriter(System.getProperty("stage4.byteman.out", "ec.trace"), true));
            out.println(s);
            out.flush();
        }
        catch (IOException e)
        {
            System.err.println("stage4.Ec: " + e);
        }
    }
}
