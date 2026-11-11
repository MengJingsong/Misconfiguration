/*
 * Stage-4 harness: memtable_heap_space-LeafBuilder-allocated--autonomous, unit tier (B2 as amended U2, 2026-10-27).
 * Not upstream code. Copied into test/unit/org/apache/cassandra/db/memtable/ by unit-run.sh.
 * Counters incremented by the observe-only Byteman rules in unit-counters.btm, which fire AT LINE 2683
 * (BTree$LeafBuilder.redistributeAndDrain) and AT LINE 2736 (BTree$LeafBuilder.propagateOverflow), i.e. only when the
 * target check `if (allocated >= 0)` passed. Only events on the thread registered with start() are counted, so the counts
 * belong to the writes of the test thread (CQLTester executes mutations on the calling thread).
 */
package org.apache.cassandra.db.memtable;

import java.util.concurrent.atomic.AtomicLong;

public final class WideLeafCounters
{
    private static volatile Thread thread;
    private static final AtomicLong c2683 = new AtomicLong();
    private static final AtomicLong c2736 = new AtomicLong();

    public static boolean on(Thread t)
    {
        return t == thread;
    }

    public static void inc2683()
    {
        c2683.incrementAndGet();
    }

    public static void inc2736()
    {
        c2736.incrementAndGet();
    }

    public static void start(Thread t)
    {
        c2683.set(0);
        c2736.set(0);
        thread = t;
    }

    public static void stop()
    {
        thread = null;
    }

    public static long n2683()
    {
        return c2683.get();
    }

    public static long n2736()
    {
        return c2736.get();
    }
}
