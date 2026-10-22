package org.apache.cassandra.utils.memory;

// Stage-4 harness for cases/memtable_heap_space-needsCleaning-nextClean--autonomous.md, section B2e.
// The case file's code, with the two audit amendments of 2026-10-21 (marked "AMEND"):
//  U1: B2h's off-heap control is printed and asserted (offHeap.used()==0, offHeap.needsCleaning()==false).
//  U2: Part C records the helper's chunk count and the bytes released, so "the block was lifted" is a
//      number: after release the helper allocates floor(released/C) more chunks (+-1) and blocks again at <= L.

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import org.junit.Assert;
import org.junit.Test;
import org.apache.cassandra.utils.concurrent.ImmediateFuture;
import org.apache.cassandra.utils.concurrent.OpOrder;

public class NextCleanBoundaryTest
{
    static final long MiB = 1L << 20, C = 256 * 1024;
    static final float[] TS = { 0.10f, 0.25f, 0.33333334f, 0.50f, 0.90f };

    /** Part A: first trigger, cleaner blocks after its first snapshot (no reclaim). */
    long[] first(long L, float t) throws Exception
    {
        AtomicReference<long[]> snap = new AtomicReference<>();
        AtomicInteger invocations = new AtomicInteger();
        CountDownLatch fired = new CountDownLatch(1), release = new CountDownLatch(1);
        AtomicReference<SlabPool> ref = new AtomicReference<>();
        SlabPool pool = new SlabPool(L, 0, t, () -> {
            invocations.incrementAndGet();
            MemtablePool.SubPool p = ref.get().onHeap;
            if (snap.compareAndSet(null, new long[]{ p.used(), p.getReclaiming(), p.nextClean })) fired.countDown();
            try { release.await(); } catch (InterruptedException e) { return ImmediateFuture.success(false); }
            return ImmediateFuture.success(true);
        });
        ref.set(pool);
        MemtableAllocator.SubAllocator sub = pool.onHeap.newAllocator();
        OpOrder.Group g = new OpOrder().start();
        long directUsed = -1, directIdx = -1, i = 0;
        while (pool.onHeap.used() + C <= (long) (0.95 * L))
        {
            sub.allocate(C, g); i++;
            if (directIdx < 0 && pool.onHeap.needsCleaning()) { directIdx = i; directUsed = pool.onHeap.used(); }
            if (fired.await(20, TimeUnit.MILLISECONDS)) break;
        }
        // AMEND U1: off-heap sub-pool (limit 0 under heap_buffers) never drives the disjunction
        long offUsed = pool.offHeap.used();
        boolean offNeeds = pool.offHeap.needsCleaning();
        pool.shutdownAndWait(10, TimeUnit.SECONDS); release.countDown();
        long[] s = snap.get();
        System.out.printf("NCB A L=%d t=%s T=%d directIdx=%d directUsed=%d cleanerUsed=%d cleanerRecl=%d nextClean=%d invocations=%d offHeapUsed=%d offHeapNeedsCleaning=%s%n",
                          L, t, (long) (L * t), directIdx, directUsed, s == null ? -1 : s[0], s == null ? -1 : s[1], s == null ? -1 : s[2],
                          invocations.get(), offUsed, offNeeds);
        Assert.assertEquals(0, offUsed);
        Assert.assertFalse(offNeeds);
        return new long[]{ directIdx, directUsed, s == null ? -1 : s[0], s == null ? -1 : s[2] };
    }

    @Test public void partA() throws Exception
    {
        long L = 64 * MiB;
        for (float t : TS)
        {
            long T = (long) (L * t), m = T / C + 1;
            long[] r = first(L, t);
            Assert.assertEquals(m, r[0]);            // line 128 first true at chunk m
            Assert.assertEquals(m * C, r[1]);
            Assert.assertEquals(m * C, r[2]);        // cleaner saw same operand
            Assert.assertEquals(T, r[3]);            // nextClean == 0 + (long)(L*t)
        }
        for (long L2 : new long[]{ 32 * MiB, 128 * MiB })
        {
            long T = (long) (L2 * 0.25f), m = T / C + 1;
            Assert.assertEquals(m * C, first(L2, 0.25f)[1]);
        }
    }

