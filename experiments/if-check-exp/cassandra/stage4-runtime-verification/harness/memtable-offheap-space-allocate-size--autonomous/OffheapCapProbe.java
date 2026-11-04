package org.apache.cassandra.utils.memory;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.reflect.Field;
import java.util.Collection;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.utils.concurrent.ImmediateFuture;
import org.apache.cassandra.utils.concurrent.OpOrder;

/**
 * Unit tier (B2) of memtable-offheap-space-allocate-size--autonomous. One scenario per JVM (the pool registers metrics).
 * usage: java ... OffheapCapProbe <fill|blocking|control> <L MiB> <S bytes>
 * Prints "STAGE4 reading k=v" lines (raw) and "STAGE4 check <name> ok|MISMATCH <detail>" lines (the B2f predictions as amended
 * 2026-10-26, plus instrument checks). Exit code 0 always when the probe itself ran; MISMATCH is data, not an error.
 */
public class OffheapCapProbe
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
        String pid = java.lang.management.ManagementFactory.getRuntimeMXBean().getName().split("@")[0];
        Process p = new ProcessBuilder("jcmd", pid, "VM.native_memory", "summary").redirectErrorStream(true).start();
        StringBuilder sb = new StringBuilder();
        try (BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream())))
        {
            for (String l; (l = r.readLine()) != null; )
                if (l.contains("Other (") || l.contains("Total: ") || l.contains("Native Memory Tracking")) sb.append(l.trim()).append(" | ");
        }
        p.waitFor();
        return sb.toString();
    }

    /** the region-size rule of NativeAllocator.trySwapRegion/allocate, replayed for n allocations of s bytes (instrument known answer) */
    static long[] model(long n, int s)
    {
        if (s > MAX_CLONED) return new long[]{ n * s, n };
        long cap = 0, regions = 0, off = 0, cur = 0;
        for (long i = 0; i < n; i++)
        {
            if (cur == 0 || off + s > cur)
            {
                long size = cur == 0 ? 8192 : cur * 2;
                if (s > size) size = (long) Integer.highestOneBit(s) << 3;
                size = Math.min(1 << 20, size);
                cur = size; off = 0; cap += size; regions++;
            }
            off += s;
        }
        return new long[]{ cap, regions };
    }

    static void touch(long peer, int s)
    {
        for (int o = 0; o < s; o += 4096) org.apache.cassandra.utils.memory.MemoryUtil.setByte(peer + o, (byte) 1);
        org.apache.cassandra.utils.memory.MemoryUtil.setByte(peer + s - 1, (byte) 1);
    }

    static long[] regionStats(NativeAllocator a) throws Exception
    {
        Field rf = NativeAllocator.class.getDeclaredField("regions");
        rf.setAccessible(true);
        Collection<?> regions = (Collection<?>) rf.get(a);
        long cap = 0;
        for (Object r : regions)
        {
            Field cf = r.getClass().getDeclaredField("capacity");
            cf.setAccessible(true);
            cap += cf.getInt(r);
        }
        return new long[]{ cap, regions.size() };
    }

    static long lastCapacity(NativeAllocator a) throws Exception
    {
        Field rf = NativeAllocator.class.getDeclaredField("regions");
        rf.setAccessible(true);
        long last = 0;
        for (Object r : (Collection<?>) rf.get(a))
        {
            Field cf = r.getClass().getDeclaredField("capacity");
            cf.setAccessible(true);
            last = cf.getInt(r);
        }
        return last;
    }

    public static void main(String[] args) throws Exception
    {
        String mode = args[0];
        long L = Long.parseLong(args[1]) * MIB;
        int S = Integer.parseInt(args[2]);
        String cfg = System.getProperty("cassandra.config");
        if (cfg != null) DatabaseDescriptor.daemonInitialization();
        AtomicInteger cleans = new AtomicInteger();
        // the stub does nothing but is throttled to 20 calls/s: unthrottled, MemtableCleanerThread calls clean() in a tight loop while needsCleaning() stays true
        // (1.8 M calls in 3 s in attempt 1) and the garbage it makes grows the heap's resident set, which is inside the RssAnon reading
        MemtableCleaner cleaner = () -> { cleans.incrementAndGet(); try { Thread.sleep(50); } catch (InterruptedException e) { Thread.currentThread().interrupt(); } return ImmediateFuture.success(false); };
        long heapLimit = 1L << 30;
        reading("mode", mode + " L_MiB=" + args[1] + " S=" + S);
        if (mode.equals("control")) { control(L, S, heapLimit, cleaner, cleans); System.out.println("STAGE4 done mismatches=" + mismatches); System.exit(0); }

        NativePool pool = new NativePool(heapLimit, L, 0.33f, cleaner);
        NativeAllocator a = pool.newAllocator("t");
        OpOrder order = new OpOrder();
        OpOrder.Group group = order.start();
        System.gc();
        long rss0 = rssAnon();
        reading("nmt_before", nmtOther());
        long n = 0;
        while (pool.offHeap.used() + S <= L)
        {
            long peer = a.allocate(S, group);
            if (peer <= 0) throw new IllegalStateException("bad peer " + peer);
            touch(peer, S);
            n++;
        }
        long used = pool.offHeap.used(), owns = a.offHeap().owns();
        long[] rs = regionStats(a);
        long rss1 = rssAnon();
        long[] mdl = model(n, S);
        reading("n", n); reading("used", used); reading("owns", owns); reading("limit", L);
        reading("usedRatio", pool.offHeap.usedRatio());
        reading("capacity_sum", rs[0]); reading("regions", rs[1]); reading("rss_delta", rss1 - rss0);
        reading("nmt_after", nmtOther());
        reading("cleaner_calls", cleans.get());
        reading("onHeap_used", pool.onHeap.used());
        long excess = rs[0] - used;
        reading("excess", excess);
        check("fill-reached-limit", used + S > L, "used=" + used + " S=" + S + " L=" + L);
        check("used-equals-n*S", used == n * S, "used=" + used + " n*S=" + n * S);
        check("used-le-L", used <= L, "used=" + used + " L=" + L);
        check("n-equals-floor(L/S)", n == L / S, "n=" + n + " L/S=" + (L / S));
        check("owns-equals-used", owns == used, "owns=" + owns + " used=" + used);
        check("capacity>=used", rs[0] >= used, "cap=" + rs[0] + " used=" + used);
        long lastCap = lastCapacity(a);
        if (S <= MAX_CLONED) check("excess<(regions-1)*S+lastCapacity", excess < (rs[1] - 1) * (long) S + lastCap && lastCap <= MIB, "excess=" + excess + " bound=" + ((rs[1] - 1) * (long) S + lastCap) + " lastCap=" + lastCap);
        if (S == MAX_CLONED) check("S=128KiB-excess-0", excess == 0, "excess=" + excess);
        if (S > MAX_CLONED) check("oversize-exact", excess == 0 && rs[1] == n, "excess=" + excess + " regions=" + rs[1] + " n=" + n);
        if (S == 100 * 1024) check("S=100KiB-excess-in[2.0pct,2.4pct+1MiB]", excess >= 0.02 * used && excess <= 0.024 * used + MIB, "excess/used=" + (double) excess / used);
        check("instrument-model-capacity", rs[0] == mdl[0] && rs[1] == mdl[1], "model cap=" + mdl[0] + " regions=" + mdl[1] + " real cap=" + rs[0] + " regions=" + rs[1]);
        long lo = used - MIB, hi = rs[0] + 4 * MIB;
        if (L >= 32 * MIB) check("rssAnon-delta-in[used-1MiB,cap+4MiB]", rss1 - rss0 >= lo && rss1 - rss0 <= hi, "delta=" + (rss1 - rss0) + " range=[" + lo + "," + hi + "]");
        else reading("rssAnon_band_not_applied_below_32MiB", "delta=" + (rss1 - rss0) + " range=[" + lo + "," + hi + "]");

        if (mode.equals("fill"))
        {
            NativeAllocator b = pool.newAllocator("t2");
            OpOrder.Group g2 = new OpOrder().start();
            AtomicReference<Throwable> err = new AtomicReference<>();
            Thread t = new Thread(() -> { try { b.allocate(S, g2); } catch (Throwable e) { err.set(e); } }, "extra");
            t.start();
            Thread.sleep(2000);
            Thread.State st = t.getState();
            reading("extra_state_2s", st);
            check("extra-allocate-parked", st == Thread.State.WAITING || st == Thread.State.TIMED_WAITING, "state=" + st);
            check("used-unchanged-while-parked", pool.offHeap.used() == used, "used=" + pool.offHeap.used());
            a.setDiscarding();
            reading("used_after_discarding", pool.offHeap.used());
            a.setDiscarded();
            t.join(10000);
            reading("extra_state_after_discard", t.getState());
            check("extra-completed-after-discard", !t.isAlive() && err.get() == null, "alive=" + t.isAlive() + " err=" + err.get());
            check("used==S-after-discard", pool.offHeap.used() == S, "used=" + pool.offHeap.used() + " S=" + S);
            reading("rss_after_discard_delta", rssAnon() - rss0);
        }
        else if (mode.equals("blocking"))
        {
            OpOrder o2 = new OpOrder();
            OpOrder.Group g = o2.start();
            OpOrder.Barrier bar = o2.newBarrier();
            bar.issue();
            bar.markBlocking();
            check("group-isBlocking", g.isBlocking(), "isBlocking=" + g.isBlocking());
            NativeAllocator c = pool.newAllocator("t3");
            final int K = 10;
            AtomicReference<Throwable> err = new AtomicReference<>();
            Thread t = new Thread(() -> { try { for (int i = 0; i < K; i++) c.allocate(S, g); } catch (Throwable e) { err.set(e); } }, "blocking-writer");
            t.start();
            t.join(5000);
            reading("blocking_writer_alive", t.isAlive());
            reading("used_after_blocking", pool.offHeap.used());
            check("blocking-group-not-parked", !t.isAlive() && err.get() == null, "alive=" + t.isAlive() + " err=" + err.get());
            check("blocking-group-exceeds-L", pool.offHeap.used() > L && pool.offHeap.used() == used + (long) K * S, "used=" + pool.offHeap.used() + " L=" + L + " expect=" + (used + (long) K * S));
            // a non-blocking group on a fresh allocator still parks
            NativeAllocator d = pool.newAllocator("t4");
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

    static void control(long L, int S, long heapLimit, MemtableCleaner cleaner, AtomicInteger cleans) throws Exception
    {
        SlabPool pool = new SlabPool(heapLimit, 0, 0.33f, cleaner);
        SlabAllocator a = (SlabAllocator) pool.newAllocator("t");
        OpOrder.Group group = new OpOrder().start();
        long n = L / S;
        for (long i = 0; i < n; i++) a.allocate(S, group);
        reading("n", n); reading("offHeap_used", pool.offHeap.used()); reading("onHeap_used", pool.onHeap.used());
        check("control-offHeap-stays-0", pool.offHeap.used() == 0, "offHeap=" + pool.offHeap.used());
        check("control-onHeap-charged", pool.onHeap.used() == n * S, "onHeap=" + pool.onHeap.used() + " n*S=" + n * S);
        AtomicReference<Throwable> err = new AtomicReference<>();
        OpOrder.Group g2 = new OpOrder().start();
        Thread t = new Thread(() -> { try { a.allocate(S, g2); } catch (Throwable e) { err.set(e); } }, "extra");
        t.start();
        t.join(2000);
        reading("extra_alive_2s", t.isAlive());
        check("control-no-blocking", !t.isAlive() && err.get() == null, "alive=" + t.isAlive());
        reading("cleaner_calls", cleans.get());
    }
}
