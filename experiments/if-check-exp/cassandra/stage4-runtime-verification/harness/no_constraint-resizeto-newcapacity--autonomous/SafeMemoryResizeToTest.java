package org.apache.cassandra.io.util;

import java.io.PrintWriter;
import java.lang.management.ManagementFactory;

import org.junit.Test;

/**
 * Stage-4 unit tier for no_constraint-resizeto-newcapacity--autonomous (case file B2 amendment 2026-10-29).
 * Properties: stage4.out (dir), stage4.mode (sweep|control), stage4.c (bytes, sweep), stage4.reps (default 5).
 * Writes raw rows to <out>/raw.csv; asserts nothing (analyze.py judges the rows against the frozen prediction).
 * Needs the Byteman agent with rules.btm (NativeLedger is fed by it).
 */
public class SafeMemoryResizeToTest
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static PrintWriter raw;

    static byte pat(long i) { return (byte) (i % 251); }

    static void fill(SafeMemoryWriter w, long n) throws Exception
    {
        int chunk = (int) Math.min(n, 1 << 20);
        byte[] b = new byte[chunk];
        long o = 0;
        while (o < n)
        {
            int len = (int) Math.min(chunk, n - o);
            for (int j = 0; j < len; j++) b[j] = pat(o + j);
            w.write(b, 0, len);
            o += len;
        }
    }

    static boolean readBack(SafeMemory m, long len)
    {
        if (len <= 0) return true;
        long[] at = { 0, len / 2, len - 1 };
        for (long p : at)
            if (m.getByte(p) != pat(p)) return false;
        return true;
    }

    interface Op { void run(SafeMemoryWriter w) throws Exception; }

    /** one measured arm: fills fillBytes into a writer of capacity c, resets the ledger with live = c, measures op. */
    static void arm(String mode, long c, String name, int rep, long fillBytes, Op op) throws Exception
    {
        SafeMemoryWriter w = new SafeMemoryWriter(c);
        fill(w, fillBytes);
        long capBefore = w.capacity(), lenBefore = w.length();
        long tid = Thread.currentThread().getId();
        NativeLedger.reset(capBefore);
        long a0 = TMX.getThreadAllocatedBytes(tid);
        op.run(w);
        long a1 = TMX.getThreadAllocatedBytes(tid);
        long[] r = NativeLedger.read();
        long capAfter = w.capacity(), lenAfter = w.length();
        boolean ok = readBack(w.currentBuffer(), Math.min(lenAfter, capBefore));
        // columns: mode,c,arm,rep,capBefore,lenBefore,copies,allocs,allocBytes,frees,freeBytes,peak,liveAfter,capAfter,lenAfter,heapBytes,readback
        raw.println(mode + "," + c + "," + name + "," + rep + "," + capBefore + "," + lenBefore + ","
                    + r[0] + "," + r[1] + "," + r[2] + "," + r[3] + "," + r[4] + "," + r[5] + "," + r[6] + ","
                    + capAfter + "," + lenAfter + "," + (a1 - a0) + "," + (ok ? 1 : 0));
        raw.flush();
        w.close();
    }

    @Test
    public void run() throws Exception
    {
        String out = System.getProperty("stage4.out");
        String mode = System.getProperty("stage4.mode", "sweep");
        int reps = Integer.getInteger("stage4.reps", 5);
        raw = new PrintWriter(new java.io.FileWriter(out + "/raw.csv", true));
        raw.println("# header mode,c,arm,rep,capBefore,lenBefore,copies,allocs,allocBytes,frees,freeBytes,peak,liveAfter,capAfter,lenAfter,heapBytes,readback"
                    + " # dob=" + System.getProperty("cassandra.DOB_DOUBLING_THRESHOLD_MB") + " mode=" + mode);
        if (mode.equals("control"))
        {
            long c = 8L << 20;
            for (int rep = 0; rep <= reps; rep++)
                arm("control", c, "grow1", rep, c, w -> w.writeByte(1));
        }
        else
        {
            long c = Long.getLong("stage4.c");
            for (int rep = 0; rep <= reps; rep++)   // rep 0 = warm-up, discarded by the analysis
            {
                arm("sweep", c, "E", rep, c, w -> w.trim());
                arm("sweep", c, "D", rep, c - 1, w -> w.trim());
                arm("sweep", c, "H", rep, c / 2, w -> w.trim());
                arm("sweep", c, "X", rep, c, w -> { SafeMemory cp = w.currentBuffer().copy(c); cp.close(); });
            }
        }
        raw.close();
    }
}
