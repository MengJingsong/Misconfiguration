package org.apache.cassandra.concurrent;

import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.apache.cassandra.config.DatabaseDescriptor;

// Stage 4 harness, maxTasksQueued-addTask-taskPermits--autonomous, B2 with audit amendments U1-U4 (2026-10-22).
// usage: SepQueueProbe <sep|tpe|base> <c> <P bytes> <N> [histo]
//   sep : SharedExecutorPool executor with c workers; c blockers on a latch, then N tasks each holding a distinct byte[P]
//   tpe : B2h positive control, ThreadPoolExecutor(c, c, ArrayBlockingQueue(1000), AbortPolicy), same workload
//   base: no executor, heap baseline only
// Prints one PROBE line (key=value) after the run. Heap statistic (U3): used after 3 x System.gc() + 300 ms, minus the
// same after the executor and its c blockers exist.
public class SepQueueProbe
{
    static volatile long sink;

    static long liveHeap() throws InterruptedException
    {
        for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(300); }
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    static String histo()
    {
        try
        {
            MBeanServer mbs = ManagementFactory.getPlatformMBeanServer();
            return (String) mbs.invoke(new ObjectName("com.sun.management:type=DiagnosticCommand"), "gcClassHistogram",
                                       new Object[]{ new String[0] }, new String[]{ String[].class.getName() });
        }
        catch (Throwable t) { return "histo failed " + t; }
    }

    public static void main(String[] a) throws Exception
    {
        String mode = a[0];
        int c = Integer.parseInt(a[1]);
        int P = Integer.parseInt(a[2]);
        int N = Integer.parseInt(a[3]);
        boolean histo = a.length > 4 && a[4].equals("histo");
        DatabaseDescriptor.daemonInitialization();
        if (mode.equals("base"))
        {
            System.out.printf("PROBE mode=base c=0 P=0 N=0 baseMiB=%.1f%n", liveHeap() / 1048576.0);
            System.exit(0);
        }
        CountDownLatch gate = new CountDownLatch(1);
        SharedExecutorPool pool = null;
        SEPExecutor sep = null;
        ThreadPoolExecutor tpe = null;
        if (mode.equals("sep"))
        {
            pool = new SharedExecutorPool("Probe");
            sep = (SEPExecutor) pool.newExecutor(c, "probe", "ProbeStage");
        }
        else
            tpe = new ThreadPoolExecutor(c, c, 0, TimeUnit.MILLISECONDS, new ArrayBlockingQueue<>(1000), new ThreadPoolExecutor.AbortPolicy());
        Runnable blocker = () -> { try { gate.await(); } catch (InterruptedException e) { } };
        for (int i = 0; i < c; i++) { if (sep != null) sep.execute(blocker); else tpe.execute(blocker); }
        long until = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
        while ((sep != null ? sep.getActiveTaskCount() : tpe.getActiveCount()) < c && System.nanoTime() < until) Thread.sleep(10);
        int activeBefore = sep != null ? sep.getActiveTaskCount() : tpe.getActiveCount();
        long base = liveHeap();
        java.util.ArrayList<byte[]> reserve = new java.util.ArrayList<>();
        for (int i = 0; i < 64; i++) reserve.add(new byte[128 << 10]);   // 8 MiB of small (non-humongous) arrays, released on OOM (defect H1)
        long submitted = 0, rejected = 0, ooms = 0;
        double maxBlockS = 0, totalS = 0;
        long t0 = System.nanoTime(), blockStart = t0;
        String firstThrown = "none";
        try
        {
            for (int i = 0; i < N; i++)
            {
                final byte[] payload = new byte[P];
                Arrays.fill(payload, (byte) (i | 1));
                Runnable r = () -> { try { gate.await(); } catch (InterruptedException e) { } sink += payload[0]; };
                try
                {
                    if (sep != null) sep.execute(r); else tpe.execute(r);
                    submitted++;
                }
                catch (RejectedExecutionException e) { rejected++; if (firstThrown.equals("none")) firstThrown = "RejectedExecutionException"; }
                if ((i + 1) % 100000 == 0)
                {
                    long now = System.nanoTime();
                    maxBlockS = Math.max(maxBlockS, (now - blockStart) / 1e9);
                    blockStart = now;
                }
            }
        }
        catch (OutOfMemoryError e)
        {
            reserve.clear();
            System.gc();
            ooms++;
            firstThrown = "OutOfMemoryError";
        }
        long now = System.nanoTime();
        maxBlockS = Math.max(maxBlockS, (now - blockStart) / 1e9);
        totalS = (now - t0) / 1e9;
        reserve.clear();
        int pending = sep != null ? sep.getPendingTaskCount() : tpe.getQueue().size();
        int active = sep != null ? sep.getActiveTaskCount() : tpe.getActiveCount();
        long maxTq = sep != null ? sep.getMaxTasksQueued() : -1;
        long live = ooms == 0 ? liveHeap() - base : -1;
        System.out.printf("PROBE mode=%s c=%d P=%d N=%d activeBefore=%d active=%d submitted=%d rejected=%d ooms=%d thrown=%s pending=%d maxTasksQueued=%d " +
                          "liveMiB=%.1f bytesPerTask=%.1f maxBlockS=%.2f totalS=%.2f%n",
                          mode, c, P, N, activeBefore, active, submitted, rejected, ooms, firstThrown, pending, maxTq,
                          live / 1048576.0, ooms == 0 && submitted > 0 ? (double) live / (mode.equals("sep") ? submitted : Math.max(1, pending)) : -1.0, maxBlockS, totalS);
        if (histo && ooms == 0)
        {
            String h = histo();
            int shown = 0;
            for (String l : h.split("\n")) { if (shown++ < 14) System.out.println("HISTO " + l.trim()); }
        }
        gate.countDown();
        if (ooms == 0)
        {
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(120);
            while ((sep != null ? sep.getPendingTaskCount() : tpe.getQueue().size()) > 0 && System.nanoTime() < deadline) Thread.sleep(50);
            Thread.sleep(500);
            int pendAfter = sep != null ? sep.getPendingTaskCount() : tpe.getQueue().size();
            long after = liveHeap() - base;
            System.out.printf("DRAIN mode=%s c=%d P=%d N=%d pendingAfter=%d liveAfterMiB=%.1f drainS=%.1f%n", mode, c, P, N, pendAfter, after / 1048576.0,
                              (System.nanoTime() - now) / 1e9);
        }
        else
            System.out.printf("DRAIN mode=%s c=%d P=%d N=%d skipped_after_oom%n", mode, c, P, N);
        if (pool != null) pool.shutdownAndWait(1, TimeUnit.MINUTES);
        if (tpe != null) tpe.shutdownNow();
        System.exit(0);
    }
}
