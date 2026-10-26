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

import java.io.FileWriter;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import com.google.common.collect.ImmutableList;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.gms.FailureDetector;
import org.apache.cassandra.net.MessagingService;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.Schema;
import org.apache.cassandra.schema.TableMetadata;

import static org.junit.Assert.assertTrue;
import static org.apache.cassandra.utils.ByteBufferUtil.bytes;

/**
 * Unit tier (B2) of the stage-4 run for the if-check-exp case
 * hints-HintsBuffer-put-slabCapacity--autonomous. Not upstream; package org.apache.cassandra.hints because
 * HintsBuffer and HintsBufferPool are package-private. Run from a local copy of cassandra-5.0.9, never the shared one.
 *
 * One @Test runs five scenarios; each prints "STAGE4 check <name> ok|MISMATCH <detail>" and the JUnit test fails at the
 * end if any is a MISMATCH. The relations come from the case file (B2f, as amended 2026-10-26); a MISMATCH is a reading.
 *   boundary   HintsBuffer.allocate(S/2-12) accepted, S/2-11 and S/2+1 rejected "too large" (S = 1, 4, 32 MiB)
 *   rotation   a HintsBufferPool (S = 4 MiB) driven by 8 writers through 200 ms recycling flushes: allocatedBuffers and the
 *              JVM direct-buffer pool never pass n x S, many times n x S bytes go through
 *   stall      flushes never return a buffer: the writer parks in take(), allocatedBuffers == n, direct delta == n x S, flat
 *   derive     a real HintsService built with max_mutation_size m has bufferSize max(2m, 32 MiB); its pool takes a hint at
 *              the slab/2 - 12 boundary and rejects one byte more
 * Settings: -Dcassandra.MAX_HINT_BUFFERS=n (one forked JVM per value); -Dstage4.out=<file> receives every STAGE4 line.
 */
public class HintsSlabCapTest
{
    private static final String KEYSPACE = "hints_slab_cap";
    private static final String TABLE = "tbl";
    private static final long MIB = 1 << 20;
    private static final UUID HOST = UUID.randomUUID();
    private static final List<String> mismatches = new ArrayList<>();
    private static BufferPoolMXBean direct;

