/* Stage-4 unit-tier probe for nativecell-int-max-size-NativeCell-size--autonomous (case file B2 as amended B2i).
 * Not upstream code. Lives only in the local test tree. Writes csv lines (arm,key,value) to $STAGE4_OUT/results.csv.
 * Package utils.memory so it can call the package-private SubAllocator.released(long). */
package org.apache.cassandra.utils.memory;

import java.io.FileInputStream;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.db.rows.BufferCell;
import org.apache.cassandra.db.rows.Cell;
import org.apache.cassandra.db.rows.NativeCell;
import org.apache.cassandra.schema.ColumnMetadata;
import org.apache.cassandra.utils.concurrent.ImmediateFuture;
import org.apache.cassandra.utils.concurrent.OpOrder;

public class NativeCellGuardTest
{
    static final long MiB = 1L << 20;
    static final long GiB = 1L << 30;
    static PrintWriter RES;
    static ColumnMetadata col;

    @BeforeClass
    public static void init() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        String out = System.getenv("STAGE4_OUT");
        RES = new PrintWriter(new FileWriter(out + "/results.csv", true), true);
        col = ColumnMetadata.regularColumn("ks", "t", "v", BytesType.instance);
    }

    static void res(String arm, String k, Object v) { RES.println(arm + "," + k + "," + v); System.out.println("RESULT " + arm + "," + k + "," + v); }

    static long rss() throws Exception
    {
        byte[] buf = new byte[8192];
        int n;
        try (FileInputStream in = new FileInputStream("/proc/self/status")) { n = in.read(buf); }
        String s = new String(buf, 0, n);
        int i = s.indexOf("RssAnon:") + 8;
        while (!Character.isDigit(s.charAt(i))) i++;
        int k = i; while (Character.isDigit(s.charAt(k))) k++;
        return Long.parseLong(s.substring(i, k)) * 1024;
    }

    static volatile long peak;
    static Thread startSampler()
    {
        peak = 0;
        Thread t = new Thread(() -> { try { while (!Thread.currentThread().isInterrupted()) { long v = rss(); if (v > peak) peak = v; Thread.sleep(10); } } catch (Exception e) { } });
        t.setDaemon(true); t.start(); return t;
    }

    static ByteBuffer direct(long cap)
    {
        ByteBuffer b = ByteBuffer.allocateDirect((int) cap);
        for (long i = 0; i < cap; i += 4096) b.put((int) i, (byte) 0x5A);   // touch every page
        return b;
    }

    static ByteBuffer view(ByteBuffer src, int len) { ByteBuffer d = src.duplicate(); d.clear(); d.limit(len); return d; }

    static NativePool pool(long limit) { return new NativePool(1L << 24, limit, 0.25f, () -> ImmediateFuture.success(false)); }

    static OpOrder.Group nonBlocking() { return new OpOrder().start(); }

    static OpOrder.Group blocking()
    {
        OpOrder order = new OpOrder();
        OpOrder.Group g = order.start();
        OpOrder.Barrier b = order.newBarrier();
        b.issue(); b.markBlocking();
        if (!g.isBlocking()) throw new AssertionError("group not blocking");
        return g;
    }

    static NativeCell cell(NativeAllocator a, OpOrder.Group g, ByteBuffer v) { return new NativeCell(a, g, col, 1L, Cell.NO_TTL, Cell.NO_DELETION_TIME, v, null); }

    static void discard(NativeAllocator a) { a.setDiscarding(); a.setDiscarded(); }

    static void sizes(String arm, long L) throws Exception
    {
        NativeAllocator a = pool(8 * GiB).newAllocator("t");
        OpOrder.Group g = nonBlocking();
        ByteBuffer src = direct(L);
        System.gc(); Thread.sleep(300);
        long base = rss(); long owns0 = a.offHeap().owns(); long sum = 0; int bad = 0, bad2 = 0, exc = 0;
        for (int i = 0; i < 10; i++)
        {
            long before = a.offHeap().owns();
            try
            {
                NativeCell c = cell(a, g, view(src, (int) L));
                long ohs = c.offHeapSize(); long d = a.offHeap().owns() - before;
                sum += ohs;
                if (ohs != L + 21) bad++;
                if (d != L + 21) bad2++;
                res(arm, "cell" + i, ohs + ";" + d);
            }
            catch (Throwable t) { exc++; res(arm, "cell" + i + "_exception", t + " @ " + t.getStackTrace()[0]); }
        }
        Thread.sleep(300);
        long rise = rss() - base; long owns = a.offHeap().owns() - owns0;
        res(arm, "L", L); res(arm, "n_cells", 10); res(arm, "offHeapSize_mismatch", bad); res(arm, "owns_delta_mismatch", bad2);
        res(arm, "exceptions", exc); res(arm, "sum_offHeapSize", sum); res(arm, "owns_total", owns); res(arm, "rss_rise", rise);
        res(arm, "expected_total", 10 * (L + 21));
        discard(a); Thread.sleep(500);
        res(arm, "rss_rise_after_free", rss() - base); res(arm, "owns_after_discard", a.offHeap().owns());
    }

    static void guard(String arm, long poolLimit, boolean blockingGroup, ByteBuffer src) throws Exception
    {
        NativeAllocator a = pool(poolLimit).newAllocator("t");
        OpOrder.Group g = blockingGroup ? blocking() : nonBlocking();
        res(arm, "pool_limit", poolLimit); res(arm, "blocking_group", blockingGroup);
        // throwing probe: L = MAX-20 -> size = 2^31
        long b0 = rss(), o0 = a.offHeap().owns();
        try
        {
            cell(a, g, view(src, Integer.MAX_VALUE - 20));
            res(arm, "throw_probe", "NO_EXCEPTION");
        }
        catch (Throwable t)
        {
            StackTraceElement f = t.getStackTrace()[0];
            res(arm, "throw_probe", t.getClass().getName());
            res(arm, "throw_message", t.getMessage());
            res(arm, "throw_frame", f.getClassName() + "." + f.getMethodName() + ":" + f.getLineNumber());
        }
        res(arm, "throw_owns_delta", a.offHeap().owns() - o0); res(arm, "throw_rss_rise", rss() - b0);
        // passing probe: L = MAX-21 -> size = 2^31-1
        b0 = rss(); o0 = a.offHeap().owns();
        Thread s = startSampler();
        try
        {
            NativeCell c = cell(a, g, view(src, Integer.MAX_VALUE - 21));
            res(arm, "pass_probe", "OK");
            res(arm, "pass_offHeapSize", c.offHeapSize());
        }
        catch (Throwable t)
        {
            StackTraceElement f = t.getStackTrace()[0];
            res(arm, "pass_probe", t.getClass().getName() + ":" + t.getMessage() + "@" + f.getClassName() + "." + f.getMethodName() + ":" + f.getLineNumber());
        }
        s.interrupt(); Thread.sleep(50);
        res(arm, "pass_owns_delta", a.offHeap().owns() - o0); res(arm, "pass_rss_rise", rss() - b0); res(arm, "pass_rss_peak_rise", peak - b0);
        discard(a); Thread.sleep(500);
        res(arm, "after_free_rss_rise", rss() - b0);
    }

    static void poolCap(long limit) throws Exception
    {
        String arm = "P" + (limit / MiB);
        final long L = MiB; final long unit = L + 21;
        NativeAllocator a = pool(limit).newAllocator("t");
        OpOrder.Group g = nonBlocking();
        ByteBuffer src = direct(L);
        AtomicInteger done = new AtomicInteger();
        Thread w = new Thread(() -> { try { while (true) { cell(a, g, view(src, (int) L)); done.incrementAndGet(); } } catch (Throwable t) { /* interrupted */ } });
        w.start();
        int last = -1; long stableSince = System.currentTimeMillis();
        long t0 = System.currentTimeMillis();
        while (System.currentTimeMillis() - t0 < 60000)
        {
            Thread.sleep(50);
            int d = done.get();
            if (d != last) { last = d; stableSince = System.currentTimeMillis(); }
            else if (System.currentTimeMillis() - stableSince >= 2000) break;
        }
        int admitted = done.get();
        res(arm, "limit", limit); res(arm, "admitted_before_block", admitted); res(arm, "expected_admitted", limit / unit);
        res(arm, "owns_at_block", a.offHeap().owns()); res(arm, "expected_owns_at_block", admitted * unit);
        res(arm, "worker_alive_blocked", w.isAlive());
        long r0 = System.currentTimeMillis();
        a.offHeap().released(unit);
        long tr = -1;
        while (System.currentTimeMillis() - r0 < 5000) { if (done.get() > admitted) { tr = System.currentTimeMillis() - r0; break; } Thread.sleep(5); }
        res(arm, "completed_after_release_ms", tr);
        w.interrupt(); w.join(5000);
        res(arm, "worker_stopped", !w.isAlive());
        discard(a);
        // same pool size, blocking group: allocation proceeds past the limit
        NativeAllocator b = pool(limit).newAllocator("t");
        OpOrder.Group bg = blocking();
        int n = (int) (limit / unit) + 3; long maxMs = 0;
        for (int i = 0; i < n; i++) { long t1 = System.nanoTime(); cell(b, bg, view(src, (int) L)); maxMs = Math.max(maxMs, (System.nanoTime() - t1) / 1000000); }
        res(arm, "blocking_cells", n); res(arm, "blocking_max_ms", maxMs); res(arm, "blocking_owns", b.offHeap().owns());
        res(arm, "blocking_expected_owns", n * unit); res(arm, "blocking_owns_over_limit", b.offHeap().owns() > limit);
        discard(b);
    }

    static void overshoot() throws Exception
    {
        NativeAllocator a = pool(8 * MiB).newAllocator("t");
        OpOrder.Group g = blocking();
        ByteBuffer src = direct(16 * MiB);
        NativeCell c = cell(a, g, view(src, (int) (16 * MiB)));
        res("O", "pool_limit", 8 * MiB); res("O", "offHeapSize", c.offHeapSize()); res("O", "owns", a.offHeap().owns());
        res("O", "owns_over_limit_ratio", (double) a.offHeap().owns() / (8 * MiB));
        discard(a);
    }

    static void heapControl() throws Exception
    {
        NativeAllocator a = pool(8 * GiB).newAllocator("t");
        long o0 = a.offHeap().owns(), b0 = rss();
        Cell<?> c = BufferCell.live(col, 1L, ByteBuffer.allocate((int) (16 * MiB)));
        res("H", "owns_before", o0); res("H", "owns_after", a.offHeap().owns()); res("H", "cell_class", c.getClass().getSimpleName());
        res("H", "rss_rise_reported", rss() - b0);
        discard(a);
    }

    @Test
    public void run() throws Exception
    {
        String only = System.getenv("STAGE4_ARMS");
        java.util.Set<String> arms = only == null ? null : new java.util.HashSet<>(java.util.Arrays.asList(only.split(",")));
        long scale = Long.parseLong(System.getenv().getOrDefault("STAGE4_SCALE", "1"));   // shakedown switch only
        res("env", "start_rss", rss());
        if (arms == null || arms.contains("S"))
        {
            sizes("S_1KiB", 1024); sizes("S_200KiB", 200 * 1024); sizes("S_16MiB", 16 * MiB / scale); sizes("S_255MiB", 255 * MiB / scale);
        }
        if (arms == null || arms.contains("R")) { sizes("R_200KiB_a", 200 * 1024); sizes("R_200KiB_b", 200 * 1024); }
        if (arms == null || arms.contains("P")) { poolCap(8 * MiB); poolCap(16 * MiB); poolCap(32 * MiB); }
        if (arms == null || arms.contains("O")) overshoot();
        if (arms == null || arms.contains("H")) heapControl();
        if (arms == null || arms.contains("G"))
        {
            ByteBuffer src = direct(Integer.MAX_VALUE - 20);
            res("G", "src_capacity", src.capacity());
            guard("G1", 8 * GiB, false, src);
            guard("G2", 8 * MiB, true, src);
        }
        res("env", "end_rss", rss());
    }
}
