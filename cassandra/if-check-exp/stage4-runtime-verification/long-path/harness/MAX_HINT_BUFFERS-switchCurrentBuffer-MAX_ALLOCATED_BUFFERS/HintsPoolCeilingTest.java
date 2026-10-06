/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.apache.cassandra.hints;

import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.Iterator;
import java.util.Queue;
import java.util.UUID;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import com.google.common.collect.ImmutableList;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.net.MessagingService;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

/**
 * Unit tier of the stage-4 run for the if-check-exp case
 * MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS (case file §9e).
 *
 * Drives a HintsBufferPool of real direct buffers until a writer waits at the
 * capacity check (HintsBufferPool.switchCurrentBuffer(), the take() at line 118),
 * and checks that:
 *   1. the pool then holds exactly n = MAX_ALLOCATED_BUFFERS buffers, and the JVM's
 *      direct memory is up by n x bufferSize;
 *   2. nothing grows while the writer waits;
 *   3. recycling one buffer releases the writer without creating another;
 *   4. every hint written is found in exactly one buffer.
 *
 * Settings, all system properties (pass them with -Dtest.jvm.args):
 *   cassandra.MAX_HINT_BUFFERS  n, the knob under test (2 or more; at 1 the writer waits forever)
 *   stage4.hints.bufferSize     bytes per buffer, default 1 MiB
 *   stage4.unit.out             optional file that also receives every STAGE4 line
 *
 * The package is org.apache.cassandra.hints because HintsBufferPool, HintsBuffer and
 * HintsBufferTest's helpers are package-private. Not upstream; run it from a local clone
 * of cassandra-5.0.9, never the shared one.
 */
public class HintsPoolCeilingTest
{
    private static final UUID HOST = UUID.randomUUID();
    private static final long PARK_TIMEOUT_MS = 60_000;
    private static BufferPoolMXBean DIRECT;
    private static long lastCount = -1, lastUsed = -1;

    @BeforeClass
    public static void defineSchema()
    {
        // HintsBufferTest.createHint() needs the schema, as HintsBufferPoolTest's @BeforeClass does.
        HintsBufferTest.defineSchema();
    }

