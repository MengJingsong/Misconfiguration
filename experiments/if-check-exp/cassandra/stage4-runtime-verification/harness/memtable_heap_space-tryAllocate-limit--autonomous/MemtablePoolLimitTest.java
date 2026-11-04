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
 * Harness for the short-path stage-4 unit tier of
 * memtable_heap_space-tryAllocate-limit (B2a-B2e). Not upstream; drives
 * SlabPool/MemtableAllocator directly, mirroring NativeAllocatorTest, to
 * exercise MemtablePool.SubPool.tryAllocate's hard limit (B2c scenario 1)
 * and the isBlocking() bypass at MemtablePool.java:177-185 (B2c scenario 2).
 */
public class MemtablePoolLimitTest
{
    private ExecutorService exec;
    private OpOrder order;
    private OpOrder.Group group;
    private SlabPool pool;
    private SlabAllocator allocator;

    @Before
    public void setUp()
    {
        exec = Executors.newFixedThreadPool(2);
        order = new OpOrder();
        group = order.start();
    }

    @After
    public void tearDown() throws Exception
    {
        exec.shutdownNow();
        if (pool != null)
            pool.shutdownAndWait(5, TimeUnit.SECONDS);
    }

    @Test
    public void testHardLimitBlocks() throws Exception
    {
        pool = new SlabPool(100, 0, 0.75f, () -> ImmediateFuture.success(true));
        allocator = (SlabAllocator) pool.newAllocator("t");

        allocator.allocate(60, group);
        System.out.println("[testHardLimitBlocks] after allocate(60): used=" + pool.onHeap.used());
        Assert.assertEquals(60, pool.onHeap.used());

        Future<?> blocked = exec.submit(() -> { allocator.allocate(60, group); return null; });
        boolean timedOut = false;
        try
        {
            blocked.get(200, TimeUnit.MILLISECONDS);
        }
        catch (TimeoutException e)
        {
            timedOut = true;
        }
        System.out.println("[testHardLimitBlocks] second allocate(60) timed out after 200ms: " + timedOut
                            + ", used while blocked=" + pool.onHeap.used());
        Assert.assertTrue("second allocate(60) should still be blocked (60+60=120>100)", timedOut);
        Assert.assertEquals(60, pool.onHeap.used());

        allocator.onHeap().released(60);

        blocked.get(5, TimeUnit.SECONDS); // must now complete
        System.out.println("[testHardLimitBlocks] after release(60)+unblock: used=" + pool.onHeap.used());
        Assert.assertEquals(60, pool.onHeap.used());
    }

    @Test
    public void testDiscardingOvershoots() throws Exception
    {
        pool = new SlabPool(100, 0, 0.75f, () -> ImmediateFuture.success(true));
        allocator = (SlabAllocator) pool.newAllocator("t");

        allocator.allocate(90, group);
        System.out.println("[testDiscardingOvershoots] after allocate(90): used=" + pool.onHeap.used());
        Assert.assertEquals(90, pool.onHeap.used());

        allocator.setDiscarding();

        OpOrder.Barrier barrier = order.newBarrier();
        barrier.issue();
        barrier.markBlocking();
        Assert.assertTrue("group must be isBlocking() before the next allocate", group.isBlocking());

        Future<?> f = exec.submit(() -> { allocator.allocate(30, group); return null; });
        f.get(1, TimeUnit.SECONDS); // must return promptly: no block expected on this path

        long used = pool.onHeap.used();
        System.out.println("[testDiscardingOvershoots] after allocate(30) while isBlocking(): used=" + used
                            + ", limit=" + pool.onHeap.limit);
        Assert.assertEquals(120, used);
        Assert.assertTrue("used() must exceed limit via the bypass", used > pool.onHeap.limit);
    }
}
