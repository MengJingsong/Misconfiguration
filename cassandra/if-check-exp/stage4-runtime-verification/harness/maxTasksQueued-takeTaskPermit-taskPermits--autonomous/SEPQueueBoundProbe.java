package org.apache.cassandra.concurrent;

import java.lang.management.ManagementFactory;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

// Stage 4 harness, maxTasksQueued-takeTaskPermit-taskPermits--autonomous, B2a-B2e: the "small program SEPQueueBoundProbe".
// A standalone main (not junit/testsome) because testsome's maxmemory="1024m" (build.xml:1153) overrides the -Xmx2g of B2a
// (audit amendment R2). usage: java ... SEPQueueBoundProbe <P bytes per task> <rep> <kind: sep|control> [maxN]
// sep:     SharedExecutorPool.newExecutor(1,...) , one blocker holds the only work permit, then execute() N tasks cumulatively
//          to N = 1e4, 1e5, 1e6 (and 4e6 when P = 0); after each: pending, max-queued, wall time, heap after 3 x GC.
// control: ThreadPoolExecutor(1,1,0,ms, ArrayBlockingQueue(10000), AbortPolicy), same blocker and payload; counts accepted/rejected.
public class SEPQueueBoundProbe
{
    static volatile long sink;
    static final long[] TARGETS = { 10_000L, 100_000L, 1_000_000L, 4_000_000L };

    static long liveHeap() throws InterruptedException
    {
        for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(300); }
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    static String histo() throws Exception
    {
        long pid = ProcessHandle.current().pid();
        Process p = new ProcessBuilder("jcmd", Long.toString(pid), "GC.class_histogram").redirectErrorStream(true).start();
        StringBuilder sb = new StringBuilder();
        try (java.util.Scanner s = new java.util.Scanner(p.getInputStream()))
        {
            while (s.hasNextLine())
            {
                String l = s.nextLine();
                if (l.contains("ConcurrentLinkedQueue$Node") || l.contains(" [B ") || l.contains("SEPQueueBoundProbe$$Lambda") || l.startsWith("Total") || l.contains("FutureTask"))
                    sb.append("  HISTO ").append(l.trim()).append('\n');
            }
        }
        p.waitFor();
        return sb.toString();
    }

    public static void main(String[] a) throws Exception
    {
        int P = Integer.parseInt(a[0]);
        String rep = a[1], kind = a[2];
        long maxN = a.length > 3 ? Long.parseLong(a[3]) : (P == 0 ? 4_000_000L : 1_000_000L);
        System.out.printf("PROBE-START kind=%s P=%d rep=%s maxHeapMiB=%d maxN=%d%n", kind, P, rep, Runtime.getRuntime().maxMemory() >> 20, maxN);
        if (kind.equals("sep")) sep(P, rep, maxN); else control(P, rep, maxN);
        System.out.println("PROBE-END kind=" + kind + " P=" + P + " rep=" + rep);
        System.exit(0);
    }

