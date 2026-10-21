package org.apache.cassandra.concurrent;

import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.BeforeClass;
import org.junit.Test;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.net.ResourceLimits;

// Stage 4 harness, concurrent_writes-takeWorkPermit-workPermits--autonomous, B2a (the filed test, verbatim from the case
// file, frozen sha256 af2af2e5...). The only addition is the last method, supplementaryIdleCallerRuns(), marked
// SUPPLEMENTARY: it is not part of B2f/B2g and checks a source note of the audit (line 196 also returns false when no task
// is queued, so maybeExecuteImmediately on an idle executor does not run inline).
public class SEPQueueHeapProbeTest
{
    static final int S = 64 * 1024;                       // payload per task
    static final int M = Integer.getInteger("probe.tasks", 4000);
    static volatile long sink;

    @BeforeClass public static void init() { DatabaseDescriptor.daemonInitialization(); }

    static long liveHeap() throws InterruptedException
    {
        for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(300); }
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    /** capBytes <= 0: no producer-side cap (claim arm); > 0: positive control gated by ResourceLimits. */
    static void probe(int n, long capBytes) throws Exception
    {
        SharedExecutorPool pool = new SharedExecutorPool("Probe" + n + "_" + capBytes);
        SEPExecutor sep = (SEPExecutor) pool.newExecutor(n, "probe", "ProbeStage" + n + "_" + capBytes);
        ResourceLimits.Concurrent cap = capBytes > 0 ? new ResourceLimits.Concurrent(capBytes) : null;
        CountDownLatch gate = new CountDownLatch(1);
        long base = liveHeap();
        int submitted = 0, rejected = 0;
        for (int i = 0; i < M; i++)
        {
            if (cap != null && !cap.tryAllocate(S)) { rejected++; continue; }
            final byte[] payload = new byte[S];
            Arrays.fill(payload, (byte) i);
            sep.execute(() -> { try { gate.await(); } catch (InterruptedException e) { } sink += payload[0]; });
            submitted++;
        }
        long until = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (sep.getActiveTaskCount() < Math.min(n, submitted) && System.nanoTime() < until) Thread.sleep(10);
        // caller-runs path through line 196: must NOT run inline when all permits are taken
        AtomicBoolean ranInline = new AtomicBoolean();
        Thread caller = Thread.currentThread();
        int pendingBefore = sep.getPendingTaskCount();
        sep.maybeExecuteImmediately(() -> ranInline.set(Thread.currentThread() == caller));
        int pendingAfter = sep.getPendingTaskCount();
        long live = liveHeap() - base;
        System.out.printf("PROBE n=%d cap=%d submitted=%d rejected=%d active=%d pending=%d maxPool=%d " +
                          "mei_inline=%b mei_pendingDelta=%d liveDeltaMiB=%.1f payloadMiB=%.1f%n",
                          n, capBytes, submitted, rejected, sep.getActiveTaskCount(), pendingAfter,
                          sep.getMaximumPoolSize(), ranInline.get(), pendingAfter - pendingBefore,
                          live / 1048576.0, (long) submitted * S / 1048576.0);
        gate.countDown();
        pool.shutdownAndWait(1, TimeUnit.MINUTES);
    }

    @Test public void claim() throws Exception { for (int n : new int[]{ 0, 2, 32, 128 }) probe(n, 0); }
    @Test public void positiveControl() throws Exception { for (long c : new long[]{ 16L << 20, 64L << 20 }) for (int n : new int[]{ 2, 128 }) probe(n, c); }

    /** SUPPLEMENTARY (not in B2f/B2g): an idle executor (no task queued, every permit free). */
    @Test public void supplementaryIdleCallerRuns() throws Exception
    {
        SharedExecutorPool pool = new SharedExecutorPool("ProbeIdle");
        SEPExecutor sep = (SEPExecutor) pool.newExecutor(2, "probe", "ProbeStageIdle");
        Thread caller = Thread.currentThread();
        for (int k = 0; k < 5; k++)
        {
            AtomicBoolean ranInline = new AtomicBoolean();
            CountDownLatch done = new CountDownLatch(1);
            int pendingBefore = sep.getPendingTaskCount();
            int activeBefore = sep.getActiveTaskCount();
            sep.maybeExecuteImmediately(() -> { ranInline.set(Thread.currentThread() == caller); done.countDown(); });
            boolean ran = done.await(10, TimeUnit.SECONDS);
            System.out.printf("SUPPL idle k=%d pendingBefore=%d activeBefore=%d ran=%b mei_inline=%b%n",
                              k, pendingBefore, activeBefore, ran, ranInline.get());
            Thread.sleep(200);
        }
        pool.shutdownAndWait(1, TimeUnit.MINUTES);
    }
}
