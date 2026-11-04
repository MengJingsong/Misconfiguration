/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
package org.apache.cassandra.utils.memory;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.After;
import org.junit.Assert;
import org.junit.Before;
import org.junit.Test;

import org.apache.cassandra.utils.concurrent.ImmediateFuture;
import org.apache.cassandra.utils.concurrent.OpOrder;

/**
 * Stage-4 harness for if-check-exp case memtable_offheap_space-tryAllocate-limit, §9e unit step 2.
 * Drives MemtablePool.SubPool.tryAllocate() (MemtablePool.java:156) on the offHeap pool of a NativePool
 * through NativeAllocator.allocate() (NativeAllocator.java:141), and records:
 *   1. the pool filled to its limit (100 B) in 10-byte pieces;
 *   2. an 11th piece parks: thread state WAITING with a frame in MemtableAllocator$SubAllocator.allocate,
 *      and a timed Future.get() that times out;
 *   3. while it is parked the counter stays at 100 (the disallow branch does no CAS);
 *   4. releasing 10 B wakes it and the counter is 100 again;
 *   5. with the OpOrder group marked blocking, a further piece is forced through: counter 110;
 *   6. discarding the allocator returns the counter to 0 (the region ledger's known answer:
 *      one 8,192 B region, owns=110 at the discard).
 * One "STAGE4 <step> <name>=<value>" line per assertion goes to stdout and to the file named by the
 * system property stage4.out, if set. A mismatch fails the test (JUnit) after its line is written.
 */
public class NativePoolTest
{
    private static final long LIMIT = 100;   // bytes: the pool's offHeap limit
    private static final int PIECE = 10;

    private ExecutorService exec;
    private OpOrder order;
    private OpOrder.Group group;
    private NativePool pool;
    private NativeAllocator allocator;
    private PrintWriter out;

    @Before
    public void setUp() throws IOException
    {
        exec = Executors.newFixedThreadPool(2);
        order = new OpOrder();
        group = order.start();
        // heap limit 1 and clean threshold 0.75 as NativeAllocatorTest.setUp(); the cleaner does nothing and
        // reports that nothing was scheduled (false), so the cleaner thread is not re-signalled in a loop
        pool = new NativePool(1, LIMIT, 0.75f, () -> ImmediateFuture.success(false));
        allocator = new NativeAllocator(pool);
        String path = System.getProperty("stage4.out");
        out = path == null ? null : new PrintWriter(new FileWriter(path, true), true);
    }

    @After
    public void tearDown()
    {
        exec.shutdownNow();
        if (out != null)
            out.close();
    }

    private void record(String step, String name, Object value)
    {
        String line = "STAGE4 " + step + ' ' + name + '=' + value;
        System.out.println(line);
        if (out != null)
            out.println(line);
    }

    private void check(String step, String name, long expected, long actual)
    {
        record(step, name, actual + (expected == actual ? "" : " MISMATCH expected=" + expected));
        Assert.assertEquals(step + ' ' + name, expected, actual);
    }

    private static boolean parkedInSubAllocator(Thread t)
    {
        if (t == null || t.getState() != Thread.State.WAITING)
            return false;
        for (StackTraceElement e : t.getStackTrace())
            if (e.getClassName().equals("org.apache.cassandra.utils.memory.MemtableAllocator$SubAllocator")
                && e.getMethodName().equals("allocate"))
                return true;
        return false;
    }

    @Test
    public void testParksAtLimitWakesOnReleaseAndForcesThroughWhenBlocking() throws Exception
    {
        // 1. fill exactly to the limit: each tryAllocate(10) passes while allocated + 10 <= 100
        for (int i = 0; i < LIMIT / PIECE; i++)
            Assert.assertTrue(allocator.allocate(PIECE, group) > 0);
        check("1", "pool.offHeap.used", LIMIT, pool.offHeap.used());
        check("1", "allocator.offHeap.owns", LIMIT, allocator.offHeap().owns());

        // 2. one more piece: 100 + 10 > 100, the disallow branch; group is not blocking, so the caller parks
        AtomicReference<Thread> waiter = new AtomicReference<>();
        Future<Long> pending = exec.submit(() -> {
            waiter.set(Thread.currentThread());
            return allocator.allocate(PIECE, group);
        });
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (!parkedInSubAllocator(waiter.get()) && System.nanoTime() < deadline)
            Thread.sleep(10);
        Thread w = waiter.get();
        record("2", "waiter.state", w == null ? "null" : w.getState());
        StringBuilder frames = new StringBuilder();
        if (w != null)
            for (StackTraceElement e : w.getStackTrace())
                if (e.getClassName().startsWith("org.apache.cassandra.utils.memory."))
                    frames.append(e.getClassName().substring(e.getClassName().lastIndexOf('.') + 1))
                          .append('.').append(e.getMethodName()).append(':').append(e.getLineNumber()).append(',');
        record("2", "waiter.frames", frames);
        check("2", "parked_in_SubAllocator.allocate", 1, parkedInSubAllocator(w) ? 1 : 0);
        boolean timedOut = false;
        try
        {
            pending.get(300, TimeUnit.MILLISECONDS);
        }
        catch (TimeoutException e)
        {
            timedOut = true;
        }
        check("2", "future_get_300ms_timed_out", 1, timedOut ? 1 : 0);

        // 3. still parked two seconds later, and no CAS was done
        Thread.sleep(2000);
        check("3", "pool.offHeap.used_after_2s", LIMIT, pool.offHeap.used());
        check("3", "still_parked", 1, parkedInSubAllocator(w) ? 1 : 0);

        // 4. release one piece: SubPool.released() signals hasRoom, the waiter retries and gets its 10 bytes
        allocator.offHeap().released(PIECE);
        long peer = pending.get(5, TimeUnit.SECONDS);
        check("4", "woken_allocation_returned_peer", 1, peer > 0 ? 1 : 0);
        check("4", "pool.offHeap.used", LIMIT, pool.offHeap.used());

        // 5. mark the group's barrier blocking, as a flush does (ColumnFamilyStore), then request one more
        //    piece from another thread: tryAllocate fails, isBlocking() is true, allocated() forces it through
        OpOrder.Barrier barrier = order.newBarrier();
        barrier.issue();
        barrier.markBlocking();
        Future<Long> forced = exec.submit(() -> allocator.allocate(PIECE, group));
        long forcedPeer = forced.get(1, TimeUnit.SECONDS);
        check("5", "forced_allocation_returned_peer", 1, forcedPeer > 0 ? 1 : 0);
        check("5", "pool.offHeap.used", LIMIT + PIECE, pool.offHeap.used());
        check("5", "allocator.offHeap.owns", LIMIT + PIECE, allocator.offHeap().owns());

        // 6. discard: NativeAllocator.setDiscarded() frees the region(s), then releases the accounting
        allocator.setDiscarding();
        allocator.setDiscarded();
        check("6", "pool.offHeap.used_after_discard", 0, pool.offHeap.used());
        record("done", "result", "pass");
    }
}