    /** Part B: cleaner simulates a memtable switch (setDiscarding + new allocator);
     *  Part C: then push past the hard limit, check blocking, release. */
    @Test public void partBC() throws Exception
    {
        long L = 64 * MiB;
        for (float t : TS)
        {
            List<long[]> snaps = Collections.synchronizedList(new ArrayList<>());
            List<MemtableAllocator.SubAllocator> discarding = Collections.synchronizedList(new ArrayList<>());
            AtomicReference<SlabPool> ref = new AtomicReference<>();
            AtomicReference<MemtableAllocator.SubAllocator> cur = new AtomicReference<>();
            SlabPool pool = new SlabPool(L, 0, t, () -> {
                MemtablePool.SubPool p = ref.get().onHeap;
                snaps.add(new long[]{ p.used(), p.getReclaiming(), p.nextClean });
                MemtableAllocator.SubAllocator old = cur.getAndSet(p.newAllocator());
                old.setDiscarding(); discarding.add(old);
                return ImmediateFuture.success(true);
            });
            ref.set(pool); cur.set(pool.onHeap.newAllocator());
            OpOrder.Group g = new OpOrder().start();
            long maxUsed = 0;
            while (pool.onHeap.used() + C <= (long) (0.95 * L))
            {
                cur.get().allocate(C, g); maxUsed = Math.max(maxUsed, pool.onHeap.used());
                Thread.sleep(20);
            }
            long T = (long) (L * t);
            int partB = snaps.size();
            synchronized (snaps)
            {
                int k = 0;
                for (long[] s : snaps)
                {
                    long live = s[0] - s[1];
                    k++;
                    System.out.printf("NCB B t=%s k=%d used=%d recl=%d live=%d T=%d nextClean=%d%n", t, k, s[0], s[1], live, T, s[2]);
                    Assert.assertTrue(live > T && live <= T + 2 * C);
                }
            }
            System.out.printf("NCB B t=%s triggersB=%d endUsedB=%d%n", t, partB, pool.onHeap.used());
            // Part C: exceed hard limit
            AtomicLong helperChunks = new AtomicLong();   // AMEND U2
            ExecutorService ex = Executors.newSingleThreadExecutor();
            Future<?> f = ex.submit(() -> { while (true) { cur.get().allocate(C, g); helperChunks.incrementAndGet(); if (Thread.interrupted()) return; } });
            boolean blocked = false;
            try { f.get(2, TimeUnit.SECONDS); } catch (TimeoutException e) { blocked = true; }
            long usedAtBlock = pool.onHeap.used();
            long chunksAtBlock = helperChunks.get();
            System.out.printf("NCB C t=%s triggers=%d blocked=%s usedAtBlock=%d L=%d maxUsedB=%d helperChunks=%d%n",
                              t, snaps.size(), blocked, usedAtBlock, L, maxUsed, chunksAtBlock);
            Assert.assertTrue(blocked);
            Assert.assertTrue(usedAtBlock <= L);
            long released = 0;
            synchronized (discarding) { for (MemtableAllocator.SubAllocator s : discarding) { released += s.owns(); s.setDiscarded(); } }
            Thread.sleep(200);
            long usedAfter = pool.onHeap.used(), chunksAfter = helperChunks.get();
            System.out.printf("NCB C t=%s afterRelease released=%d used=%d recl=%d helperChunksAfter=%d delta=%d expectedDelta=%d blockedAgain=%s%n",
                              t, released, usedAfter, pool.onHeap.getReclaiming(), chunksAfter, chunksAfter - chunksAtBlock,
                              released / C, !f.isDone());
            Assert.assertTrue(usedAfter <= L);
            ex.shutdownNow(); pool.shutdownAndWait(10, TimeUnit.SECONDS);
        }
    }
}
