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
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Queue;
import java.util.Random;
import java.util.UUID;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.net.MessagingService;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.Schema;
import org.apache.cassandra.schema.TableMetadata;

import static org.apache.cassandra.utils.ByteBufferUtil.bytes;

/**
 * Stage-4 unit tier (B2, as amended 2026-10-26) of the if-check-exp case
 * hints_buffer_size-allocateBytes-prev--autonomous.
 *
 * Observation only: it prints one HBCAP line per reading (System.out; it lands in
 * build/test/logs/** /TEST-org.apache.cassandra.hints.HintsBufferCapTest.log) and asserts nothing about
 * the case, so every reading reaches the log. The run script and the self-check judge the lines.
 *
 *   case 1 (one @Test per slab size B): HBCAP case=1 B=.. e=.. emin=.. emax=.. n=.. sum=.. remaining=.. nextNull=..
 *          alloc1Null=.. leftover=.. found=.. foundBytes=.. dmem0=.. dmem1=.. dmem2=.. dmem3=.. cnt0=.. cnt1=.. cnt2=.. cnt3=..
 *   case 2 (same @Test):  HBCAP case=2 B=.. request=.. threw=<exception class or none> msg=..
 *   case 3 (pool, B=32 MiB): HBCAP case=3 B=.. max=.. offeredTarget=.. hintsWritten=.. allocatedBuffers=.. held=..
 *          writerState=.. inTake=.. dmem0=.. dmem1=.. cnt0=.. cnt1=..
 *   formula:               HBCAP formula M=.. B=..
 *
 * Settings (system properties, -Dtest.jvm.args): hbcap.sizes (comma list of slab sizes in bytes, default
 * 1048576,33554432,67108864, which are the B2b values; a shakedown passes another list), hbcap.pool (true/false,
 * default true).
 */
public class HintsBufferCapTest
{
    private static final String KS = "hbcap";
    private static final String TABLE = "t";
    private static final UUID HOST = UUID.randomUUID();
    private static final int VALUE_BYTES = 4096;
    private static final long BASE_TS = 1_700_000_000_000L; // fixed, so every hint serializes to the same size
    private static BufferPoolMXBean DIRECT;
    private static final byte[] VALUE = new byte[VALUE_BYTES];

