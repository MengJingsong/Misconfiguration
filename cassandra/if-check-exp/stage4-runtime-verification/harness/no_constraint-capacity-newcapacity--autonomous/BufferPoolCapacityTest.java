package org.apache.cassandra.net;

import java.io.PrintWriter;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

import org.junit.BeforeClass;
import org.junit.Test;

import io.netty.buffer.ByteBuf;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.utils.memory.BufferPools;

/**
 * Stage-4 unit tier for no_constraint-capacity-newcapacity--autonomous (case file B2 amendment 2026-10-29).
 * Properties: stage4.out (dir), stage4.mode (sweep|control), stage4.c (requested bytes), stage4.cache (networking_cache_size MiB, default 128),
 * stage4.reps (default 5). Writes raw rows to <out>/raw.csv; asserts nothing. Needs the Byteman agent with rules.btm.
 */
public class BufferPoolCapacityTest
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static PrintWriter raw;

    @BeforeClass
    public static void beforeClass()
    {
        DatabaseDescriptor.clientInitialization();
        DatabaseDescriptor.getRawConfig().networking_cache_size = new DataStorageSpec.IntMebibytesBound(Integer.getInteger("stage4.cache", 128));
    }

    static long used() { return GlobalBufferPoolAllocator.instance.usedSizeInBytes(); }
    static long ovf() { return GlobalBufferPoolAllocator.instance.overflowMemoryInBytes(); }
    static long pooled() { return BufferPools.forNetworking().sizeInBytes() - ovf(); }

    static long direct()
    {
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct")) return b.getMemoryUsed();
        return -1;
    }

    /** gc until the direct gauge has been stable for 5 polls of 100 ms (at most 5 s). */
    static long settle() throws Exception
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
        return last;
    }

    static void arm(String mode, long c, String name, int rep, boolean doGc) throws Exception
    {
        int max = (int) (4 * c + 8192);
        if (doGc) settle();
        ByteBuf buf = GlobalBufferPoolAllocator.instance.buffer((int) c, max);
        int cap0 = buf.capacity();
        int target = name.equals("E") ? cap0 : name.equals("G") ? cap0 + 1 : name.equals("S") ? cap0 / 2 : name.equals("M") ? max + 1 : -1;
        long usedAlloc = used(), ovfAlloc = ovf(), poolAlloc = pooled();
        long u0 = used(), o0 = ovf(), d0 = direct();
        NetProbe.reset();
        String exc = "-";
        long tid = Thread.currentThread().getId();
        long a0 = TMX.getThreadAllocatedBytes(tid);
        try { buf.capacity(target); } catch (Throwable t) { exc = t.getClass().getSimpleName(); }
        long a1 = TMX.getThreadAllocatedBytes(tid);
        int capNew = buf.capacity();
        long u1 = used(), o1 = ovf(), d1 = direct(), p1 = pooled();
        long sc = NetProbe.sc, u128 = NetProbe.used128, o128 = NetProbe.ovf128;
        long d2 = doGc ? settle() : -1;
        buf.release();
        long u2 = used(), o2 = ovf();
        // columns: mode,c,arm,rep,cap0,target,usedAlloc,ovfAlloc,poolAlloc,u0,o0,d0,sc,u128,o128,capNew,u1,o1,d1,p1,d2,u2,o2,heapBytes,exc
        raw.println(mode + "," + c + "," + name + "," + rep + "," + cap0 + "," + target + "," + usedAlloc + "," + ovfAlloc + "," + poolAlloc + ","
                    + u0 + "," + o0 + "," + d0 + "," + sc + "," + u128 + "," + o128 + "," + capNew + "," + u1 + "," + o1 + "," + d1 + "," + p1 + ","
                    + d2 + "," + u2 + "," + o2 + "," + (a1 - a0) + "," + exc);
        raw.flush();
    }

    @Test
    public void run() throws Exception
    {
        String out = System.getProperty("stage4.out");
        String mode = System.getProperty("stage4.mode", "sweep");
        int reps = Integer.getInteger("stage4.reps", 5);
        long c = Long.getLong("stage4.c");
        raw = new PrintWriter(new java.io.FileWriter(out + "/raw.csv", true));
        raw.println("# header mode,c,arm,rep,cap0,target,usedAlloc,ovfAlloc,poolAlloc,u0,o0,d0,sc,u128,o128,capNew,u1,o1,d1,p1,d2,u2,o2,heapBytes,exc"
                    + " # cache=" + System.getProperty("stage4.cache", "128") + " mode=" + mode);
        boolean doGc = c >= (1 << 20);
        if (mode.equals("control"))
        {
            for (int rep = 0; rep <= reps; rep++)
                arm("control", c, "E", rep, false);
        }
        else
        {
            for (int rep = 0; rep <= reps; rep++)   // rep 0 = warm-up, discarded by the analysis
                for (String a : new String[]{ "E", "G", "S", "M" })
                    arm("sweep", c, a, rep, doGc);
        }
        raw.close();
    }
}
