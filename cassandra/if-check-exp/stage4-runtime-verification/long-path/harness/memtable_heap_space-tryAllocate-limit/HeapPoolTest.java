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

import java.nio.ByteBuffer;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.junit.After;
import org.junit.Assert;
import org.junit.Before;
import org.junit.Test;

import org.apache.cassandra.utils.concurrent.ImmediateFuture;
import org.apache.cassandra.utils.concurrent.OpOrder;

/**
 * Verification experiment for the if-check-exp case
 * memtable/memtable_heap_space-tryAllocate-limit.md: drives execution into the
 * disallow branch of MemtablePool.SubPool.tryAllocate() (MemtablePool.java:156)
 * via the on-heap path (HeapPool.Allocator -> MemtableAllocator.SubAllocator),
 * and captures direct evidence of both disallow-branch outcomes:
 *   1. the calling thread blocking on SubPool.hasRoom (testBlocksThenUnblocksOnRelease)
 *   2. the isBlocking() escape hatch overshooting the limit (testForcesThroughWhenOpGroupIsBlocking)
 */
public class HeapPoolTest
{
    private static final long LIMIT = 100; // bytes - deterministic single-shot trigger

    private ExecutorService exec;
    private OpOrder order;
    private OpOrder.Group group;
    private HeapPool pool;
    private HeapPool.Allocator allocator;

    @Before
    public void setUp()
    {
        exec = Executors.newSingleThreadExecutor();
        order = new OpOrder();
        group = order.start();
        // cleanThreshold=1.0f and a no-op cleaner: we are testing the HARD
        // limit in tryAllocate(), not the soft needsCleaning() threshold, so
        // the cleaner should never need to run in this test.
        pool = new HeapPool(LIMIT, 1.0f, () -> ImmediateFuture.success(true));
        allocator = (HeapPool.Allocator) pool.newAllocator("if_check_exp_heap_pool_test");
    }

    @After
    public void tearDown()
    {
        exec.shutdownNow();
    }

    /**
     * Evidence path 1: fill the pool exactly to LIMIT, then request one more
     * byte. tryAllocate() must return false (100 + 1 > 100) -> the disallow
     * branch -> the calling thread parks in
     * WaitQueue$Signal.awaitThrowUncheckedOnInterrupt() (MemtableAllocator.java:195)
     * because opGroup.isBlocking() is false at this point.
     *
     * We prove the park with a timed Future.get() that must time out. We then
     * release capacity (SubAllocator.released(), MemtableAllocator.java:244-256,
     * which calls SubPool.released() -> hasRoom.signalAll(), MemtablePool.java:192-197)
     * and prove the parked call then completes and returns a correctly-sized
     * ByteBuffer, with pool usage reflecting the net allocation.
     */
    @Test
    public void testBlocksThenUnblocksOnRelease() throws Exception
    {
        // fill exactly to the limit: tryAllocate(100) -> 0 + 100 <= 100 -> allow branch
        ByteBuffer first = allocator.allocate((int) LIMIT, group);
        Assert.assertEquals(LIMIT, first.capacity());
        Assert.assertEquals(LIMIT, pool.onHeap.used());
        Assert.assertEquals(LIMIT, allocator.onHeap().owns());

        // request 1 more byte: tryAllocate(1) -> 100 + 1 > 100 -> DISALLOW BRANCH
        Callable<ByteBuffer> overLimit = () -> allocator.allocate(1, group);
        Future<ByteBuffer> pending = exec.submit(overLimit);

        // EVIDENCE 1: the call must NOT complete - it is parked on hasRoom,
        // not rejected and not silently succeeding.
        boolean timedOut = false;
        try
        {
            pending.get(300, TimeUnit.MILLISECONDS);
        }
        catch (TimeoutException e)
        {
            timedOut = true;
        }
        Assert.assertTrue("expected the over-limit allocate() to block, but it returned instead", timedOut);
        // usage must be unchanged while parked - the disallow branch performed no CAS
        Assert.assertEquals(LIMIT, pool.onHeap.used());

        // release 50 bytes from the first allocation -> SubPool.released(50)
        // -> hasRoom.signalAll() -> wakes the parked thread -> it retries
        // tryAllocate(1): 50 + 1 <= 100 -> now succeeds via the allow branch.
        allocator.onHeap().released(50);

        // EVIDENCE 2: the previously-parked call now completes and returns
        // a correctly-sized ByteBuffer.
        ByteBuffer second = pending.get(5, TimeUnit.SECONDS);
        Assert.assertEquals(1, second.capacity());
        Assert.assertEquals(LIMIT - 50 + 1, pool.onHeap.used());
    }

    /**
     * Evidence path 2: the escape hatch. Fill to the limit as above, then
     * mark this opGroup's barrier "blocking" BEFORE requesting the extra
     * byte, so opGroup.isBlocking() is already true when tryAllocate() fails.
     * Per MemtableAllocator.java:180-184, this takes the force-through path
     * (allocated(size)) instead of parking - proving the if-check's disallow
     * branch does not stop this class of caller, only non-blocking ones.
     */
    @Test
    public void testForcesThroughWhenOpGroupIsBlocking() throws Exception
    {
        ByteBuffer first = allocator.allocate((int) LIMIT, group);
        Assert.assertEquals(LIMIT, pool.onHeap.used());

        // mark this group's in-flight op as "blocking", the same way a flush
        // barrier does for writes it must wait out (ColumnFamilyStore.java:1238)
        OpOrder.Barrier barrier = order.newBarrier();
        barrier.issue();
        barrier.markBlocking();

        // tryAllocate(1) still returns false (100 + 1 > 100), but this time
        // opGroup.isBlocking() is true, so allocate() takes the escape hatch
        // and returns IMMEDIATELY without parking.
        ByteBuffer second = allocator.allocate(1, group);
        Assert.assertEquals(1, second.capacity());

        // EVIDENCE: usage now exceeds LIMIT - the hard cap was overshot.
        Assert.assertEquals(LIMIT + 1, pool.onHeap.used());
        Assert.assertTrue("expected pool usage to exceed the configured limit via the escape hatch",
                           pool.onHeap.used() > LIMIT);
    }
}