    @BeforeClass
    public static void defineSchema()
    {
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1), SchemaLoader.standardCFMD(KS, TABLE));
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct"))
                DIRECT = b;
        Random r = new Random(42);
        for (int i = 0; i < VALUE_BYTES; i++)
            VALUE[i] = (byte) ('a' + r.nextInt(26)); // random bytes (printable, since val is an ascii column)
        // warm this thread up: the first Mutation.serializedSize() on a thread creates a 128-byte direct
        // scratch buffer (Mutation.java:453); it must exist before any dmem baseline
        Hint.serializer.serializedSize(hint(0), MessagingService.current_version);
        String mdm = "unset";
        for (String arg : ManagementFactory.getRuntimeMXBean().getInputArguments())
            if (arg.startsWith("-XX:MaxDirectMemorySize="))
                mdm = arg.substring("-XX:MaxDirectMemorySize=".length());
        emit("HBCAP setup maxDirectMemorySize=" + mdm + " directBean=" + (DIRECT != null)
             + " valueBytes=" + VALUE_BYTES + " entryOverhead=" + HintsBuffer.ENTRY_OVERHEAD_SIZE);
    }

    static Hint hint(int idx)
    {
        TableMetadata table = Schema.instance.getTableMetadata(KS, TABLE);
        Mutation m = new RowUpdateBuilder(table, TimeUnit.MILLISECONDS.toMicros(BASE_TS), bytes(idx))
                     .clustering(String.format("%08d", idx % 100_000_000))
                     .add("val", ByteBuffer.wrap(VALUE))
                     .build();
        return Hint.create(m, BASE_TS);
    }

    static void emit(String s)
    {
        System.out.println(s);
        System.out.flush();
    }

    static long used() { return DIRECT.getMemoryUsed(); }
    static long count() { return DIRECT.getCount(); }

    static void settle() throws InterruptedException
    {
        System.gc();
        Thread.sleep(300);
    }

    static int[] sizes()
    {
        String[] p = System.getProperty("hbcap.sizes", "1048576,33554432,67108864").split(",");
        int[] s = new int[p.length];
        for (int i = 0; i < p.length; i++)
            s[i] = Integer.parseInt(p[i].trim());
        return s;
    }

    @Test
    public void case1And2AllSizes() throws Exception
    {
        for (int b : sizes())
            fillOne(b);
    }

    private void fillOne(int B) throws Exception
    {
        settle();
        long dmem0 = used(), cnt0 = count();
        HintsBuffer buf = HintsBuffer.create(B);
        long dmem1 = used(), cnt1 = count();

        int n = 0;
        long sum = 0;
        int emin = Integer.MAX_VALUE, emax = 0;
        boolean nextNull = false;
        List<UUID> hosts = Collections.singletonList(HOST);
        while (true)
        {
            Hint h = hint(n);
            int hintSize = (int) Hint.serializer.serializedSize(h, MessagingService.current_version);
            int e = hintSize + HintsBuffer.ENTRY_OVERHEAD_SIZE;
            HintsBuffer.Allocation a = buf.allocate(hintSize);
            if (a == null)
            {
                nextNull = true;
                emin = Math.min(emin, e); emax = Math.max(emax, e);
                break;
            }
            try
            {
                a.write(hosts, h);
            }
            finally
            {
                a.close();
            }
            emin = Math.min(emin, e); emax = Math.max(emax, e);
            n++;
            sum += e;
            if (n > 10_000_000)
                break; // safety stop: the limit was never reached
        }
        int remaining = buf.remaining();
        HintsBuffer.Allocation one = buf.allocate(1); // 13 bytes; the closed-slab test (:187) must refuse it
        boolean alloc1Null = one == null;
        if (one != null)
            one.close();
        long dmem2 = used(), cnt2 = count();

        // count what the slab really holds, through the buffer's own iterator
        int found = 0;
        long foundBytes = 0;
        Iterator<ByteBuffer> it = buf.consumingHintsIterator(HOST);
        while (it.hasNext())
        {
            ByteBuffer bb = it.next();
            found++;
            foundBytes += bb.remaining();
        }

        // case 2: a single hint larger than B/2 is refused before allocation
        int request = B / 2 - HintsBuffer.ENTRY_OVERHEAD_SIZE + 1;
        String threw = "none", msg = "";
        try
        {
            HintsBuffer.Allocation big = buf.allocate(request);
            if (big != null)
                big.close();
        }
        catch (Throwable t)
        {
            threw = t.getClass().getName();
            msg = String.valueOf(t.getMessage()).replace(' ', '_');
        }

        buf.free();
        long dmem3 = used(), cnt3 = count();
        int e = emin;
        emit("HBCAP case=1 B=" + B + " e=" + e + " emin=" + emin + " emax=" + emax + " n=" + n + " sum=" + sum
             + " remaining=" + remaining + " nextNull=" + nextNull + " alloc1Null=" + alloc1Null + " leftover=" + (B - sum)
             + " found=" + found + " foundBytes=" + foundBytes
             + " dmem0=" + dmem0 + " dmem1=" + dmem1 + " dmem2=" + dmem2 + " dmem3=" + dmem3
             + " cnt0=" + cnt0 + " cnt1=" + cnt1 + " cnt2=" + cnt2 + " cnt3=" + cnt3);
        emit("HBCAP case=2 B=" + B + " request=" + request + " threw=" + threw + " msg=" + msg);
    }

    @Test
    public void case3PoolAndFormula() throws Exception
    {
        for (long mMiB : new long[]{ 8, 16, 32 })
        {
            long m = mMiB << 20;
            emit("HBCAP formula M=" + m + " B=" + Math.max(m * 2, 32 << 20));
        }
        if (!Boolean.parseBoolean(System.getProperty("hbcap.pool", "true")))
            return;

        final int B = 32 << 20;
        int max = HintsBufferPool.MAX_ALLOCATED_BUFFERS;
        Queue<HintsBuffer> held = new ConcurrentLinkedQueue<>();
        Field allocatedField = HintsBufferPool.class.getDeclaredField("allocatedBuffers");
        allocatedField.setAccessible(true);

        int e = (int) Hint.serializer.serializedSize(hint(0), MessagingService.current_version) + HintsBuffer.ENTRY_OVERHEAD_SIZE;
        long offeredTarget = (long) (3.5 * B); // amended B2c: 3.5 x B, so the writer needs a 4th buffer and must wait
        int total = (int) ((offeredTarget + e - 1) / e);
        AtomicLong written = new AtomicLong();
        CountDownLatch warmed = new CountDownLatch(1);
        CountDownLatch go = new CountDownLatch(1);
        final HintsBufferPool[] poolRef = new HintsBufferPool[1];
        Thread writer = new Thread(() -> {
            try
            {
                Hint.serializer.serializedSize(hint(0), MessagingService.current_version); // per-thread scratch buffer
                warmed.countDown();
                go.await();
                List<UUID> hosts = Collections.singletonList(HOST);
                for (int i = 0; i < total; i++)
                {
                    poolRef[0].write(hosts, hint(i));
                    written.incrementAndGet();
                }
            }
            catch (Throwable t)
            {
                emit("HBCAP case=3 writerEnded=" + t.getClass().getName());
            }
        }, "hbcap-writer");
        writer.start();
        warmed.await(60, TimeUnit.SECONDS);
        settle();
        long dmem0 = used(), cnt0 = count();
        poolRef[0] = new HintsBufferPool(B, (b, p) -> held.add(b)); // a flush callback that never recycles
        go.countDown();
        Thread.sleep(5000);
        int allocated = (int) allocatedField.get(poolRef[0]);
        long dmem1 = used(), cnt1 = count();
        Thread.State st = writer.getState();
        boolean inTake = false, inSwitch = false;
        for (StackTraceElement f : writer.getStackTrace())
        {
            inTake |= f.getMethodName().equals("take");
            inSwitch |= f.getClassName().endsWith("HintsBufferPool") && f.getMethodName().equals("switchCurrentBuffer");
        }
        emit("HBCAP case=3 B=" + B + " max=" + max + " e=" + e + " offeredTarget=" + offeredTarget + " hintsToWrite=" + total
             + " hintsWritten=" + written.get() + " allocatedBuffers=" + allocated + " held=" + held.size()
             + " writerState=" + st + " inTake=" + inTake + " inSwitch=" + inSwitch
             + " dmem0=" + dmem0 + " dmem1=" + dmem1 + " cnt0=" + cnt0 + " cnt1=" + cnt1);
        writer.interrupt();
        writer.join(10_000);
        for (HintsBuffer b : held)
            b.free();
        poolRef[0].close();
        settle();
        emit("HBCAP case=3 end writerAlive=" + writer.isAlive() + " dmemAfterFree=" + used() + " cntAfterFree=" + count());
    }
}