    @BeforeClass
    public static void defineSchema()
    {
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KEYSPACE, KeyspaceParams.simple(1), SchemaLoader.standardCFMD(KEYSPACE, TABLE));
    }

    @Test
    public void slabCap() throws Exception
    {
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct"))
                direct = b;
        int n = HintsBufferPool.MAX_ALLOCATED_BUFFERS;
        String raw = System.getProperty("cassandra.MAX_HINT_BUFFERS");
        check("knob-took-effect", n == (raw == null ? 3 : Integer.parseInt(raw)), "n=" + n + " property=" + raw);
        emit("unit start n=" + n + " java=" + System.getProperty("java.version") + " MaxDirectMemorySize-arg="
             + ManagementFactory.getRuntimeMXBean().getInputArguments());
        String only = System.getProperty("stage4.only", "");
        if (only.equals("derive"))
            derive();
        else
        {
            boundary();
            if (n >= 2)
                rotation(n);
            stall(n);
        }
        emit("unit summary mismatches=" + mismatches.size() + " " + mismatches);
        assertTrue("MISMATCH: " + mismatches, mismatches.isEmpty());
    }

    // ---- boundary --------------------------------------------------------------------------------------------------
    private void boundary()
    {
        for (long s : new long[]{ 1 * MIB, 4 * MIB, 32 * MIB })
        {
            int S = (int) s;
            HintsBuffer buffer = HintsBuffer.create(S);
            String r1 = tryAllocate(buffer, S / 2 - 12);
            String r2 = tryAllocate(buffer, S / 2 - 11);
            String r3 = tryAllocate(buffer, S / 2 + 1);
            check("boundary-S" + (S >> 20) + "MiB", r1.equals("accepted") && r2.startsWith("rejected") && r3.startsWith("rejected"),
                  "S=" + S + " hint=S/2-12:" + r1 + " | S/2-11:" + r2 + " | S/2+1:" + r3);
            check("boundary-message-S" + (S >> 20) + "MiB", r2.contains("Hint of " + (S / 2 - 11) + " bytes is too large - the maximum size is " + (S / 2)), r2);
            buffer.free();
        }
    }

    private static String tryAllocate(HintsBuffer b, int hintSize)
    {
        try (HintsBuffer.Allocation a = b.allocate(hintSize))
        {
            return a == null ? "null" : "accepted";
        }
        catch (IllegalArgumentException e)
        {
            return "rejected(" + e.getMessage() + ")";
        }
    }

    // ---- rotation --------------------------------------------------------------------------------------------------
    private void rotation(int n) throws Exception
    {
        final int S = (int) (4 * MIB);
        settle();
        // writer threads warmed up (the per-thread 128-byte scratch buffer of Mutation.serializedSize) before the baseline
        final int threads = 8;
        final Hint sample = hint(0, S / 4 - 4096);
        final int hintSize = (int) Hint.serializer.serializedSize(sample, MessagingService.current_version);
        final long entry = hintSize + HintsBuffer.ENTRY_OVERHEAD_SIZE;
        final int total = (int) ((20L * S) / entry) + 1;                      // 20 x S bytes of entries, rounded up
        final ExecutorService flusher = Executors.newSingleThreadExecutor(r -> { Thread t = new Thread(r, "stage4-flusher"); t.setDaemon(true); return t; });
        final AtomicInteger flushes = new AtomicInteger(), submitted = new AtomicInteger();
        final ConcurrentLinkedQueue<Integer> capsSeen = new ConcurrentLinkedQueue<>();
        final HintsBufferPool[] holder = new HintsBufferPool[1];
        final HintsBufferPool pool = new HintsBufferPool(S, (buffer, p) -> {
            submitted.incrementAndGet();
            flusher.submit(() -> {
                try
                {
                    capsSeen.add(buffer.capacity());
                    buffer.waitForModifications();
                    Thread.sleep(200);
                }
                catch (InterruptedException e) { return; }
                flushes.incrementAndGet();
                p.offer(buffer.recycle());
            });
        });
        holder[0] = pool;
        Field allocated = HintsBufferPool.class.getDeclaredField("allocatedBuffers");
        allocated.setAccessible(true);

        final CountDownLatch warmed = new CountDownLatch(threads), go = new CountDownLatch(1);
        final AtomicInteger next = new AtomicInteger(), written = new AtomicInteger();
        final AtomicLong failures = new AtomicLong();
        List<Thread> ws = new ArrayList<>();
        for (int t = 0; t < threads; t++)
        {
            Thread w = new Thread(() -> {
                try
                {
                    Hint.serializer.serializedSize(hint(0, 16), MessagingService.current_version);   // warm-up
                    warmed.countDown();
                    go.await();
                    int i;
                    while ((i = next.getAndIncrement()) < total)
                    {
                        pool.write(ImmutableList.of(HOST), hint(i, S / 4 - 4096));
                        written.incrementAndGet();
                    }
                }
                catch (Throwable e) { failures.incrementAndGet(); emit("unit writer-failure " + e); }
            }, "stage4-writer-" + t);
            w.setDaemon(true);
            ws.add(w);
            w.start();
        }
        warmed.await();
        settle();
        long count0 = direct.getCount(), used0 = direct.getMemoryUsed();
        emit("unit rotation baseline count=" + count0 + " used=" + used0 + " n=" + n + " S=" + S + " hintSize=" + hintSize
             + " entry=" + entry + " hintsToWrite=" + total + " bytesThrough=" + total * entry + " (" + (total * entry) / (double) S + " x S)");
        go.countDown();
        long maxUsedDelta = 0, maxCountDelta = 0;
        int maxAllocated = 0;
        long last = System.currentTimeMillis();
        while (ws.stream().anyMatch(Thread::isAlive))
        {
            maxUsedDelta = Math.max(maxUsedDelta, direct.getMemoryUsed() - used0);
            maxCountDelta = Math.max(maxCountDelta, direct.getCount() - count0);
            maxAllocated = Math.max(maxAllocated, allocated.getInt(pool));
            if (System.currentTimeMillis() - last > 1000)
            {
                last = System.currentTimeMillis();
                emit("unit rotation progress written=" + written.get() + " flushes=" + flushes.get() + " allocated=" + allocated.getInt(pool) + " usedDelta=" + (direct.getMemoryUsed() - used0));
            }
            Thread.sleep(2);
        }
        maxUsedDelta = Math.max(maxUsedDelta, direct.getMemoryUsed() - used0);
        long endUsed = direct.getMemoryUsed() - used0, endCount = direct.getCount() - count0;
        int endAllocated = allocated.getInt(pool);
        emit("unit rotation end written=" + written.get() + " flushes=" + flushes.get() + " allocated=" + endAllocated + " maxAllocated=" + maxAllocated
             + " usedDelta=" + endUsed + " maxUsedDelta=" + maxUsedDelta + " countDelta=" + endCount + " maxCountDelta=" + maxCountDelta
             + " capsSeen=" + new java.util.TreeSet<>(capsSeen));
        long tol = 64 * 1024;
        check("rotation-all-written", failures.get() == 0 && written.get() == total, "written=" + written.get() + " of " + total + " failures=" + failures.get());
        long turnovers = (total * entry) / S - 1;       // bytes through / slab size, less one: slabs that must have been handed to the flusher
        check("rotation-many-slabs-through", submitted.get() >= turnovers && turnovers >= 19, "flush callbacks (slab rotations)=" + submitted.get() + " flushes started=" + capsSeen.size() + " completed=" + flushes.get() + " required >= " + turnovers);
        check("rotation-allocated==n", maxAllocated == n && endAllocated == n, "maxAllocated=" + maxAllocated + " end=" + endAllocated + " n=" + n);
        check("rotation-direct-delta==n*S", Math.abs(endUsed - (long) n * S) <= tol, "end=" + endUsed + " expected=" + (long) n * S + " tol=" + tol);
        check("rotation-direct-max<=n*S+tol", maxUsedDelta <= (long) n * S + tol, "max=" + maxUsedDelta + " ceiling=" + ((long) n * S + tol));
        check("rotation-all-slabs-S", capsSeen.stream().allMatch(c -> c == S), "capsSeen=" + new java.util.TreeSet<>(capsSeen));
        flusher.shutdownNow();
    }

    // ---- stall -----------------------------------------------------------------------------------------------------
    private void stall(int n) throws Exception
    {
        final int S = (int) (4 * MIB);
        settle();
        final int vlen = S / 4 - 4096;
        final ConcurrentLinkedQueue<HintsBuffer> queued = new ConcurrentLinkedQueue<>();
        final HintsBufferPool pool = new HintsBufferPool(S, (buffer, p) -> queued.add(buffer));      // never returns a buffer
        Field allocated = HintsBufferPool.class.getDeclaredField("allocatedBuffers");
        allocated.setAccessible(true);
        final CountDownLatch warmed = new CountDownLatch(1), go = new CountDownLatch(1);
        final AtomicInteger written = new AtomicInteger();
        Thread w = new Thread(() -> {
            try
            {
                Hint.serializer.serializedSize(hint(0, 16), MessagingService.current_version);
                warmed.countDown();
                go.await();
                for (int i = 0; i < 1000; i++)
                {
                    pool.write(ImmutableList.of(HOST), hint(i, vlen));
                    written.incrementAndGet();
                }
            }
            catch (Throwable e) { emit("unit stall writer ended " + e); }
        }, "stage4-stall-writer");
        w.setDaemon(true);
        w.start();
        warmed.await();
        settle();
        long count0 = direct.getCount(), used0 = direct.getMemoryUsed();
        go.countDown();
        String parked = null;
        long deadline = System.currentTimeMillis() + 30000;
        while (System.currentTimeMillis() < deadline)
        {
            parked = parkedFrame(w);
            if (parked != null)
            {
                int before = written.get();
                Thread.sleep(300);
                if (parkedFrame(w) != null && written.get() == before)
                    break;
            }
            Thread.sleep(20);
        }
        long used1 = direct.getMemoryUsed() - used0, count1 = direct.getCount() - count0;
        int w1 = written.get(), a1 = allocated.getInt(pool), q1 = queued.size();
        Thread.sleep(2000);
        long used2 = direct.getMemoryUsed() - used0, count2 = direct.getCount() - count0;
        emit("unit stall n=" + n + " S=" + S + " state=" + w.getState() + " parkedAt=" + parked + " written=" + w1 + " allocated=" + a1
             + " flushCallbacks=" + q1 + " usedDelta=" + used1 + " countDelta=" + count1 + " | after 2 s: written=" + written.get()
             + " allocated=" + allocated.getInt(pool) + " usedDelta=" + used2 + " countDelta=" + count2);
        check("stall-writer-parked-in-take", parked != null && w.getState() == Thread.State.WAITING, "state=" + w.getState() + " frame=" + parked);
        check("stall-allocated==n", a1 == n && allocated.getInt(pool) == n, "allocated=" + a1 + " n=" + n);
        check("stall-direct-delta==n*S", Math.abs(used1 - (long) n * S) <= 64 * 1024 && used2 == used1, "delta=" + used1 + " then " + used2 + " expected=" + (long) n * S);
        check("stall-flat", written.get() == w1 && count2 == count1, "written " + w1 + " -> " + written.get() + ", count " + count1 + " -> " + count2);
        check("stall-flush-callbacks==n-1", q1 == n - 1, "flushCallbacks=" + q1 + " (the n-th buffer's flush is requested only after the wait ends; at n=1 none: the deadlock)");
        w.interrupt();
        w.join(5000);
        for (HintsBuffer b : queued)
            b.free();
        pool.close();
    }

    private static String parkedFrame(Thread t)
    {
        boolean inSwitch = false;
        String take = null;
        for (StackTraceElement e : t.getStackTrace())
        {
            if (e.getMethodName().equals("take") && e.getClassName().startsWith("java.util.concurrent."))
                take = e.toString();
            if (e.getClassName().equals(HintsBufferPool.class.getName()) && e.getMethodName().equals("switchCurrentBuffer"))
                inSwitch = true;
        }
        return inSwitch ? take : null;
    }

    // ---- derive ----------------------------------------------------------------------------------------------------
    private void derive() throws Exception
    {
        // HintsService.instance is built once per JVM (static initializer), so one max_mutation_size per JVM:
        // -Dstage4.mms=<MiB>, set on the raw config before HintsService is first touched.
        int mMiB = Integer.getInteger("stage4.mms");
        emit("unit derive original max_mutation_size=" + DatabaseDescriptor.getRawConfig().max_mutation_size);
        DatabaseDescriptor.getRawConfig().max_mutation_size = new DataStorageSpec.IntKibibytesBound(mMiB * 1024L);
        int m = DatabaseDescriptor.getMaxMutationSize();
        settle();
        HintsService svc = HintsService.instance;
        Field pf = HintsService.class.getDeclaredField("bufferPool");
        pf.setAccessible(true);
        HintsBufferPool pool = (HintsBufferPool) pf.get(svc);
        Field sf = HintsBufferPool.class.getDeclaredField("bufferSize");
        sf.setAccessible(true);
        int slab = sf.getInt(pool);
        int expect = Math.max(m * 2, 32 << 20);
        check("derive-slab-m" + mMiB + "MiB", slab == expect, "m=" + m + " bufferSize=" + slab + " expected max(2m,32MiB)=" + expect);
        // boundary on the real derived pool: hintSize + 12 == slab/2 accepted, one byte more rejected
        int cap = slab / 2;
        Hint ok = hintWithSize(cap - HintsBuffer.ENTRY_OVERHEAD_SIZE);
        Hint over = hintWithSize(cap - HintsBuffer.ENTRY_OVERHEAD_SIZE + 1);
        int okSize = (int) Hint.serializer.serializedSize(ok, MessagingService.current_version);
        int overSize = (int) Hint.serializer.serializedSize(over, MessagingService.current_version);
        long used0 = direct.getMemoryUsed();
        String r1, r2;
        try { pool.write(ImmutableList.of(HOST), ok); r1 = "accepted"; }
        catch (IllegalArgumentException e) { r1 = "rejected(" + e.getMessage() + ")"; }
        long used1 = direct.getMemoryUsed();
        try { pool.write(ImmutableList.of(HOST), over); r2 = "accepted"; }
        catch (IllegalArgumentException e) { r2 = "rejected(" + e.getMessage() + ")"; }
        check("derive-boundary-m" + mMiB + "MiB", okSize + 12 == cap && overSize + 12 == cap + 1 && r1.equals("accepted") && r2.startsWith("rejected"),
              "slab=" + slab + " cap=" + cap + " hintSize(ok)=" + okSize + ":" + r1 + " hintSize(over)=" + overSize + ":" + r2);
        emit("unit derive direct MemoryUsed before first write " + used0 + " after (slab allocated) " + used1 + " delta " + (used1 - used0));
        pool.close();
    }

    // ---- helpers ---------------------------------------------------------------------------------------------------
    private static Hint hint(int idx, int valueLen)
    {
        TableMetadata table = Schema.instance.getTableMetadata(KEYSPACE, TABLE);
        long ts = 1_000_000L + idx;
        Mutation m = new RowUpdateBuilder(table, ts, bytes(idx)).clustering(bytes(idx)).add("val", ByteBuffer.allocate(valueLen)).build();
        return Hint.create(m, ts / 1000);
    }

    /** A hint whose Hint.serializer.serializedSize is exactly the wanted size (value length found by solving the linear part). */
    private static Hint hintWithSize(int wanted)
    {
        int len = wanted - 100;
        for (int tries = 0; tries < 64; tries++)
        {
            Hint h = hint(0, len);
            long size = Hint.serializer.serializedSize(h, MessagingService.current_version);
            if (size == wanted)
                return h;
            len += (int) (wanted - size);
        }
        throw new AssertionError("cannot size a hint to " + wanted);
    }

    /** GC until the direct pool's MemoryUsed is the same on three reads 300 ms apart. */
    private static void settle() throws InterruptedException
    {
        long prev = -1;
        int same = 0;
        for (int i = 0; i < 60 && same < 3; i++)
        {
            System.gc();
            Thread.sleep(300);
            long u = direct.getMemoryUsed();
            same = u == prev ? same + 1 : 0;
            prev = u;
        }
    }

    private static void check(String name, boolean ok, String detail)
    {
        if (!ok)
            mismatches.add(name);
        emit("check " + name + (ok ? " ok " : " MISMATCH ") + detail);
    }

    private static void emit(String line)
    {
        System.out.println("STAGE4 " + line);
        String out = System.getProperty("stage4.out");
        if (out != null)
        {
            try (FileWriter w = new FileWriter(out, true)) { w.write("STAGE4 " + line + "\n"); }
            catch (java.io.IOException e) { throw new RuntimeException(e); }
        }
    }
}
