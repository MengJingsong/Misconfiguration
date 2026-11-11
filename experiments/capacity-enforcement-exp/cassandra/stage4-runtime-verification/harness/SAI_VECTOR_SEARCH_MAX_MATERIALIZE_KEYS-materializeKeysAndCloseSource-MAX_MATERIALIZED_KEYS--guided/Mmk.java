package stage4;

/**
 * Helper for hold.btm (SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS), as Rss.java of
 * the repair_session_space harness: Byteman 4.0.20 cannot parse a `new` expression in a rule condition. cluster-run.py compiles it
 * into a jar on the boot class path.
 */
public final class Mmk
{
    private Mmk() {}

    /** True while the flag file /tmp/mmk-hold-<point> exists. */
    public static boolean holding(String point)
    {
        return new java.io.File("/tmp/mmk-hold-" + point).exists();
    }
}
