package org.apache.cassandra.utils.memory;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.utils.concurrent.ImmediateFuture;
import org.apache.cassandra.utils.concurrent.OpOrder;

/**
 * Unit tier (B2) of max-cloned-size-allocate-size--autonomous (SlabAllocator.MAX_CLONED_SIZE, line 92). One scenario per JVM.
 * usage: java ... SlabCapProbe <fill|blocking|control> <L MiB> <S bytes>
 *  fill      offheap_buffers pool (SlabPool(heap, L)): phase 1 (N1 = floor(L/2/S) allocations), phase 2 (to the plateau, extra allocation on a
 *            second allocator parks, discard, release)
 *  blocking  fill to the plateau, then a blocking op group (Barrier.issue + markBlocking) allocates K = ceil(16 MiB / S) past L
 *  control   heap_buffers pool (SlabPool(L, 0)): same allocations charged to onHeap; plateau at L on the heap counter, offHeap stays 0
 * Prints "STAGE4 reading k=v" (raw) and "STAGE4 check <name> ok|MISMATCH <detail>" (B2f as amended 2026-10-26, plus instrument checks).
 */
public class SlabCapProbe
{
    static final long MIB = 1L << 20;
    static final int MAX_CLONED = 128 * 1024;
    static int mismatches = 0;

    static void reading(String k, Object v) { System.out.println("STAGE4 reading " + k + "=" + v); }

    static void check(String name, boolean ok, String detail)
    {
        if (!ok) mismatches++;
        System.out.println("STAGE4 check " + name + (ok ? " ok " : " MISMATCH ") + detail);
    }

    static long rssAnon() throws Exception
    {
        try (BufferedReader r = new BufferedReader(new java.io.FileReader("/proc/self/status")))
        {
            for (String l; (l = r.readLine()) != null; )
                if (l.startsWith("RssAnon:")) return Long.parseLong(l.replaceAll("[^0-9]", "")) * 1024;
        }
        throw new IllegalStateException("no RssAnon");
    }

