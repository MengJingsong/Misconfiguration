package org.apache.cassandra.concurrent;

import java.lang.management.ManagementFactory;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.net.ResourceLimits;

public class SEPMemoryProbeTest
{
    static final int PAYLOAD = 64 * 1024;   // bytes retained per task
    static final int M = 2000;              // tasks per run -> 2000 * 64 KiB = 125 MiB

    @BeforeClass
    public static void init() { DatabaseDescriptor.daemonInitialization(); }

    static long usedAfterGc() throws InterruptedException
    {
        for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(200); }
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    static Runnable task(CountDownLatch gate, AtomicInteger running, AtomicInteger peak)
    {
        final byte[] payload = new byte[PAYLOAD];
        payload[PAYLOAD - 1] = 1;
        return () -> {
            int r = running.incrementAndGet();
            peak.accumulateAndGet(r, Math::max);
            try { gate.await(120, TimeUnit.SECONDS); } catch (InterruptedException e) { }
            if (payload[PAYLOAD - 1] != 1) throw new AssertionError();
            running.decrementAndGet();
        };
    }

    // Phase 1: retained heap vs maximum pool size
    @Test
    public void heapVsPoolSize() throws Exception
    {
        for (int n : new int[]{ 1, 4, 32, 128 })
        {
            SharedExecutorPool pool = new SharedExecutorPool("Probe" + n);
            SEPExecutor exec = (SEPExecutor) pool.newExecutor(n, "internal", "probe" + n);
            CountDownLatch gate = new CountDownLatch(1);
            AtomicInteger running = new AtomicInteger(), peak = new AtomicInteger();
            long base = usedAfterGc();
            for (int i = 0; i < M; i++) exec.execute(task(gate, running, peak));
            Thread.sleep(2000);
            long used = usedAfterGc();
            System.out.printf("PROBE phase=1 max=%d active=%d pending=%d running=%d peak=%d heapDeltaMiB=%.1f%n",
                              n, exec.getActiveTaskCount(), exec.getPendingTaskCount(), running.get(), peak.get(),
                              (used - base) / 1048576.0);
            gate.countDown();
            pool.shutdownAndWait(60, TimeUnit.SECONDS);
        }
    }

    // Phase 2: shrink while all workers are busy -> drives workPermits < 0 (SEPExecutor.java:165)
    @Test
    public void shrinkDrivesNegativeWorkPermits() throws Exception
    {
        SharedExecutorPool pool = new SharedExecutorPool("ProbeShrink");
        SEPExecutor exec = (SEPExecutor) pool.newExecutor(32, "internal", "probeShrink");
        CountDownLatch gate1 = new CountDownLatch(1), gate2 = new CountDownLatch(1);
        AtomicInteger running = new AtomicInteger(), peak = new AtomicInteger();
        long base = usedAfterGc();
        for (int i = 0; i < 32; i++) exec.execute(task(gate1, running, peak));
        Thread.sleep(1000);
        for (int i = 0; i < 200; i++) exec.execute(task(gate2, running, peak));
        Thread.sleep(1000);
        long before = usedAfterGc();
        System.out.printf("PROBE phase=2a max=%d active=%d pending=%d running=%d heapDeltaMiB=%.1f%n",
                          exec.getMaximumPoolSize(), exec.getActiveTaskCount(), exec.getPendingTaskCount(), running.get(), (before - base) / 1048576.0);
        exec.setMaximumPoolSize(4);   // workPermits = 4 - 32 = -28
        System.out.printf("PROBE phase=2b max=%d active=%d pending=%d running=%d%n",
                          exec.getMaximumPoolSize(), exec.getActiveTaskCount(), exec.getPendingTaskCount(), running.get());
        gate1.countDown();            // 32 tasks finish; 28 workers must exit via RETURNED_WORK_PERMIT
        Thread.sleep(2000);
        long after = usedAfterGc();
        System.out.printf("PROBE phase=2c max=%d active=%d pending=%d running=%d heapDeltaMiB=%.1f%n",
                          exec.getMaximumPoolSize(), exec.getActiveTaskCount(), exec.getPendingTaskCount(), running.get(), (after - base) / 1048576.0);
        gate2.countDown();
        pool.shutdownAndWait(60, TimeUnit.SECONDS);
    }

    // Phase 3 (positive control): same tasks admitted through a byte limit that is known to bind
    @Test
    public void positiveControlByteLimit() throws Exception
    {
        for (long limitMiB : new long[]{ 16, 64 })
        {
            SharedExecutorPool pool = new SharedExecutorPool("ProbeCtl" + limitMiB);
            SEPExecutor exec = (SEPExecutor) pool.newExecutor(4, "internal", "probeCtl" + limitMiB);
            ResourceLimits.Concurrent limit = new ResourceLimits.Concurrent(limitMiB << 20);
            CountDownLatch gate = new CountDownLatch(1);
            AtomicInteger running = new AtomicInteger(), peak = new AtomicInteger();
            int accepted = 0;
            long base = usedAfterGc();
            for (int i = 0; i < M; i++)
                if (limit.tryAllocate(PAYLOAD)) { exec.execute(task(gate, running, peak)); accepted++; }
            Thread.sleep(2000);
            long used = usedAfterGc();
            System.out.printf("PROBE phase=3 limitMiB=%d accepted=%d pending=%d heapDeltaMiB=%.1f%n",
                              limitMiB, accepted, exec.getPendingTaskCount(), (used - base) / 1048576.0);
            gate.countDown();
            pool.shutdownAndWait(60, TimeUnit.SECONDS);
        }
    }

    // Phase 4 (audit amendment R4, 2026-10-21): working memory held only by RUNNING tasks (instrument check for
    // "usage = running tasks x per-task bytes"); queued tasks capture nothing, a task allocates W = 1 MiB when it starts
    static final int W = 1 << 20;

    @Test
    public void workingMemoryPerRunningTask() throws Exception
    {
        System.out.println("PROBE phase=4info xmxMiB=" + (Runtime.getRuntime().maxMemory() >> 20));
        for (int n : new int[]{ 1, 4, 32, 128 })
        {
            SharedExecutorPool pool = new SharedExecutorPool("ProbeWM" + n);
            SEPExecutor exec = (SEPExecutor) pool.newExecutor(n, "internal", "probeWM" + n);
            CountDownLatch gate = new CountDownLatch(1);
            AtomicInteger running = new AtomicInteger(), peak = new AtomicInteger();
            long base = usedAfterGc();
            for (int i = 0; i < M; i++)
                exec.execute(() -> {
                    byte[] work = new byte[W];
                    work[W - 1] = 1;
                    int r = running.incrementAndGet();
                    peak.accumulateAndGet(r, Math::max);
                    try { gate.await(120, TimeUnit.SECONDS); } catch (InterruptedException e) { }
                    if (work[W - 1] != 1) throw new AssertionError();
                    running.decrementAndGet();
                });
            Thread.sleep(2000);
            long used = usedAfterGc();
            System.out.println(String.format("PROBE phase=4 max=%d active=%d pending=%d running=%d peak=%d heapDeltaMiB=%.1f",
                                             n, exec.getActiveTaskCount(), exec.getPendingTaskCount(), running.get(), peak.get(),
                                             (used - base) / 1048576.0));
            gate.countDown();
            pool.shutdownAndWait(60, TimeUnit.SECONDS);
        }
    }
}