    @Test
    public void poolHoldsExactlyNBuffersWhileAWriterWaits() throws Exception
    {
        int n = HintsBufferPool.MAX_ALLOCATED_BUFFERS;
        int bufferSize = Integer.getInteger("stage4.hints.bufferSize", 1 << 20);

        String raw = System.getProperty("cassandra.MAX_HINT_BUFFERS");
        assertEquals("cassandra.MAX_HINT_BUFFERS took effect", raw == null ? 3 : Integer.parseInt(raw), n);
        assertTrue("n must be 2 or more: at n = 1 the writer waits forever (case 9b), n = " + n, n >= 2);

        BufferPoolMXBean direct = null;
        for (BufferPoolMXBean bean : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (bean.getName().equals("direct"))
                direct = bean;
        assertNotNull("direct buffer pool bean", direct);
        DIRECT = direct;
        Field allocatedField = HintsBufferPool.class.getDeclaredField("allocatedBuffers");
        allocatedField.setAccessible(true);

        // Flush callback that queues buffers without recycling them, as HintsBufferPoolTest does.
        Queue<HintsBuffer> queued = new ConcurrentLinkedQueue<>();
        HintsBufferPool pool = new HintsBufferPool(bufferSize, (buffer, p) -> queued.offer(buffer));

        // Enough hints to need more than n + 2 buffers, so the writer must wait and then keep going.
        int entrySize = (int) Hint.serializer.serializedSize(HintsBufferTest.createHint(0, 0), MessagingService.current_version)
                        + HintsBuffer.ENTRY_OVERHEAD_SIZE;
        int total = (int) (((long) (n + 3) * bufferSize) / entrySize) + 1;

        // Warm the writer thread up, then take the baseline. The first Mutation.serializedSize() on a
        // thread creates a per-thread scratch DataOutputBuffer with a 128-byte direct buffer
        // (Mutation.java:453, a netty FastThreadLocal); left inside the deltas it adds 1 to Count and
        // 128 to MemoryUsed (found at the instrument check, 2026-09-30). The output path is warmed up
        // the same way, and a GC settles buffers the cleaner would otherwise free mid-test.
        Writer writer = new Writer(pool, total);
        writer.start();
        assertTrue("writer warmed up", writer.warmed.await(PARK_TIMEOUT_MS, TimeUnit.MILLISECONDS));
        emit("unit start");
        System.gc();
        Thread.sleep(500);
        long count0 = direct.getCount();
        long used0 = direct.getMemoryUsed();
        emit("unit directBaseline count=" + count0 + " used=" + used0);
        writer.go.countDown();

        // 1. The writer waits, and the pool holds exactly n buffers.
        String frame = awaitParked(writer, -1);
        Snapshot s1 = new Snapshot(allocatedField, pool, direct, count0, used0, queued, writer);
        emit("unit n=" + n + " bufferSize=" + bufferSize + " hintsToWrite=" + total + " entrySize=" + entrySize);
        emit("unit parkedAt=" + frame);
        emit("unit atWait " + s1);
        assertEquals("allocatedBuffers when the writer waits", n, s1.allocated);
        assertEquals("buffers handed to the flush callback (the n-th is handed over only after the wait)", n - 1, s1.queued);
        assertEquals("direct buffer Count delta", n, s1.countDelta);
        assertEquals("direct MemoryUsed delta", (long) n * bufferSize, s1.usedDelta);

        // 2. Nothing grows while the writer waits.
        Thread.sleep(2000);
        Snapshot s2 = new Snapshot(allocatedField, pool, direct, count0, used0, queued, writer);
        emit("unit after2s " + s2);
        assertTrue("writer is still waiting after 2 s", isParked(writer) != null);
        assertEquals("allocatedBuffers after 2 s", s1.allocated, s2.allocated);
        assertEquals("Count delta after 2 s", s1.countDelta, s2.countDelta);
        assertEquals("MemoryUsed delta after 2 s", s1.usedDelta, s2.usedDelta);
        assertEquals("hints written after 2 s", s1.written, s2.written);

        // 3. Recycling one buffer releases the writer, and it waits again without a new buffer.
        int counted = 0;
        HintsBuffer first = queued.poll();
        assertNotNull("a queued buffer to recycle", first);
        counted += countHints(first);
        pool.offer(first.recycle());
        awaitParked(writer, s2.written);
        Snapshot s3 = new Snapshot(allocatedField, pool, direct, count0, used0, queued, writer);
        emit("unit afterOneRecycle " + s3);
        assertTrue("writer made progress after the recycle", s3.written > s2.written);
        assertEquals("allocatedBuffers after one recycle", n, s3.allocated);
        assertEquals("Count delta after one recycle", n, s3.countDelta);
        assertEquals("MemoryUsed delta after one recycle", (long) n * bufferSize, s3.usedDelta);
        assertEquals("buffers queued after one recycle (one taken, one handed over)", n - 1, s3.queued);

        // 4. Recycle the rest and let the writer finish; every hint is in exactly one buffer.
        while (writer.isAlive())
        {
            HintsBuffer buffer = queued.poll();
            if (buffer == null)
            {
                Thread.sleep(1);
                continue;
            }
            counted += countHints(buffer);
            pool.offer(buffer.recycle());
        }
        writer.join();
        assertNull("writer failure: " + writer.failure, writer.failure);
        HintsBuffer buffer;
        while ((buffer = queued.poll()) != null)
            counted += countHints(buffer);
        counted += countHints(pool.currentBuffer());

        Snapshot s4 = new Snapshot(allocatedField, pool, direct, count0, used0, queued, writer);
        emit("unit atEnd " + s4 + " hintsCounted=" + counted);
        assertEquals("hints written", total, writer.written.get());
        assertEquals("hints found across all buffers", total, counted);
        assertEquals("allocatedBuffers at the end", n, s4.allocated);
        assertEquals("Count delta at the end", n, s4.countDelta);
        assertEquals("MemoryUsed delta at the end", (long) n * bufferSize, s4.usedDelta);
        emit("unit PASS n=" + n + " bufferSize=" + bufferSize);
    }

    /** Hints are written one at a time until the pool makes the writer wait. */
    private static final class Writer extends Thread
    {
        final HintsBufferPool pool;
        final int total;
        final AtomicInteger written = new AtomicInteger();
        final CountDownLatch warmed = new CountDownLatch(1);
        final CountDownLatch go = new CountDownLatch(1);
        volatile Throwable failure;

        Writer(HintsBufferPool pool, int total)
        {
            super("stage4-hints-writer");
            setDaemon(true);
            this.pool = pool;
            this.total = total;
        }

        public void run()
        {
            try
            {
                try
                {
                    Hint.serializer.serializedSize(HintsBufferTest.createHint(0, 0), MessagingService.current_version);
                }
                finally
                {
                    warmed.countDown();
                }
                go.await();
                for (int i = 0; i < total; i++)
                {
                    pool.write(ImmutableList.of(HOST), HintsBufferTest.createHint(i, i));
                    written.incrementAndGet();
                }
            }
            catch (Throwable t)
            {
                failure = t;
            }
        }
    }

    private static final class Snapshot
    {
        final int allocated, queued, written;
        final long countDelta, usedDelta;

        Snapshot(Field allocatedField, HintsBufferPool pool, BufferPoolMXBean direct, long count0, long used0,
                 Queue<HintsBuffer> queued, Writer writer) throws Exception
        {
            allocated = allocatedField.getInt(pool);
            this.queued = queued.size();
            written = writer.written.get();
            countDelta = direct.getCount() - count0;
            usedDelta = direct.getMemoryUsed() - used0;
        }

        public String toString()
        {
            return "allocatedBuffers=" + allocated + " queued=" + queued + " written=" + written
                   + " countDelta=" + countDelta + " usedDelta=" + usedDelta;
        }
    }

    /** The writer's stack if it is parked in take() under switchCurrentBuffer(), else null. */
    private static String isParked(Thread writer)
    {
        boolean inSwitch = false;
        String take = null;
        for (StackTraceElement e : writer.getStackTrace())
        {
            if (e.getMethodName().equals("take") && e.getClassName().startsWith("java.util.concurrent."))
                take = e.toString();
            if (e.getClassName().equals(HintsBufferPool.class.getName()) && e.getMethodName().equals("switchCurrentBuffer"))
                inSwitch = true;
        }
        return inSwitch && take != null ? take : null;
    }

    /**
     * Waits for the writer to be parked in take(). With afterWritten >= 0 it also requires the
     * writer to have made progress since, so a thread that has not yet woken from the previous
     * wait is not mistaken for a new one. Returns the parked frame.
     */
    private static String awaitParked(Writer writer, int afterWritten) throws InterruptedException
    {
        long deadline = System.currentTimeMillis() + PARK_TIMEOUT_MS;
        while (System.currentTimeMillis() < deadline)
        {
            logDirectChange(writer);
            if (!writer.isAlive())
                fail("writer finished without waiting at the cap: wrote " + writer.written.get() + " hints, failure " + writer.failure);
            String frame = isParked(writer);
            if (frame != null && writer.written.get() > afterWritten)
            {
                // Stable for a moment, so a thread still waking up is not caught mid-way.
                int before = writer.written.get();
                Thread.sleep(300);
                if (isParked(writer) != null && writer.written.get() == before)
                    return frame + " (HintsBufferPool.switchCurrentBuffer)";
            }
            Thread.sleep(20);
        }
        fail("writer did not wait at the cap within " + PARK_TIMEOUT_MS + " ms; wrote " + writer.written.get() + " hints");
        return null;
    }

    /** Timeline: one line whenever the JVM's direct buffer Count or MemoryUsed changes while we wait. */
    private static void logDirectChange(Writer writer)
    {
        long count = DIRECT.getCount(), used = DIRECT.getMemoryUsed();
        if (count != lastCount || used != lastUsed)
        {
            lastCount = count;
            lastUsed = used;
            try { emit("unit directChange count=" + count + " used=" + used + " written=" + writer.written.get()); }
            catch (java.io.IOException e) { throw new RuntimeException(e); }
        }
    }

    /** Counts the hints in a buffer for HOST. Call before recycle(), which clears the offsets. */
    private static int countHints(HintsBuffer buffer)
    {
        buffer.waitForModifications();
        Iterator<ByteBuffer> hints = buffer.consumingHintsIterator(HOST);
        int count = 0;
        while (hints.hasNext())
        {
            hints.next();
            count++;
        }
        return count;
    }

    /**
     * Prints a line, and appends it to stage4.unit.out if set. The file is written with java.io:
     * java.nio.file.Files.write goes through a channel that caches a temporary direct buffer of the
     * line's size, which would add one to the direct buffer Count and about 128 bytes to
     * MemoryUsed, the very readings this test takes (found at the instrument check, 2026-09-30).
     */
    private static void emit(String line) throws java.io.IOException
    {
        System.out.println("STAGE4 " + line);
        String out = System.getProperty("stage4.unit.out");
        if (out != null)
        {
            try (java.io.FileWriter writer = new java.io.FileWriter(out, true))
            {
                writer.write(line + "\n");
            }
        }
    }
}
