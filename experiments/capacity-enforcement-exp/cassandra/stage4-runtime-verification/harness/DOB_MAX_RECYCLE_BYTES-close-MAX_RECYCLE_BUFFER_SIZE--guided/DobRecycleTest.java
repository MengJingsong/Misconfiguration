/*
 * Stage-4 harness, unit tier U1-U10 of DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE (case file section 9e).
 * Not upstream. Copy into test/unit/org/apache/cassandra/io/util/ (package access to capacity(), calculateNewSize() and the
 * buffer field). One JVM per value: the limit is a static final read at class initialization; the test never sets it.
 * Every probe runs on its own io.netty FastThreadLocalThread (a single-thread executor that stays alive between steps, so the
 * direct pool can be read while the thread holds its buffer). Prints "STAGE4 check <name> <expected> <actual> ok|MISMATCH" and
 * "STAGE4 info" lines (also to -Dstage4.out); fails at the end on a mismatch.
 * -Dstage4.expect_init_failure=true: U10, only records how the first touch of DataOutputBuffer fails.
 */
package org.apache.cassandra.io.util;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.Assert;
import org.junit.Test;

import io.netty.util.concurrent.FastThreadLocalThread;

public class DobRecycleTest
{
    static PrintWriter out;
    static int checks = 0, mismatches = 0;
    static BufferPoolMXBean direct;

    static void line(String s) { System.out.println(s); if (out != null) { out.println(s); out.flush(); } }

