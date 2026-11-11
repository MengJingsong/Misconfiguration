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
import java.util.concurrent.locks.LockSupport;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.Config.MemtableAllocationType;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.memtable.AbstractAllocatorMemtable;
import org.apache.cassandra.utils.concurrent.ImmediateFuture;
import org.apache.cassandra.utils.concurrent.OpOrder;

/**
 * Stage-4 harness, unit tier B2 of memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous
 * (B2b-B2e and B2h (i), as amended 2026-10-24). Records readings; never fails on a mismatch.
 * Output: one "STAGE4 ..." line per reading, to stdout and to -Dstage4.out.
 */
public class CleanupThresholdTest
{
    static final int SIZE = 4096;
    static final long LIMIT = 16L << 20;          // B2b: 16 MiB heap pool
    static final long CALLS = 8192;               // B2c amended: 32 MiB offered, twice the limit
    static final long PARK_NS = 50_000;           // B2c amended: 50 us between calls

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
        final SlabAllocator allocator; final OpOrder.Group group; final MemtablePool pool;
        final AtomicLong done = new AtomicLong();
        volatile String end = "running";
        Writer(SlabAllocator a, OpOrder.Group g, MemtablePool p) { super("stage4-writer"); allocator = a; group = g; pool = p; setDaemon(true); }
        public void run()
        {
            try
            {
                for (long i = 0; i < CALLS; i++)
                {
                    allocator.allocate(SIZE, group);
                    done.incrementAndGet();
                    LockSupport.parkNanos(PARK_NS);
                    if (Thread.currentThread().isInterrupted()) throw new InterruptedException();
                }
                end = "finished";
            }
            catch (Throwable t) { end = "stopped:" + t.getClass().getSimpleName(); }
        }
    }

    static void scenario(String label, long limit, float t) throws Exception
    {
        AtomicLong invocations = new AtomicLong();
        AtomicLong firstUsed = new AtomicLong(-1);
        AtomicLong firstDone = new AtomicLong(-1);
        final MemtablePool[] holder = new MemtablePool[1];
        final Writer[] wh = new Writer[1];
        MemtablePool pool = AbstractAllocatorMemtable.createMemtableAllocatorPoolInternal(MemtableAllocationType.heap_buffers, limit, 0, t, () -> {
            if (invocations.incrementAndGet() == 1)
            {
                firstUsed.set(holder[0].onHeap.used());
                firstDone.set(wh[0] == null ? -1 : wh[0].done.get());
            }
            return ImmediateFuture.success(false);
        });
        holder[0] = pool;
        long T = (long) (pool.onHeap.limit * pool.onHeap.cleanThreshold);   // as MemtablePool.java:139 (reclaiming = 0)
        SlabAllocator allocator = (SlabAllocator) pool.newAllocator("t");
        OpOrder.Group group = new OpOrder().start();
        out(label + " setup t=" + t + " pool=" + pool.getClass().getSimpleName() + " onHeap.limit=" + pool.onHeap.limit
            + " onHeap.cleanThreshold=" + pool.onHeap.cleanThreshold + " T=" + T + " calls=" + CALLS + " size=" + SIZE
            + " parkNs=" + PARK_NS + " groupBlocking=" + group.isBlocking());
        Writer w = new Writer(allocator, group, pool);
        wh[0] = w;
        w.start();
        Thread.sleep(3000);
        long fu = firstUsed.get();
        out(label + " t3s invocations=" + invocations.get() + " firstInvocationUsed=" + fu + " firstInvocationWriterDone=" + firstDone.get()
            + " done=" + w.done.get() + " used=" + pool.onHeap.used() + " offHeap.used=" + pool.offHeap.used()
            + " state=" + w.getState() + " end=" + w.end
            + " firstMinusT=" + (fu < 0 ? "na" : String.valueOf(fu - T)));
        w.interrupt();
        w.join(5000);
        out(label + " teardown writerAlive=" + w.isAlive() + " end=" + w.end + " done=" + w.done.get() + " invocations=" + invocations.get());
        group.close();
        pool.shutdownAndWait(10, TimeUnit.SECONDS);
    }

    @Test
    public void scenarios() throws Exception
    {
        for (float t : new float[]{ 0.11f, 0.33f, 0.5f, 0.9f })
            scenario("t=" + t, LIMIT, t);
    }

    @Test
    public void control() throws Exception
    {
        scenario("ctlMax/t=0.99", Long.MAX_VALUE, 0.99f);
    }
}
