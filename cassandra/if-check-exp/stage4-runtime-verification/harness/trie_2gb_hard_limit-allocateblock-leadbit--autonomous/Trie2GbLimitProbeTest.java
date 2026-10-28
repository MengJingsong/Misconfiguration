package org.apache.cassandra.db.tries;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.util.List;

import org.junit.Test;

import org.apache.cassandra.io.compress.BufferType;
import org.apache.cassandra.utils.bytecomparable.ByteComparable;

/**
 * Stage-4 unit-tier probe for trie_2gb_hard_limit-allocateblock-leadbit--autonomous (case B2c-B2e).
 * One JVM per run. System properties: probe.type = OFF_HEAP | ON_HEAP, probe.out = output file (one line per reading,
 * "key=value" pairs), probe.nmt = true to call "jcmd <self> VM.native_memory summary" at each reading.
 * The knob -Dcassandra.memtable.row_overhead_size is read by InMemoryTrie's static initializer; this class touches
 * InMemoryTrie only inside try/catch so an invalid value (0, 2048) is recorded, not fatal.
 */
public class Trie2GbLimitProbeTest
{
    static PrintWriter out;
    static boolean nmt;

    static void log(String s)
    {
        out.println(s);
        out.flush();
        System.out.println("PROBE " + s);
    }

    static String nmtSummary()
    {
        try
        {
            long pid = ProcessHandle.current().pid();
            Process p = new ProcessBuilder("jcmd", Long.toString(pid), "VM.native_memory", "summary").redirectErrorStream(true).start();
            String all = new String(p.getInputStream().readAllBytes());
            p.waitFor();
            // keep the total line and the "Other" (direct buffers) line committed values
            StringBuilder sb = new StringBuilder();
            for (String l : all.split("\n"))
                if (l.startsWith("Total:") || l.contains("Other (reserved") || l.contains("- Java Heap"))
                    sb.append(l.trim().replaceAll("\\s+", " ")).append(" ; ");
            return sb.toString();
        }
        catch (Throwable t)
        {
            return "NMT-ERR " + t;
        }
    }

    static long allocatedPos(InMemoryTrie<String> trie)
    {
        try
        {
            Field f = InMemoryTrie.class.getDeclaredField("allocatedPos");
            f.setAccessible(true);
            return f.getInt(trie);
        }
        catch (Throwable t)
        {
            return -1;
        }
    }

    static String mem(InMemoryTrie<String> trie, String tag)
    {
        long direct = 0, count = 0;
        List<BufferPoolMXBean> pools = ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class);
        for (BufferPoolMXBean b : pools)
            if (b.getName().equals("direct")) { direct = b.getMemoryUsed(); count = b.getCount(); }
        long heap = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
        String s = "tag=" + tag + " allocatedPos=" + allocatedPos(trie) + " sizeOffHeap=" + trie.sizeOffHeap() + " sizeOnHeap=" + trie.sizeOnHeap()
                   + " reached=" + trie.reachedAllocatedSizeThreshold()
                   + " directUsed=" + direct + " directCount=" + count + " heapUsed=" + heap;
        if (nmt)
            s += " nmt=[" + nmtSummary() + "]";
        return s;
    }

    static String adv(InMemoryTrie<String> trie, String tag, int target)
    {
        try
        {
            int r = trie.advanceAllocatedPos(target);
            return "op=" + tag + " target=" + target + " result=OK returned=" + r;
        }
        catch (InMemoryTrie.SpaceExhaustedException e)
        {
            return "op=" + tag + " target=" + target + " result=SpaceExhaustedException msg=\"" + e.getMessage() + "\"";
        }
    }

    @Test
    public void probe() throws Exception
    {
        out = new PrintWriter(new FileWriter(System.getProperty("probe.out", "probe.out"), true));
        nmt = Boolean.getBoolean("probe.nmt");
        BufferType type = BufferType.valueOf(System.getProperty("probe.type", "OFF_HEAP"));
        log("RUN type=" + type + " knob=" + System.getProperty("cassandra.memtable.row_overhead_size", "<unset>")
            + " maxMemory=" + Runtime.getRuntime().maxMemory());
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
            return;
        }
        log("THRESHOLD ALLOCATED_SIZE_THRESHOLD=" + thr + " (" + (thr >> 20) + " MiB) hardLimit=" + ((1L << 31) - 256));

        // phase 1: advance in steps, bracketing the soft threshold; then the edge
        InMemoryTrie<String> trie = new InMemoryTrie<>(type);
        log(mem(trie, "start"));
        String t1 = "test1", t2 = "testing2", t3 = "onemoretest3";
        trie.putRecursive(ByteComparable.of(t1), t1, (x, y) -> y);
        log(mem(trie, "after-put-t1"));
        int[] targets = { thr - 0x1000, thr, thr + 0x1000, 0x7FFFFEE0 };
        String[] names = { "thr-0x1000", "thr", "thr+0x1000", "edge-0x7FFFFEE0" };
        for (int i = 0; i < targets.length; i++)
        {
            log(adv(trie, names[i], targets[i]));
            log(mem(trie, "after-" + names[i]));
        }
        log("CHECK read-t1=" + trie.get(ByteComparable.of(t1)) + " read-t3=" + trie.get(ByteComparable.of(t3)));
        // a real put near the edge
        long before = allocatedPos(trie);
        String res;
        try
        {
            trie.putRecursive(ByteComparable.of(t3), t3, (x, y) -> y);
            res = "OK";
        }
        catch (InMemoryTrie.SpaceExhaustedException e)
        {
            res = "SpaceExhaustedException";
        }
        log("op=putRecursive-t3 result=" + res + " posBefore=" + before + " posAfter=" + allocatedPos(trie));
        log(mem(trie, "after-put-t3"));
        log("CHECK read-t1=" + trie.get(ByteComparable.of(t1)) + " read-t2=" + trie.get(ByteComparable.of(t2)) + " read-t3=" + trie.get(ByteComparable.of(t3)));
        for (int k = 0; k < 2; k++)
        {
            before = allocatedPos(trie);
            log(adv(trie, "advance-MAX_VALUE-try" + (k + 1), Integer.MAX_VALUE) + " posBefore=" + before + " posAfter=" + allocatedPos(trie));
            log(mem(trie, "after-advance-MAX-try" + (k + 1)));
        }
        log("CHECK read-t1=" + trie.get(ByteComparable.of(t1)) + " final-allocatedPos=" + allocatedPos(trie));
        trie = null;

        // phase 2: fresh trie, edge then straight to MAX_VALUE (no put in between)
        System.gc();
        InMemoryTrie<String> trie2 = new InMemoryTrie<>(type);
        log(adv(trie2, "B-advance-edge", 0x7FFFFEE0) + " pos=" + allocatedPos(trie2));
        before = allocatedPos(trie2);
        log(adv(trie2, "B-advance-MAX", Integer.MAX_VALUE) + " posBefore=" + before + " posAfter=" + allocatedPos(trie2));
        log(mem(trie2, "B-after-MAX"));
        log("DONE");
        out.close();
    }
}
