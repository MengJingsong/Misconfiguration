package org.apache.cassandra.db.tries;

import java.io.PrintWriter;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;

import org.junit.Test;

import org.apache.cassandra.io.compress.BufferType;

/**
 * Stage-4 unit tier for no_constraint-allocateblock-inchunkpointer--autonomous (case file B2 amendment 2026-10-29).
 * Properties: stage4.out (dir), stage4.mode (sweep|control), stage4.reps (default 5). Raw rows to <out>/raw.csv; asserts nothing.
 */
public class InMemoryTrieAllocBlockTest
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static PrintWriter raw;
    static Field POS;
    static long R;

    static int pos(InMemoryTrie<?> t) throws Exception { return POS.getInt(t); }

    static long retained(InMemoryTrie<?> t)
    {
        long s = 0;
        for (int j = 0; j < t.buffers.length; j++)
            if (t.buffers[j] != null) s += t.buffers[j].capacity();
        return s;
    }

    static long direct()
    {
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct")) return b.getMemoryUsed();
        return -1;
    }

    static void settle() throws Exception
    {
        long last = -2; int stable = 0;
        for (int i = 0; i < 50 && stable < 5; i++)
        {
            System.gc();
            Thread.sleep(100);
            long d = direct();
            stable = (d == last) ? stable + 1 : 0;
            last = d;
        }
    }

    // columns: mode,type,i,rep,call,N,S,pos0,pos1,soh0,soh1,ret0,ret1,bufNullBefore,bufCapAfter,d0,d1,heapBytes,exc,R
    static void call(String mode, BufferType type, int i, int rep, String name, InMemoryTrie<String> t, int target, boolean idx) throws Exception
    {
        long N = 256L << i, S = 256L * ((1L << i) - 1);
        int pos0 = pos(t); long soh0 = t.sizeOnHeap(), ret0 = retained(t);
        int nullBefore = (idx && t.buffers[i] == null) ? 1 : 0;
        long d0 = direct();
        long tid = Thread.currentThread().getId();
        String exc = "-";
        long a0 = TMX.getThreadAllocatedBytes(tid);
        try { t.advanceAllocatedPos(target); } catch (InMemoryTrie.SpaceExhaustedException e) { exc = "SpaceExhaustedException"; }
        long a1 = TMX.getThreadAllocatedBytes(tid);
        int pos1 = pos(t); long soh1 = t.sizeOnHeap(), ret1 = retained(t);
        long cap = (idx && i < t.buffers.length && t.buffers[i] != null) ? t.buffers[i].capacity() : -1;
        long d1 = direct();
        raw.println(mode + "," + type + "," + i + "," + rep + "," + name + "," + N + "," + S + "," + pos0 + "," + pos1 + "," + soh0 + "," + soh1 + ","
                    + ret0 + "," + ret1 + "," + nullBefore + "," + cap + "," + d0 + "," + d1 + "," + (a1 - a0) + "," + exc + "," + R);
        raw.flush();
    }

    static void arm(BufferType type, int i, int rep) throws Exception
    {
        long S = 256L * ((1L << i) - 1);
        if (type == BufferType.OFF_HEAP) settle();
        InMemoryTrie<String> t = new InMemoryTrie<>(type);
        t.advanceAllocatedPos((int) (S - 32));                        // setup, outside any window
        long tid = Thread.currentThread().getId();
        long f0 = TMX.getThreadAllocatedBytes(tid), f1 = TMX.getThreadAllocatedBytes(tid);   // instrument floor (empty window)
        raw.println("sweep," + type + "," + i + "," + rep + ",F," + (256L << i) + "," + S + ",0,0,0,0,0,0,0,0,0,0," + (f1 - f0) + ",-," + R);
        call("sweep", type, i, rep, "A", t, (int) S, true);          // one block at S-32 (mid-chunk, check false)
        call("sweep", type, i, rep, "B", t, (int) (S + 32), true);   // one block at S (chunk start, check true)
    }

    @Test
    public void run() throws Exception
    {
        POS = InMemoryTrie.class.getDeclaredField("allocatedPos"); POS.setAccessible(true);
        Field rf = InMemoryTrie.class.getDeclaredField("REFERENCE_ARRAY_ON_HEAP_SIZE"); rf.setAccessible(true);
        R = rf.getLong(null);
        String out = System.getProperty("stage4.out");
        String mode = System.getProperty("stage4.mode", "sweep");
        int reps = Integer.getInteger("stage4.reps", 5);
        raw = new PrintWriter(new java.io.FileWriter(out + "/raw.csv", true));
        raw.println("# header mode,type,i,rep,call,N,S,pos0,pos1,soh0,soh1,ret0,ret1,bufNullBefore,bufCapAfter,d0,d1,heapBytes,exc,R # mode=" + mode);
        if (mode.equals("control"))
        {
            int i = 22;
            long S = 256L * ((1L << i) - 1);
            InMemoryTrie<String> t = new InMemoryTrie<>(BufferType.ON_HEAP);
            t.advanceAllocatedPos((int) (S - 32));
            call("control", BufferType.ON_HEAP, i, 1, "A", t, (int) S, true);
            call("control", BufferType.ON_HEAP, i, 1, "B", t, (int) (S + 32), true);
            int s23 = 2147483392;                                   // S_23 = 2^31 - 256: the hard limit
            call("control", BufferType.ON_HEAP, 23, 1, "C1", t, s23, false);
            call("control", BufferType.ON_HEAP, 23, 1, "C2", t, s23 + 32, false);
        }
        else
        {
            for (int rep = 0; rep <= reps; rep++)   // rep 0 = warm-up, discarded
            {
                for (int i : new int[]{ 1, 3, 7, 11, 15, 19 }) arm(BufferType.ON_HEAP, i, rep);
                for (int i : new int[]{ 11, 15 }) arm(BufferType.OFF_HEAP, i, rep);
            }
        }
        raw.close();
    }
}
