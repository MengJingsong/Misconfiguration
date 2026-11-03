package stage4;

import java.lang.management.ManagementFactory;

/** Helper for read-alloc.btm: bytes allocated by the calling thread between start() and end(). Observation only. */
public final class Alloc
{
    private static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    private static final ThreadLocal<Long> START = new ThreadLocal<>();

    private static long now() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    public static void start() { START.set(now()); }

    public static String end()
    {
        Long s = START.get();
        START.remove();
        return "read-alloc thread=" + Thread.currentThread().getName() + " bytes=" + (s == null ? -1 : now() - s) + " ms=" + System.currentTimeMillis();
    }
}
