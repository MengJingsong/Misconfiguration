package org.apache.cassandra.db.partitions;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.concurrent.atomic.LongAdder;

/**
 * Stage-4 counters for the EXCESS_WASTE_* cases (written 2026-10-28). Compiled into the patched copies of AtomicBTreePartition made
 * by mkvariant.sh; never part of the tag. attempt() is called at every compare-and-set of Updater.tryUpdateData, tracker() at every
 * entry of updateWastedAllocationTracker, flip() when a partition's tracker moves to TRACKER_PESSIMISTIC_LOCKING for the first time.
 * With -Dstage4.wastelog=<file> a daemon thread appends one CSV line per second.
 */
public final class S4Waste
{
    public static final LongAdder attempts = new LongAdder(), fails = new LongAdder(), failHeap = new LongAdder();
    public static final LongAdder lockedAttempts = new LongAdder(), lockedFails = new LongAdder(), lockedFailHeap = new LongAdder();
    public static final LongAdder trackerCalls = new LongAdder(), trackerBytes = new LongAdder(), flips = new LongAdder();

    static
    {
        String f = System.getProperty("stage4.wastelog");
        if (f != null)
        {
            Thread t = new Thread(() -> {
                try (PrintWriter w = new PrintWriter(new FileWriter(f, true)))
                {
                    Thread.sleep(200);
                    try
                    {
                        Class<?> k = Class.forName("org.apache.cassandra.db.partitions.AtomicBTreePartition");
                        java.lang.reflect.Field fc = k.getDeclaredField("EXCESS_WASTE_BYTES"), fo = k.getDeclaredField("EXCESS_WASTE_OFFSET");
                        fc.setAccessible(true);
                        fo.setAccessible(true);
                        w.println("# C=" + fc.getLong(null) + " OFFSET=" + fo.getInt(null));
                    }
                    catch (Throwable e) { w.println("# C=unreadable " + e); }
                    w.println("ms,attempts,fails,failHeap,lockedAttempts,lockedFails,lockedFailHeap,trackerCalls,trackerBytes,flips");
                    while (true)
                    {
                        w.println(line());
                        w.flush();
                        Thread.sleep(1000);
                    }
                }
                catch (Throwable e) { }
            }, "s4waste-reporter");
            t.setDaemon(true);
            t.start();
        }
    }

    public static String line()
    {
        return System.currentTimeMillis() + "," + attempts.sum() + "," + fails.sum() + "," + failHeap.sum() + "," + lockedAttempts.sum() + ","
               + lockedFails.sum() + "," + lockedFailHeap.sum() + "," + trackerCalls.sum() + "," + trackerBytes.sum() + "," + flips.sum();
    }

    public static void attempt(boolean ok, long heapSize, boolean locked)
    {
        attempts.increment();
        if (locked) lockedAttempts.increment();
        if (!ok)
        {
            fails.increment();
            failHeap.add(heapSize);
            if (locked) { lockedFails.increment(); lockedFailHeap.add(heapSize); }
        }
    }

    public static void tracker(long wastedBytes) { trackerCalls.increment(); trackerBytes.add(wastedBytes); }

    public static void flip() { flips.increment(); }
}
