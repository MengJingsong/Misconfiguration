/*
 * Stage 4 unit tier (B2, as amended 2026-10-26) of
 * cases/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous.md.
 * The filed B2c sketch, with the B2b/B2c amendments: N in {1,4,16,32,64,128}, M = 256 (control D: N = 64, M = 8),
 * settle 2 s (5 s if the cap is not reached), exact high-water after the release, shrink 64 -> 1 with a 35 s wait.
 * Runbook fix 2026-10-26 (defect 1): each line is one println of a String.format (the test JVM logs every
 * write of System.out as its own line, so printf fragments split a reading).
 * Readings are printed on lines starting "SEPFP" (they land in the TEST-<class>.log file under build/test/logs).
 */
package org.apache.cassandra.concurrent;

import java.lang.management.ManagementFactory;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;

public class SEPMaxPoolSizeFootprintTest
{
    @BeforeClass
    public static void init()
    {
        DatabaseDescriptor.daemonInitialization();
        System.out.println("SEPFP-SETUP java=" + System.getProperty("java.version") + " gc=" +
                           ManagementFactory.getGarbageCollectorMXBeans().stream().map(b -> b.getName()).reduce((a, b) -> a + "," + b).orElse("?") +
                           " maxHeap=" + Runtime.getRuntime().maxMemory());
    }

    static long heapUsed()
    {
        for (int i = 0; i < 3; i++)
            System.gc();
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    static int liveThreads(SharedExecutorPool p)
    {
        Thread[] t = new Thread[4096];
        int n = p.threadGroup.enumerate(t);
        int c = 0;
        for (int i = 0; i < n; i++)
            if (t[i].isAlive())
                c++;
        return c;
    }

    void run(int N, int M, boolean queuedPayload, boolean shrink) throws Exception
    {
        String tag = (M == 256 ? "" : "m" + M) + (queuedPayload ? "q" : "");
        SharedExecutorPool pool = new SharedExecutorPool("FP" + N + tag.toUpperCase());
        LocalAwareExecutorPlus ex = pool.newExecutor(N, "internal", "fp" + N + tag);
        SEPExecutor sep = (SEPExecutor) ex;
        AtomicInteger running = new AtomicInteger(), maxRunning = new AtomicInteger();
        CountDownLatch release = new CountDownLatch(1);
        long h0 = heapUsed();
        for (int i = 0; i < M; i++)
        {
            final byte[] carried = queuedPayload ? new byte[256 << 10] : null;
            ex.execute(() -> {
                int r = running.incrementAndGet();
                maxRunning.accumulateAndGet(r, Math::max);
                byte[] held = new byte[1 << 20];
                try { release.await(30, TimeUnit.SECONDS); } catch (InterruptedException e) {}
                if (held.length + (carried == null ? 0 : carried.length) < 0) System.out.print("");
                running.decrementAndGet();
            });
        }
        int settle = 2000;
        Thread.sleep(2000);
        if (maxRunning.get() < Math.min(N, M))
        {
            Thread.sleep(3000);   // B2h: repeat with 5 s
            settle = 5000;
        }
        int mr = maxRunning.get(), active = sep.getActiveTaskCount(), pending = sep.getPendingTaskCount(), threads = liveThreads(pool);
        long hd = heapUsed() - h0;
        System.out.println(String.format("SEPFP N=%d M=%d Q=%b settleMs=%d maxRunning=%d active=%d pending=%d threads=%d heapDeltaBytes=%d heapDeltaMiB=%.2f",
                          N, M, queuedPayload, settle, mr, active, pending, threads, hd, hd / 1048576.0));
        release.countDown();
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(60);
        while (sep.getCompletedTaskCount() < M && System.nanoTime() < deadline)
            Thread.sleep(50);
        System.out.println(String.format("SEPFP-DONE N=%d M=%d Q=%b completed=%d maxRunningFinal=%d threadsAfter=%d",
                          N, M, queuedPayload, sep.getCompletedTaskCount(), maxRunning.get(), liveThreads(pool)));
        if (shrink)
        {
            ex.setMaximumPoolSize(1);
            int max = ex.getMaximumPoolSize();
            Thread.sleep(35000);
            System.out.println(String.format("SEPFP-SHRINK N=%d max=%d threads=%d waitMs=35000 activeAfter=%d",
                              N, max, liveThreads(pool), sep.getActiveTaskCount()));
        }
        pool.shutdownAndWait(10, TimeUnit.SECONDS);
    }

    @Test
    public void sweep() throws Exception
    {
        for (int N : new int[]{ 1, 4, 16, 32, 64, 128 })
        {
            run(N, 256, false, N == 64);
            run(N, 256, true, false);
        }
        run(64, 8, false, false);   // control D: demand below the cap
        System.out.println("SEPFP-END");
    }
}
