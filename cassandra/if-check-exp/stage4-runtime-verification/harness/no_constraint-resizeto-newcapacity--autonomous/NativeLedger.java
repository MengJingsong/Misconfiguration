package org.apache.cassandra.io.util;

/**
 * Stage-4 ledger of native (Unsafe) allocations made through Memory(long), fed by Byteman rules (rules.btm).
 * reset(live0) sets the live bytes already held before the measured call; read() returns
 * {copies, allocs, allocBytes, frees, freeBytes, peakLive, liveAfter}. Single-threaded use.
 */
public final class NativeLedger
{
    static long copies, allocs, allocBytes, frees, freeBytes, live, peak;

    public static void reset(long live0)
    {
        copies = 0; allocs = 0; allocBytes = 0; frees = 0; freeBytes = 0; live = live0; peak = live0;
    }

    public static void alloc(long bytes)
    {
        allocs++; allocBytes += bytes; live += bytes;
        if (live > peak) peak = live;
    }

    public static void free(long bytes)
    {
        frees++; freeBytes += bytes; live -= bytes;
    }

    public static void copy() { copies++; }

    public static long[] read()
    {
        return new long[]{ copies, allocs, allocBytes, frees, freeBytes, peak, live };
    }
}