    static void sep(int P, String rep, long maxN) throws Exception
    {
        SharedExecutorPool pool = new SharedExecutorPool("probe");
        SEPExecutor sep = (SEPExecutor) pool.newExecutor(1, "internal", "probe");
        CountDownLatch gate = new CountDownLatch(1);
        sep.execute(() -> { try { gate.await(); } catch (InterruptedException e) { } });
        long until = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
        while (sep.getActiveTaskCount() < 1 && System.nanoTime() < until) Thread.sleep(10);
        long base = liveHeap();
        System.out.printf("PROBE kind=sep P=%d rep=%s N=0 active=%d pending=%d maxQueued=%d heapMiB=%.2f deltaMiB=0.00%n",
                          P, rep, sep.getActiveTaskCount(), sep.getPendingTaskCount(), sep.getMaxTasksQueued(), base / 1048576.0);
        long n = 0;
        String err = "none";
        for (long target : TARGETS)
        {
            if (target > maxN) break;
            long t0 = System.nanoTime();
            long maxCallNs = 0;
            long submitted = 0;
            try
            {
                for (; n < target; n++)
                {
                    long c0 = System.nanoTime();
                    final byte[] payload = new byte[P];
                    sep.execute(() -> { sink += payload.length; });
                    long c1 = System.nanoTime() - c0;
                    if (c1 > maxCallNs) maxCallNs = c1;
                    submitted++;
                }
            }
            catch (Throwable t) { err = t.getClass().getName() + ":" + t.getMessage(); }
            long wallMs = (System.nanoTime() - t0) / 1_000_000;
            long h = liveHeap();
            int pend = sep.getPendingTaskCount();
            System.out.printf("PROBE kind=sep P=%d rep=%s N=%d submitted=%d active=%d pending=%d maxQueued=%d wallMs=%d maxCallUs=%d err=%s heapMiB=%.2f deltaMiB=%.2f perTaskB=%.1f%n",
                              P, rep, n, submitted, sep.getActiveTaskCount(), pend, sep.getMaxTasksQueued(), wallMs, maxCallNs / 1000, err,
                              h / 1048576.0, (h - base) / 1048576.0, (h - base) / (double) Math.max(1, n));
            if (!err.equals("none")) break;
        }
        System.out.print(histo());
        long completedBefore = sep.getCompletedTaskCount();
        gate.countDown();
        until = System.nanoTime() + TimeUnit.SECONDS.toNanos(300);
        while ((sep.getPendingTaskCount() > 0 || sep.getActiveTaskCount() > 0) && System.nanoTime() < until) Thread.sleep(50);
        Thread.sleep(300);
        System.out.printf("PROBE kind=sep P=%d rep=%s DRAIN pending=%d active=%d completed=%d expectedCompleted=%d%n",
                          P, rep, sep.getPendingTaskCount(), sep.getActiveTaskCount(), sep.getCompletedTaskCount(), n + 1);
        pool.shutdownAndWait(1, TimeUnit.MINUTES);
    }

    static void control(int P, String rep, long maxN) throws Exception
    {
        ThreadPoolExecutor tpe = new ThreadPoolExecutor(1, 1, 0, TimeUnit.MILLISECONDS, new ArrayBlockingQueue<>(10000), new ThreadPoolExecutor.AbortPolicy());
        CountDownLatch gate = new CountDownLatch(1);
        tpe.execute(() -> { try { gate.await(); } catch (InterruptedException e) { } });
        long until = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
        while (tpe.getActiveCount() < 1 && System.nanoTime() < until) Thread.sleep(10);
        long base = liveHeap();
        long n = 0, accepted = 0, rejected = 0;
        String firstReject = "none";
        for (long target : TARGETS)
        {
            if (target > maxN) break;
            long t0 = System.nanoTime();
            for (; n < target; n++)
            {
                final byte[] payload = new byte[P];
                try { tpe.execute(() -> { sink += payload.length; }); accepted++; }
                catch (RejectedExecutionException e) { if (rejected == 0) firstReject = "afterAccepted=" + accepted; rejected++; }
            }
            long wallMs = (System.nanoTime() - t0) / 1_000_000;
            long h = liveHeap();
            System.out.printf("PROBE kind=control P=%d rep=%s N=%d accepted=%d rejected=%d queued=%d firstReject=%s wallMs=%d heapMiB=%.2f deltaMiB=%.2f%n",
                              P, rep, n, accepted, rejected, tpe.getQueue().size(), firstReject, wallMs, h / 1048576.0, (h - base) / 1048576.0);
        }
        gate.countDown();
        tpe.shutdown();
        tpe.awaitTermination(5, TimeUnit.MINUTES);
        System.out.printf("PROBE kind=control P=%d rep=%s DRAIN completed=%d%n", P, rep, tpe.getCompletedTaskCount());
    }
}
