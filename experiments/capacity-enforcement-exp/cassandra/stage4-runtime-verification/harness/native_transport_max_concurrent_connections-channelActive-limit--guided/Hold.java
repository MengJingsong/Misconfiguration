/*
 * Stage-4 harness helper for native_transport_max_concurrent_connections-channelActive-limit--guided (cluster tier,
 * positive control, 9f R2). Compiled into a jar on the node's boot class path (-Xbootclasspath/a:), called by the
 * "ncc hold request" rule of ncc.btm: waits while <file> exists, for at most <maxMs> ms, and returns the ms waited.
 * Holding a decoded request inside Dispatcher.processRequest keeps its in-flight capacity acquired, as a slow query would.
 */
package stage4;

public final class Hold
{
    public static long await(String file, long maxMs) throws InterruptedException
    {
        long t0 = System.currentTimeMillis();
        java.io.File f = new java.io.File(file);
        while (f.exists() && System.currentTimeMillis() - t0 < maxMs)
            Thread.sleep(50);
        return System.currentTimeMillis() - t0;
    }
}
