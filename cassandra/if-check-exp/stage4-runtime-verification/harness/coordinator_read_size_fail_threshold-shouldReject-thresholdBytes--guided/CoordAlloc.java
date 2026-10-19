package stage4;

import java.lang.management.ManagementFactory;

/** Helper for coord-read.btm: bytes allocated by the calling thread inside SelectStatement.process(). Observation only.
 *  A copy of the sibling's Alloc.java with its own ThreadLocal and the prefix coord-alloc. Names JDK classes only. */
public final class CoordAlloc
{
    private static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    private static final ThreadLocal<Long> START = new ThreadLocal<>();

    private static long now() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    public static void start() { START.set(now()); }

    public static String end(String how)
    {
        Long s = START.get();
        START.remove();
        return "coord-alloc thread=" + Thread.currentThread().getName() + " bytes=" + (s == null ? -1 : now() - s) + " exit=" + how + " ms=" + System.currentTimeMillis();
    }
}
