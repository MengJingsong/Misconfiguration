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
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.memtable.AbstractAllocatorMemtable;
import org.apache.cassandra.utils.concurrent.ImmediateFuture;
import org.apache.cassandra.utils.concurrent.OpOrder;

/**
 * Stage-4 harness, unit tier B2 of memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous
 * (B2e steps 1-2 and the B2h controls, as amended 2026-10-24). Records readings; never fails on a mismatch.
 * Output: one "STAGE4 ..." line per reading, to stdout and to -Dstage4.out.
 */
public class MemtableHeapCapTest
{
    static final int SIZE = 1024;

    @BeforeClass
    public static void init()
    {
        DatabaseDescriptor.daemonInitialization();
    }

    static synchronized void out(String s)
    {
        String line = "STAGE4 " + s;
        System.out.println(line);
        String f = System.getProperty("stage4.out");
        if (f != null)
            try (FileWriter w = new FileWriter(f, true)) { w.write(line + "\n"); }
            catch (IOException e) { throw new RuntimeException(e); }
    }

    static class Writer extends Thread
    {
        final SlabAllocator allocator; final OpOrder.Group group; final long calls; final MemtablePool pool;
        final AtomicLong done = new AtomicLong(), maxUsed = new AtomicLong();
        volatile String end = "running";
        Writer(SlabAllocator a, OpOrder.Group g, long calls, MemtablePool p) { super("stage4-writer"); allocator = a; group = g; this.calls = calls; pool = p; setDaemon(true); }
        public void run()
        {
            try
            {
                for (long i = 0; i < calls; i++)
                {
                    allocator.allocate(SIZE, group);
                    done.incrementAndGet();
                    maxUsed.accumulateAndGet(pool.onHeap.used(), Math::max);
                }
                end = "finished";
            }
            catch (Throwable t) { end = "stopped:" + t.getClass().getSimpleName(); }
        }
    }

    /** samples used() every 10 ms for ms milliseconds; returns the max seen by the test thread */
    static long sample(MemtablePool pool, long ms) throws InterruptedException
    {
        long max = 0, endAt = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(ms);
        while (System.nanoTime() < endAt)
        {
            max = Math.max(max, pool.onHeap.used());
            Thread.sleep(10);
        }
        return Math.max(max, pool.onHeap.used());
    }

    static void scenario(String label, long limit, long calls, boolean blocking, boolean release) throws Exception
    {
        MemtablePool pool = AbstractAllocatorMemtable.createMemtableAllocatorPoolInternal(Config.MemtableAllocationType.heap_buffers,
                                                                                           limit, 0, 0.5f, () -> ImmediateFuture.success(false));
        SlabAllocator allocator = (SlabAllocator) pool.newAllocator("t");
        OpOrder order = new OpOrder();
        OpOrder.Group group = order.start();
        if (blocking)
        {
            OpOrder.Barrier b = order.newBarrier();
            b.issue();
            b.markBlocking();
        }
        out(label + " setup pool=" + pool.getClass().getSimpleName() + " limit=" + pool.onHeap.limit + " calls=" + calls
            + " size=" + SIZE + " groupBlocking=" + group.isBlocking());
        Writer w = new Writer(allocator, group, calls, pool);
        w.start();
        long max1 = sample(pool, 2000);
        out(label + " t2s done=" + w.done.get() + " used=" + pool.onHeap.used() + " maxUsedSampled=" + max1
            + " maxUsedWriter=" + w.maxUsed.get() + " state=" + w.getState() + " end=" + w.end
            + " usedOverLimit=" + (pool.onHeap.used() > limit));
        if (release)
        {
            long before = w.done.get();
            pool.onHeap.released(limit / 2);
            out(label + " released=" + (limit / 2) + " usedAfterRelease=" + pool.onHeap.used());
            long max2 = sample(pool, 2000);
            out(label + " t4s done=" + w.done.get() + " resumedCalls=" + (w.done.get() - before) + " used=" + pool.onHeap.used()
                + " maxUsedSampled=" + max2 + " state=" + w.getState() + " end=" + w.end);
        }
        if (!blocking && limit == Long.MAX_VALUE || blocking)
        {
            w.join(10000);
            out(label + " final done=" + w.done.get() + " used=" + pool.onHeap.used() + " end=" + w.end + " alive=" + w.isAlive());
        }
        w.interrupt();
        w.join(5000);
        out(label + " teardown writerAlive=" + w.isAlive() + " end=" + w.end);
        group.close();
        pool.shutdownAndWait(10, TimeUnit.SECONDS);
    }

    @Test
    public void limits() throws Exception
    {
        for (long mib : new long[]{ 1, 4, 16 })
        {
            long limit = mib << 20;
            scenario("limit" + mib + "MiB", limit, 4 * limit / SIZE, false, true);
        }
    }

    @Test
    public void controlNoLimit() throws Exception
    {
        scenario("ctlMaxLimit", Long.MAX_VALUE, 4 * (16L << 20) / SIZE, false, false);
    }

    @Test
    public void controlBlockingGroup() throws Exception
    {
        scenario("ctlBlocking1MiB", 1L << 20, 4 * (1L << 20) / SIZE, true, false);
    }
}
