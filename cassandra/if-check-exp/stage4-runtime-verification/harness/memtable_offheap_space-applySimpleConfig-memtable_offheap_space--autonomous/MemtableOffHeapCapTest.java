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

import org.apache.cassandra.config.Config.MemtableAllocationType;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.memtable.AbstractAllocatorMemtable;
import org.apache.cassandra.utils.concurrent.ImmediateFuture;
import org.apache.cassandra.utils.concurrent.OpOrder;

/**
 * Stage-4 harness, unit tier B2 of memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous
 * (B2b-B2e and the B2h controls, as amended 2026-10-24). Records readings; never fails on a mismatch.
 * Output: one "STAGE4 ..." line per reading, to stdout and to -Dstage4.out.
 */
public class MemtableOffHeapCapTest
{
    static final int SIZE = 1024;
    static final long CALLS = (32L << 20) / SIZE;   // 32,768 calls = 32 MiB
    static final long HEAP_LIMIT = 64L << 20;      // B2b: 64 MiB on-heap

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
        final MemtableAllocator allocator; final OpOrder.Group group; final MemtablePool pool;
        final AtomicLong done = new AtomicLong(), maxOff = new AtomicLong(), maxOn = new AtomicLong();
        volatile String end = "running";
        Writer(MemtableAllocator a, OpOrder.Group g, MemtablePool p) { super("stage4-writer"); allocator = a; group = g; pool = p; setDaemon(true); }
        public void run()
        {
            try
            {
                for (long i = 0; i < CALLS; i++)
                {
                    if (allocator instanceof SlabAllocator)
                        ((SlabAllocator) allocator).allocate(SIZE, group);
                    else
                        ((NativeAllocator) allocator).allocate(SIZE, group);
                    done.incrementAndGet();
                    maxOff.accumulateAndGet(pool.offHeap.used(), Math::max);
                    maxOn.accumulateAndGet(pool.onHeap.used(), Math::max);
                }
                end = "finished";
            }
            catch (Throwable t) { end = "stopped:" + t.getClass().getSimpleName(); }
        }
    }

    static void scenario(String label, MemtableAllocationType type, long offHeapLimit) throws Exception
    {
        MemtablePool pool = AbstractAllocatorMemtable.createMemtableAllocatorPoolInternal(type, HEAP_LIMIT, offHeapLimit, 0.5f,
                                                                                           () -> ImmediateFuture.success(false));
        MemtableAllocator allocator = pool.newAllocator("t");
        OpOrder.Group group = new OpOrder().start();
        out(label + " setup type=" + type + " pool=" + pool.getClass().getSimpleName() + " allocator=" + allocator.getClass().getSimpleName()
            + " onHeap.limit=" + pool.onHeap.limit + " offHeap.limit=" + pool.offHeap.limit + " calls=" + CALLS + " size=" + SIZE
            + " groupBlocking=" + group.isBlocking());
        Writer w = new Writer(allocator, group, pool);
        w.start();
        Thread.sleep(2000);
        out(label + " t2s done=" + w.done.get() + " offHeap.used=" + pool.offHeap.used() + " onHeap.used=" + pool.onHeap.used()
            + " maxOffWriter=" + w.maxOff.get() + " maxOnWriter=" + w.maxOn.get() + " state=" + w.getState() + " end=" + w.end
            + " offOverLimit=" + (pool.offHeap.used() > offHeapLimit));
        w.interrupt();
        w.join(5000);
        out(label + " teardown writerAlive=" + w.isAlive() + " end=" + w.end + " done=" + w.done.get());
        group.close();
        pool.shutdownAndWait(10, TimeUnit.SECONDS);
    }

    @Test
    public void scenarios() throws Exception
    {
        for (MemtableAllocationType t : new MemtableAllocationType[]{ MemtableAllocationType.offheap_buffers, MemtableAllocationType.offheap_objects })
            for (long mib : new long[]{ 1, 8, 0 })
                scenario(t + "/" + mib + "MiB", t, mib << 20);
    }

    @Test
    public void controls() throws Exception
    {
        scenario("ctlMax/offheap_buffers", MemtableAllocationType.offheap_buffers, Long.MAX_VALUE);
        scenario("ctlMax/offheap_objects", MemtableAllocationType.offheap_objects, Long.MAX_VALUE);
        scenario("ctlHeapBuffers/1MiB", MemtableAllocationType.heap_buffers, 1L << 20);
    }
}
