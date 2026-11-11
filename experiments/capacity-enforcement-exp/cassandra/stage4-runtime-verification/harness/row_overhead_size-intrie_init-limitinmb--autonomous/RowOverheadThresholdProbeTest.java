package org.apache.cassandra.db.tries;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.util.SplittableRandom;

import org.junit.Test;

import org.apache.cassandra.io.compress.BufferType;
import org.apache.cassandra.utils.bytecomparable.ByteComparable;

/**
 * Stage-4 unit-tier probe for row_overhead_size-intrie_init-limitinmb--autonomous (case B2). One JVM per run, run through the plain
 * java launcher + JUnitCore. System properties: probe.type = OFF_HEAP | ON_HEAP, probe.out = output file, probe.fill = true to
 * write random 16-byte keys until reachedAllocatedSizeThreshold() flips and then 10 percent more keys (false: read the threshold only),
 * probe.skiplist = true to also load SkipListMemtable and print its ROW_OVERHEAD_HEAP_SIZE (the same property read as bytes).
 * The knob -Dcassandra.memtable.row_overhead_size is read by InMemoryTrie's static initializer; this class touches InMemoryTrie
 * only inside try/catch so an invalid value is recorded (root cause class and message), not fatal.
 */
public class RowOverheadThresholdProbeTest
{
    static PrintWriter out;

    static void log(String s)
    {
        out.println(s);
        out.flush();
        System.out.println("PROBE " + s);
    }

    static long allocatedPos(InMemoryTrie<String> trie) throws Exception
    {
        Field f = InMemoryTrie.class.getDeclaredField("allocatedPos");
        f.setAccessible(true);
        return f.getInt(trie);
    }

    static long direct()
    {
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct")) return b.getMemoryUsed();
        return -1;
    }

    static String state(InMemoryTrie<String> t, long keys, String tag) throws Exception
    {
        return "tag=" + tag + " keys=" + keys + " allocatedPos=" + allocatedPos(t) + " reached=" + t.reachedAllocatedSizeThreshold()
               + " sizeOffHeap=" + t.sizeOffHeap() + " sizeOnHeap=" + t.sizeOnHeap()
               + " directUsed=" + direct() + " heapUsed=" + ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    @Test
    public void probe() throws Exception
    {
        out = new PrintWriter(new FileWriter(System.getProperty("probe.out", "probe.out"), true));
        // SkipListMemtable's static initialiser estimates the row overhead through a throw-away memtable, which needs the config loaded
        org.apache.cassandra.config.DatabaseDescriptor.daemonInitialization();
        BufferType type = BufferType.valueOf(System.getProperty("probe.type", "OFF_HEAP"));
        log("RUN type=" + type + " knob=" + System.getProperty("cassandra.memtable.row_overhead_size", "<unset>")
            + " trie_size_limit_mb=" + System.getProperty("cassandra.trie_size_limit_mb", "<unset>") + " maxMemory=" + Runtime.getRuntime().maxMemory());
        int thr;
        try
        {
            Field f = InMemoryTrie.class.getDeclaredField("ALLOCATED_SIZE_THRESHOLD");
            f.setAccessible(true);
            thr = f.getInt(null);
        }
        catch (Throwable t)
        {
            Throwable c = t;
            while (c.getCause() != null) c = c.getCause();
            log("CLINIT_FAIL outer=" + t.getClass().getName() + " root=" + c.getClass().getName() + " msg=\"" + c.getMessage() + "\"");
            if (Boolean.getBoolean("probe.skiplist"))
                skiplist();
            out.close();
            return;
        }
        log("THRESHOLD ALLOCATED_SIZE_THRESHOLD=" + thr + " (" + (thr / 1048576.0) + " MiB)");
        if (Boolean.getBoolean("probe.skiplist"))
            skiplist();
        if (Boolean.parseBoolean(System.getProperty("probe.fill", "true")))
        {
            InMemoryTrie<String> trie = new InMemoryTrie<>(type);
            log(state(trie, 0, "start"));
            SplittableRandom r = new SplittableRandom(42);
            byte[] k = new byte[16];
            long keys = 0;
            long flipKeys = -1;
            long limit = Long.MAX_VALUE;
            long lastReport = 0;
            while (keys < limit)
            {
                long a = r.nextLong(), b = r.nextLong();
                for (int i = 0; i < 8; i++) { k[i] = (byte) (a >>> (8 * i)); k[8 + i] = (byte) (b >>> (8 * i)); }
                try
                {
                    trie.putRecursive(ByteComparable.fixedLength(k.clone()), "v", (x, y) -> y);
                }
                catch (InMemoryTrie.SpaceExhaustedException e)
                {
                    log("EXHAUSTED " + state(trie, keys, "exhausted") + " threshold=" + thr + " keysAtFlip=" + flipKeys + " keysAfterFlip=" + (flipKeys < 0 ? -1 : keys - flipKeys));
                    out.close();
                    return;
                }
                keys++;
                if (flipKeys < 0 && trie.reachedAllocatedSizeThreshold())
                {
                    flipKeys = keys;
                    limit = keys + keys / 10;
                    log("FLIP " + state(trie, keys, "flip") + " threshold=" + thr);
                }
                else if (flipKeys < 0 && keys - lastReport >= 2_000_000)
                {
                    lastReport = keys;
                    log(state(trie, keys, "progress"));
                }
            }
            long pos = allocatedPos(trie);
            log("END10 " + state(trie, keys, "after+10pct") + " threshold=" + thr + " ratioToThreshold=" + (pos / (double) thr) + " keysAtFlip=" + flipKeys);
        }
        out.close();
    }

    static void skiplist() throws Exception
    {
        try
        {
            Class<?> c = Class.forName("org.apache.cassandra.db.memtable.SkipListMemtable");
            Field f = c.getDeclaredField("ROW_OVERHEAD_HEAP_SIZE");
            f.setAccessible(true);
            log("SKIPLIST ROW_OVERHEAD_HEAP_SIZE=" + f.getInt(null));
        }
        catch (Throwable t)
        {
            Throwable c = t;
            while (c.getCause() != null) c = c.getCause();
            log("SKIPLIST_FAIL root=" + c.getClass().getName() + " msg=\"" + c.getMessage() + "\"");
        }
    }
}
