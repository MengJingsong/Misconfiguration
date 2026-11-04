package stage4;

/**
 * Stage-4 harness counter for the none-type cases (RandomAccessReaderAdapter lines 72/120, ChecksummedDataInput.checkLimit entry,
 * UDFDataType line 180). Called from a Byteman rule action; a plain static increment (no allocation), single-threaded use.
 * Not upstream; compiled by the unit-run.sh into a separate directory.
 */
public final class Count
{
    public static long hits;

    public static void hit() { hits++; }

    public static long get() { return hits; }
}
