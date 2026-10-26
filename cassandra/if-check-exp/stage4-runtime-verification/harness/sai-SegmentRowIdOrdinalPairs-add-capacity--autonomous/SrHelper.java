package stage4;

import java.io.FileWriter;
import java.lang.management.ManagementFactory;

/** Byteman helper (boot class path). enter() at the constructor of SegmentRowIdOrdinalPairs records the calling thread's allocated bytes;
 *  exit() writes one line: "SR ts=<epoch ms> thr=<thread> cap=<ctor arg> arrlen=<array.length> alloc_ctor=<bytes the thread allocated in the constructor> caller=<frame>". */
public class SrHelper
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static final ThreadLocal<long[]> START = ThreadLocal.withInitial(() -> new long[1]);
    static final String OUT = System.getProperty("stage4.sr.out", "/tmp/sr-trace.out");

    public static boolean enter()
    {
        START.get()[0] = TMX.getThreadAllocatedBytes(Thread.currentThread().getId());
        return true;
    }

    public static synchronized boolean exit(int cap, int arrlen)
    {
        long used = TMX.getThreadAllocatedBytes(Thread.currentThread().getId()) - START.get()[0];
        String caller = "?";
        for (StackTraceElement e : new Throwable().getStackTrace())
        {
            String c = e.getClassName();
            if (c.startsWith("org.jboss.byteman") || c.startsWith("stage4.") || c.endsWith("SegmentRowIdOrdinalPairs") || c.contains("reflect") || c.contains("GeneratedMethodAccessor")) continue;
            caller = c.substring(c.lastIndexOf('.') + 1) + "." + e.getMethodName() + ":" + e.getLineNumber();
            break;
        }
        try (FileWriter w = new FileWriter(OUT, true))
        {
            w.write("SR ts=" + System.currentTimeMillis() + " thr=" + Thread.currentThread().getName().replace(' ', '_') + " cap=" + cap
                    + " arrlen=" + arrlen + " alloc_ctor=" + used + " caller=" + caller + "\n");
        }
        catch (Exception ex) { /* never disturb the node */ }
        return true;
    }
}
