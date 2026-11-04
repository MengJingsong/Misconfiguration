package stage4;

/**
 * Helper for hold-trees.btm (repair_session_space-split-maxsize). Compiled into a jar on the boot class path by
 * cluster-run.py, because the node runs from build/apache-cassandra-*.jar. Byteman 4.0.20 cannot parse a `new`
 * expression in a rule condition, hence a static method.
 */
public final class Rss
{
    private Rss() {}

    /** True while the flag file named by -Dstage4.holdflag exists. */
    public static boolean holding()
    {
        String f = System.getProperty("stage4.holdflag");
        return f != null && new java.io.File(f).exists();
    }

    /** Sleeps the calling thread; an interrupt ends the sleep early. */
    public static void sleep(long ms)
    {
        try
        {
            Thread.sleep(ms);
        }
        catch (InterruptedException e)
        {
            Thread.currentThread().interrupt();
        }
    }
}