    static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        checks++; if (!ok) mismatches++;
        line("STAGE4 check " + name + " " + expected + " " + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    static long used() { return direct.getMemoryUsed(); }
    static long count() { return direct.getCount(); }

    /** a probe: one FastThreadLocalThread that stays alive until stop() */
    static final class Probe
    {
        final ExecutorService ex = Executors.newSingleThreadExecutor(r -> new FastThreadLocalThread(r, "stage4-probe"));
        <T> T run(Callable<T> c) throws Exception { return ex.submit(c).get(60, TimeUnit.SECONDS); }
        void stop() throws Exception { ex.shutdown(); ex.awaitTermination(30, TimeUnit.SECONDS); }
    }

    static DataOutputBuffer scratch() { return DataOutputBuffer.scratchBuffer.get(); }

    static long settle(java.util.function.LongSupplier s, long want, long ms) throws InterruptedException
    {
        long end = System.currentTimeMillis() + ms, v = s.getAsLong();
        while (v != want && System.currentTimeMillis() < end) { Thread.sleep(50); v = s.getAsLong(); }
        return v;
    }

    @Test
    public void recycle() throws Throwable
    {
        String f = System.getProperty("stage4.out");
        if (f != null) out = new PrintWriter(new FileWriter(f, true));
        line("STAGE4 info props dob_max_recycle_bytes=" + System.getProperty("cassandra.dob_max_recycle_bytes") + " dob.allocate_type=" + System.getProperty("cassandra.dob.allocate_type"));

        if (Boolean.getBoolean("stage4.expect_init_failure"))
        {   // U10
            String got = "initialized";
            try { Class.forName("org.apache.cassandra.io.util.DataOutputBuffer", true, DobRecycleTest.class.getClassLoader()); }
            catch (Throwable t)
            {
                Throwable c = t.getCause();
                got = t.getClass().getSimpleName() + (c == null ? "" : " <- " + c.getClass().getSimpleName() + ": " + c.getMessage());
            }
            line("STAGE4 info U10 first touch: " + got);
            check("U10_init_fails", true, got.startsWith("ExceptionInInitializerError"));
            line("STAGE4 summary checks " + checks + " mismatches " + mismatches);
            Assert.assertEquals(0, mismatches);
            return;
        }

        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct")) direct = b;

        // U1 — read-back of the statics by reflection
        Field fl = DataOutputBuffer.class.getDeclaredField("MAX_RECYCLE_BUFFER_SIZE"); fl.setAccessible(true);
        Field ft = DataOutputBuffer.class.getDeclaredField("ALLOCATION_TYPE"); ft.setAccessible(true);
        int L = fl.getInt(null);
        String type = String.valueOf(ft.get(null));
        String prop = System.getProperty("cassandra.dob_max_recycle_bytes");
        check("U1_L", prop == null ? 1048576 : Integer.decode(prop), L);
        String tprop = System.getProperty("cassandra.dob.allocate_type");
        check("U1_type", tprop == null ? "DIRECT" : tprop.toUpperCase(), type);
        boolean isDirect = type.equals("DIRECT");
        line("STAGE4 info L " + L + " type " + type);

        // U2 — one instance per thread, 128 bytes at creation
        Probe p = new Probe(), q = new Probe();
        DataOutputBuffer a1 = p.run(DobRecycleTest::scratch), a2 = p.run(DobRecycleTest::scratch), b1 = q.run(DobRecycleTest::scratch);
        check("U2_initial_capacity", 128L, p.run(() -> scratch().capacity()));
        check("U2_initial_direct", isDirect, p.run(() -> scratch().buffer.isDirect()));
        check("U2_same_instance_same_thread", true, a1 == a2);
        check("U2_other_thread_other_instance", true, a1 != b1);
        check("U2_class", "org.apache.cassandra.io.util.DataOutputBuffer$1$1", a1.getClass().getName());
        p.stop(); q.stop();

        if (L >= 256)
        {
            // U3 — keep at L, replace at L + 1 (one-shot write from 128: capacity max(256, n))
            Probe k = new Probe();
            k.run(DobRecycleTest::scratch);
            long u0 = used(), c0 = count();
            Object[] r = k.run(() -> {
                DataOutputBuffer d = scratch();
                d.write(new byte[L]);
                ByteBuffer before = d.buffer;
                long cap = d.capacity();
                d.close();
                return new Object[]{ cap, before == d.buffer, d.capacity(), d.buffer.position() };
            });
            check("U3_keep_capacity_in_use", (long) L, r[0]);
            check("U3_keep_same_buffer", true, r[1]);
            check("U3_keep_capacity_after", (long) L, r[2]);
            check("U3_keep_position_0", 0, r[3]);
            if (isDirect)
            {
                check("U3_keep_pool_delta", (long) L - 128, used() - u0);
                check("U3_keep_count_delta", 0L, count() - c0);
            }
            Probe rp = new Probe();
            rp.run(DobRecycleTest::scratch);
            long u1 = used(), c1 = count();
            Object[] r2 = rp.run(() -> {
                DataOutputBuffer d = scratch();
                d.write(new byte[L + 1]);
                ByteBuffer before = d.buffer;
                long cap = d.capacity();
                d.close();
                return new Object[]{ cap, before == d.buffer, d.capacity() };
            });
            check("U3_replace_capacity_in_use", (long) L + 1, r2[0]);
            check("U3_replace_new_buffer", false, r2[1]);
            check("U3_replace_capacity_after", 128L, r2[2]);
            if (isDirect)
            {
                check("U3_replace_pool_delta", 0L, used() - u1);
                check("U3_replace_count_delta", 0L, count() - c1);
            }
            k.stop(); rp.stop();
        }

        // U4 — the grow policy, each probe on a fresh thread
        for (int n : new int[]{ 129, 256, 257, 100000, 1048577 })
        {
            Probe g = new Probe();
            long cap = g.run(() -> { DataOutputBuffer d = scratch(); for (int i = 0; i < n; i++) d.write(1); long c = d.capacity(); d.close(); return c; });
            long want = 128;
            while (want < n) want *= 2;
            check("U4_single_bytes_" + n, want, cap);
            g.stop();
        }
        for (int v : new int[]{ 1000, 100000, 524238, 524239 })
        {
            Probe g = new Probe();
            long[] cr = g.run(() -> {
                DataOutputBuffer d = scratch();
                d.write(new byte[50]);
                d.write(ByteBuffer.wrap(new byte[v]));
                d.write(1);
                long c = d.capacity();
                d.close();
                return new long[]{ c, d.capacity() };
            });
            check("U4_prefix50_value_byte_" + v, 2L * (v + 50), cr[0]);
            check("U4_prefix50_value_byte_" + v + "_after_close", 2L * (v + 50) <= L ? 2L * (v + 50) : 128L, cr[1]);
            g.stop();
        }
        for (int s : new int[]{ 1000, 999999 })
        {
            Probe g = new Probe();
            long cap = g.run(() -> { DataOutputBuffer d = scratch(); d.write(new byte[s]); long c = d.capacity(); d.close(); return c; });
            check("U4_one_shot_" + s, (long) Math.max(256, s), cap);
            g.stop();
        }
        for (long c : new long[]{ 64L << 20, (64L << 20) + 2 })
        {
            DataOutputBuffer spy = new DataOutputBuffer() { @Override long capacity() { return c; } };
            long got = spy.calculateNewSize(1);
            check("U4_calculateNewSize_" + c, c > (64L << 20) ? (3 * c) / 2 : 2 * c, got);
            spy.close();
        }

        if (isDirect && L >= 262144)
        {
            // U5 — a parked thread keeps its buffer across GC; a dead thread's buffer goes at the next GC
            // runbook fix 2026-10-15 (run 1, unit tier restarted): collect the earlier probes' dead-thread buffers first, so the
            // GC below frees nothing but what this step measures
            System.gc(); Thread.sleep(1000);
            Probe t = new Probe();
            t.run(DobRecycleTest::scratch);
            long u0 = used(), c0 = count();
            t.run(() -> { DataOutputBuffer d = scratch(); d.write(new byte[262144]); d.close(); return null; });
            long kept = used() - u0;
            System.gc(); Thread.sleep(1000);
            check("U5_parked_kept_before_gc", 262144L - 128, kept);
            check("U5_parked_survives_gc", 262144L - 128, used() - u0);
            long uBefore = used(), cBefore = count();
            t.stop();
            Thread.sleep(500);
            check("U5_dead_thread_still_held_before_gc", uBefore, used());
            System.gc();
            long uAfter = settle(DobRecycleTest::used, uBefore - 262144, 5000);
            long cAfter = settle(DobRecycleTest::count, cBefore - 1, 5000);
            check("U5_dead_thread_freed_after_gc_bytes", -262144L, uAfter - uBefore);
            check("U5_dead_thread_freed_after_gc_count", -1L, cAfter - cBefore);
            line("STAGE4 info U5 c0 " + c0);
        }

        if (isDirect && L >= 256)
        {
            // U6 — 8 parked threads
            for (int extra : new int[]{ 0, 1 })
            {
                List<Probe> ps = new ArrayList<>();
                for (int i = 0; i < 8; i++) { Probe x = new Probe(); x.run(DobRecycleTest::scratch); ps.add(x); }
                long u0 = used();
                for (Probe x : ps) x.run(() -> { DataOutputBuffer d = scratch(); d.write(new byte[L + extra]); d.close(); return null; });
                check("U6_8_threads_" + (extra == 0 ? "L" : "L+1"), extra == 0 ? 8L * (L - 128) : 0L, used() - u0);
                for (Probe x : ps) x.stop();
            }
        }

        if (L < 128)
        {
            // U7 — every close replaces, even untouched
            Probe s = new Probe();
            Object[] r = s.run(() -> {
                DataOutputBuffer d = scratch();
                ByteBuffer x0 = d.buffer; d.close();
                ByteBuffer x1 = d.buffer; d.close();
                ByteBuffer x2 = d.buffer;
                return new Object[]{ x0 != x1 && x1 != x2, d.capacity() };
            });
            check("U7_every_close_replaces", true, r[0]);
            check("U7_capacity_stays_128", 128L, r[1]);
            s.stop();
        }

        // U8 — buffer(false) hands the buffer away; close() then installs a new 128-byte one
        Probe h = new Probe();
        Object[] r8 = h.run(() -> {
            DataOutputBuffer d = scratch();
            d.write(new byte[10]);
            ByteBuffer away = d.buffer(false);
            String err = "none";
            try { d.close(); } catch (Throwable t) { err = t.toString(); }
            return new Object[]{ err, d.buffer != null && d.buffer != away, d.buffer == null ? -1 : d.capacity() };
        });
        check("U8_no_exception", "none", r8[0]);
        check("U8_new_buffer", true, r8[1]);
        check("U8_capacity_128", 128L, r8[2]);
        h.stop();

        if (!isDirect)
        {
            // U9 — heap mode: same rule on array().length, direct pool unchanged
            Probe hp = new Probe();
            long u0 = used();
            Object[] r9 = hp.run(() -> {
                DataOutputBuffer d = scratch();
                boolean dir = d.buffer.isDirect();
                d.write(new byte[L]);
                byte[] arr = d.buffer.array();
                d.close();
                boolean same = d.buffer.array() == arr;
                int lenKept = d.buffer.array().length;
                d.write(new byte[L + 1]);
                d.close();
                return new Object[]{ dir, same, lenKept, d.buffer.array().length };
            });
            check("U9_not_direct", false, r9[0]);
            check("U9_keep_same_array", true, r9[1]);
            check("U9_keep_length_L", L, r9[2]);
            check("U9_replace_length_128", 128, r9[3]);
            check("U9_direct_pool_unchanged", 0L, used() - u0);
            hp.stop();
        }

        line("STAGE4 summary checks " + checks + " mismatches " + mismatches);
        Assert.assertEquals(0, mismatches);
    }
}