    static String nmtOther() throws Exception
    {
        String pid = ManagementFactory.getRuntimeMXBean().getName().split("@")[0];
        Process p = new ProcessBuilder("jcmd", pid, "VM.native_memory", "summary").redirectErrorStream(true).start();
        StringBuilder sb = new StringBuilder();
        try (BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream())))
        {
            for (String l; (l = r.readLine()) != null; )
                if (l.contains("Other (") || l.contains("Total: ")) sb.append(l.trim()).append(" | ");
        }
        p.waitFor();
        return sb.toString();
    }

    static BufferPoolMXBean direct()
    {
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct")) return b;
        throw new IllegalStateException("no direct pool");
    }

    /** the region rule of SlabAllocator (n allocations of s bytes, one thread): {capacity of direct buffers, buffer count} */
    static long[] model(long n, int s)
    {
        if (s > MAX_CLONED) return new long[]{ n * s, n };
        if (n == 0) return new long[]{ 0, 0 };
        long per = (1L << 20) / s;
        long regions = (n + per - 1) / per;
        return new long[]{ regions * (1L << 20), regions };
    }

    public static void main(String[] args) throws Exception
    {
        String mode = args[0];
        long L = Long.parseLong(args[1]) * MIB;
        int S = Integer.parseInt(args[2]);
        String cfg = System.getProperty("cassandra.config");
        if (cfg != null) DatabaseDescriptor.daemonInitialization();
        AtomicInteger cleans = new AtomicInteger();
        // throttled stub: unthrottled, MemtableCleanerThread calls clean() in a tight loop while needsCleaning() stays true (sibling case defect 1)
        MemtableCleaner cleaner = () -> { cleans.incrementAndGet(); try { Thread.sleep(50); } catch (InterruptedException e) { Thread.currentThread().interrupt(); } return ImmediateFuture.success(false); };
        reading("mode", mode + " L_MiB=" + args[1] + " S=" + S);
        if (mode.equals("control")) { control(L, S, cleaner, cleans); System.out.println("STAGE4 done mismatches=" + mismatches); System.exit(0); }

        long heapLimit = 2L << 30;
        SlabPool pool = new SlabPool(heapLimit, L, 0.99f, cleaner);
        SlabAllocator a = (SlabAllocator) pool.newAllocator("t");
        OpOrder order = new OpOrder();
        OpOrder.Group group = order.start();
        BufferPoolMXBean dp = direct();
        System.gc();
        long rss0 = rssAnon(), d0 = dp.getMemoryUsed(), c0 = dp.getCount();
        reading("nmt_before", nmtOther());
        reading("direct_before", d0 + " count=" + c0);

        // phase 1
        long n1 = (L / 2) / S, n = 0;
        for (; n < n1; n++) a.allocate(S, group);
        long used1 = pool.offHeap.used(), dd1 = dp.getMemoryUsed() - d0, dc1 = dp.getCount() - c0;
        long[] m1 = model(n1, S);
        reading("p1_n", n1); reading("p1_used", used1); reading("p1_direct_delta", dd1); reading("p1_count_delta", dc1);
        check("p1-used-equals-N*S", used1 == n1 * S, "used=" + used1 + " N*S=" + n1 * S);
        check("p1-direct-delta-equals-model", dd1 == m1[0] && dc1 == m1[1], "delta=" + dd1 + " count=" + dc1 + " model=" + m1[0] + "/" + m1[1]);
        check("p1-onHeap-0", pool.onHeap.used() == 0, "onHeap=" + pool.onHeap.used());

        // phase 2: to the plateau
        while (pool.offHeap.used() + S <= L) { a.allocate(S, group); n++; }
        long used = pool.offHeap.used(), owns = a.offHeap().owns();
        long dd = dp.getMemoryUsed() - d0, dc = dp.getCount() - c0, rss1 = rssAnon();
        long[] mdl = model(n, S);
        reading("n", n); reading("used", used); reading("owns", owns); reading("limit", L);
        reading("direct_delta", dd); reading("count_delta", dc); reading("rss_delta", rss1 - rss0);
        reading("nmt_after", nmtOther());
        reading("cleaner_calls", cleans.get());
        reading("onHeap_used", pool.onHeap.used());
        reading("unslabbed_oversize", S > MAX_CLONED);
        check("fill-reached-limit", used + S > L, "used=" + used + " S=" + S + " L=" + L);
        check("used-equals-n*S", used == n * S, "used=" + used + " n*S=" + n * S);
        check("used-le-L", used <= L, "used=" + used + " L=" + L);
        check("n-equals-floor(L/S)", n == L / S, "n=" + n + " L/S=" + (L / S));
        check("owns-equals-used", owns == used, "owns=" + owns + " used=" + used);
        check("direct-delta-equals-model", dd == mdl[0] && dc == mdl[1], "delta=" + dd + " count=" + dc + " model=" + mdl[0] + "/" + mdl[1]);
        if (S > MAX_CLONED) check("oversize-direct-equals-used", dd == used && dc == n, "delta=" + dd + " used=" + used + " count=" + dc + " n=" + n);
        if (S <= MAX_CLONED) check("waste-within-bound", dd - used >= 0 && dd - used <= mdl[1] * (MIB % S) + MIB, "excess=" + (dd - used) + " regions=" + mdl[1]);
        long lo = used - MIB, hi = dd + 4 * MIB;
        if (L >= 32 * MIB) check("rssAnon-delta-in[used-1MiB,direct+4MiB]", rss1 - rss0 >= lo && rss1 - rss0 <= hi, "delta=" + (rss1 - rss0) + " range=[" + lo + "," + hi + "]");
        else reading("rssAnon_band_not_applied_below_32MiB", "delta=" + (rss1 - rss0) + " range=[" + lo + "," + hi + "]");

        if (mode.equals("fill"))
        {
            SlabAllocator b = (SlabAllocator) pool.newAllocator("t2");
            OpOrder.Group g2 = new OpOrder().start();
            AtomicReference<Throwable> err = new AtomicReference<>();
            Thread t = new Thread(() -> { try { b.allocate(S, g2); } catch (Throwable e) { err.set(e); } }, "extra");
            t.start();
            Thread.sleep(2000);
            Thread.State st = t.getState();
            reading("extra_state_2s", st);
            check("extra-allocate-parked", st == Thread.State.WAITING || st == Thread.State.TIMED_WAITING, "state=" + st);
            check("used-unchanged-while-parked", pool.offHeap.used() == used, "used=" + pool.offHeap.used());
            check("direct-unchanged-while-parked", dp.getMemoryUsed() - d0 == dd, "delta=" + (dp.getMemoryUsed() - d0));
            a.setDiscarding();
            reading("used_after_discarding", pool.offHeap.used());
            a.setDiscarded();
            t.join(10000);
            reading("extra_state_after_discard", t.getState());
            check("extra-completed-after-discard", !t.isAlive() && err.get() == null, "alive=" + t.isAlive() + " err=" + err.get());
            check("used==S-after-discard", pool.offHeap.used() == S, "used=" + pool.offHeap.used() + " S=" + S);
            long[] mb = model(1, S);
            long dda = dp.getMemoryUsed() - d0, dca = dp.getCount() - c0;
            reading("direct_delta_after_discard", dda + " count=" + dca);
            check("direct-released-after-discard", dda == mb[0] && dca == mb[1], "delta=" + dda + " count=" + dca + " expect=" + mb[0] + "/" + mb[1]);
        }
        else if (mode.equals("blocking"))
        {
            OpOrder o2 = new OpOrder();
            OpOrder.Group g = o2.start();
            OpOrder.Barrier bar = o2.newBarrier();
            bar.issue();
            bar.markBlocking();
            check("group-isBlocking", g.isBlocking(), "isBlocking=" + g.isBlocking());
            SlabAllocator c = (SlabAllocator) pool.newAllocator("t3");
            final int K = (int) ((16 * MIB + S - 1) / S);
            AtomicReference<Throwable> err = new AtomicReference<>();
            Thread t = new Thread(() -> { try { for (int i = 0; i < K; i++) c.allocate(S, g); } catch (Throwable e) { err.set(e); } }, "blocking-writer");
            t.start();
            t.join(10000);
            reading("blocking_K", K);
            reading("blocking_writer_alive", t.isAlive());
            reading("used_after_blocking", pool.offHeap.used());
            check("blocking-group-not-parked", !t.isAlive() && err.get() == null, "alive=" + t.isAlive() + " err=" + err.get());
            check("blocking-group-exceeds-L", pool.offHeap.used() > L && pool.offHeap.used() == used + (long) K * S, "used=" + pool.offHeap.used() + " L=" + L + " expect=" + (used + (long) K * S));
            SlabAllocator d = (SlabAllocator) pool.newAllocator("t4");
            OpOrder.Group g4 = new OpOrder().start();
            Thread t4 = new Thread(() -> d.allocate(S, g4), "nonblocking-extra");
            t4.start();
            Thread.sleep(2000);
            reading("nonblocking_extra_state", t4.getState());
            check("nonblocking-still-parked", t4.getState() == Thread.State.WAITING || t4.getState() == Thread.State.TIMED_WAITING, "state=" + t4.getState());
        }
        System.out.println("STAGE4 done mismatches=" + mismatches);
        System.exit(0);
    }

    /** heap_buffers: SlabPool(L, 0): the heap counter takes the charge, plateau at L for every S (ByteBuffer.allocate path included), off-heap counter stays 0 */
    static void control(long L, int S, MemtableCleaner cleaner, AtomicInteger cleans) throws Exception
    {
        SlabPool pool = new SlabPool(L, 0, 0.99f, cleaner);
        SlabAllocator a = (SlabAllocator) pool.newAllocator("t");
        OpOrder.Group group = new OpOrder().start();
        BufferPoolMXBean dp = direct();
        long d0 = dp.getMemoryUsed(), c0 = dp.getCount();
        long n = 0;
        while (pool.onHeap.used() + S <= L) { a.allocate(S, group); n++; }
        reading("n", n); reading("offHeap_used", pool.offHeap.used()); reading("onHeap_used", pool.onHeap.used());
        reading("direct_delta", (dp.getMemoryUsed() - d0) + " count=" + (dp.getCount() - c0));
        check("control-offHeap-stays-0", pool.offHeap.used() == 0, "offHeap=" + pool.offHeap.used());
        check("control-onHeap-plateau-floor(L/S)*S", pool.onHeap.used() == (L / S) * S && n == L / S, "onHeap=" + pool.onHeap.used() + " expect=" + (L / S) * S);
        check("control-no-direct-buffers", dp.getMemoryUsed() == d0 && dp.getCount() == c0, "delta=" + (dp.getMemoryUsed() - d0));
        SlabAllocator b = (SlabAllocator) pool.newAllocator("t2");
        OpOrder.Group g2 = new OpOrder().start();
        AtomicReference<Throwable> err = new AtomicReference<>();
        Thread t = new Thread(() -> { try { b.allocate(S, g2); } catch (Throwable e) { err.set(e); } }, "extra");
        t.start();
        Thread.sleep(2000);
        reading("extra_state_2s", t.getState());
        check("control-extra-parked-on-heap-limit", t.getState() == Thread.State.WAITING || t.getState() == Thread.State.TIMED_WAITING, "state=" + t.getState());
        a.setDiscarding();
        a.setDiscarded();
        t.join(10000);
        check("control-extra-completes-after-discard", !t.isAlive() && err.get() == null, "alive=" + t.isAlive() + " err=" + err.get());
    }
}
