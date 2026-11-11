package org.apache.cassandra.utils.memory;

import java.io.BufferedReader;
import java.lang.reflect.Field;
import java.util.Collection;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.utils.concurrent.ImmediateFuture;
import org.apache.cassandra.utils.concurrent.OpOrder;

/**
 * Unit tier (B2) of max-region-size-region-allocate-capacity--autonomous (case file as amended 2026-10-26).
 * usage: java ... RegionCapProbe <fill|threads|limit> <N or L MiB> <s>
 *   fill    N s   : one NativeAllocator on a never-binding 1 GiB pool, N allocations of s bytes (every page written), then the region
 *                   structure by reflection. Works on any build; MAX_REGION_SIZE is read from the loaded class.
 *   threads N s   : the same with 8 threads (CAS races stash regions in RACE_ALLOCATED); reads the stash by reflection.
 *   limit   L s   : pool L MiB; fill with a non-blocking group to the limit, a parked extra allocation (positive control), then a blocking
 *                   group overshoots (case E).
 * Output: "STAGE4 reading k=v" raw lines and "STAGE4 check <name> ok|MISMATCH <detail>" lines. One scenario per JVM (static RACE_ALLOCATED).
 */
public class RegionCapProbe
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

    static int maxRegionSize() throws Exception
    {
        Field f = NativeAllocator.class.getDeclaredField("MAX_REGION_SIZE");
        f.setAccessible(true);
        return f.getInt(null);
    }

    /** the region-size rule of NativeAllocator.allocate/trySwapRegion (:144-168) replayed for n allocations of s bytes: {capacity sum, regions, max capacity} */
    static long[] model(long n, int s, int max)
    {
        if (s > MAX_CLONED) return new long[]{ n * s, n, s };
        long cap = 0, regions = 0, off = 0, cur = 0, mx = 0;
        for (long i = 0; i < n; i++)
        {
            if (cur == 0 || off + s > cur)
            {
                long size = cur == 0 ? 8192 : cur * 2;
                if (s > size) size = (long) Integer.highestOneBit(s) << 3;
                size = Math.min(max, size);
                cur = size; off = 0; cap += size; regions++; mx = Math.max(mx, size);
            }
            off += s;
        }
        return new long[]{ cap, regions, mx };
    }

    /** B2f literal values (case file as amended 2026-10-26): {capacity sum, regions}, keyed by max KiB, s; null where B2f gives none */
    static long[] expected(int maxKiB, int s, long n)
    {
        if (n == 2000000 && s == 100)
            return maxKiB == 256 ? new long[]{ 200269824L, 768 } : maxKiB == 1024 ? new long[]{ 200269824L, 197 } : maxKiB == 4096 ? new long[]{ 201318400L, 56 } : null;
        if (n == 1000 && s == 100000)
            return maxKiB == 256 ? new long[]{ 131072000L, 500 } : maxKiB == 1024 ? new long[]{ 105381888L, 101 } : maxKiB == 4096 ? new long[]{ 104333312L, 27 } : null;
        if (n == 1000 && s == 131072)
            return maxKiB == 256 ? new long[]{ 131072000L, 500 } : maxKiB == 1024 ? new long[]{ 131072000L, 125 } : maxKiB == 4096 ? new long[]{ 133169152L, 33 } : null;
        if (n == 1000 && s == 131073) return new long[]{ 131073000L, 1000 };
        return null;
    }

    static void touch(long peer, int s)
    {
        for (int o = 0; o < s; o += 4096) MemoryUtil.setByte(peer + o, (byte) 1);
        MemoryUtil.setByte(peer + s - 1, (byte) 1);
    }

    static long[] regionStats(NativeAllocator a) throws Exception
    {
        Field rf = NativeAllocator.class.getDeclaredField("regions");
        rf.setAccessible(true);
        Collection<?> regions = (Collection<?>) rf.get(a);
        long cap = 0, mx = 0;
        for (Object r : regions)
        {
            Field cf = r.getClass().getDeclaredField("capacity");
            cf.setAccessible(true);
            int c = cf.getInt(r);
            cap += c; mx = Math.max(mx, c);
        }
        return new long[]{ cap, regions.size(), mx };
    }

    static MemtableCleaner stubCleaner(AtomicInteger cleans)
    {
        // throttled: unthrottled, MemtableCleanerThread spins on needsCleaning() and its garbage enters the RssAnon reading
        return () -> { cleans.incrementAndGet(); try { Thread.sleep(50); } catch (InterruptedException e) { Thread.currentThread().interrupt(); } return ImmediateFuture.success(false); };
    }

    public static void main(String[] args) throws Exception
    {
        String mode = args[0];
        long arg1 = Long.parseLong(args[1]);
        int S = Integer.parseInt(args[2]);
        if (System.getProperty("cassandra.config") != null) DatabaseDescriptor.daemonInitialization();
        AtomicInteger cleans = new AtomicInteger();
        int max = maxRegionSize();
        reading("mode", mode + " arg1=" + arg1 + " S=" + S);
        reading("MAX_REGION_SIZE", max);
        reading("MAX_CLONED_SIZE", MAX_CLONED);
        if (mode.equals("limit")) { limit(arg1 * MIB, S, stubCleaner(cleans), max); System.out.println("STAGE4 done mismatches=" + mismatches); System.exit(0); }

        long N = arg1;
        long L = 1024 * MIB;
        NativePool pool = new NativePool(1L << 30, L, 0.33f, stubCleaner(cleans));
        NativeAllocator a = pool.newAllocator("t");
        OpOrder order = new OpOrder();
        OpOrder.Group group = order.start();
        System.gc();
        long rss0 = rssAnon();
        int threads = mode.equals("threads") ? 8 : 1;
        Thread[] ts = new Thread[threads];
        AtomicReference<Throwable> err = new AtomicReference<>();
        for (int t = 0; t < threads; t++)
        {
            final long share = N / threads;
            ts[t] = new Thread(() -> { try { for (long i = 0; i < share; i++) touch(a.allocate(S, group), S); } catch (Throwable e) { err.set(e); } }, "w" + t);
        }
        for (Thread t : ts) t.start();
        for (Thread t : ts) t.join();
        check("workers-no-error", err.get() == null, String.valueOf(err.get()));
        long used = pool.offHeap.used(), owns = a.offHeap().owns();
        long[] rs = regionStats(a);
        long rss1 = rssAnon();
        long[] mdl = model(N, S, max);
        reading("n", N); reading("used", used); reading("owns", owns);
        reading("capacity_sum", rs[0]); reading("regions", rs[1]); reading("max_capacity", rs[2]);
        reading("slack", rs[0] - used);
        reading("slack_pct", String.format("%.3f", 100.0 * (rs[0] - used) / used));
        reading("rss_delta", rss1 - rss0);
        reading("onHeap_used", pool.onHeap.used());
        check("used-equals-n*S", used == N * S, "used=" + used + " n*S=" + N * S);
        check("owns-equals-used", owns == used, "owns=" + owns + " used=" + used);
        check("used-independent-of-region-constant", used == N * S, "MAX_REGION_SIZE=" + max);
        check("sum>=used", rs[0] >= used, "cap=" + rs[0] + " used=" + used);
        check("max-capacity-equals-constant-or-oversize", rs[2] == (S > MAX_CLONED ? S : max), "max=" + rs[2] + " MAX_REGION_SIZE=" + max + " S=" + S);
        check("sum-capacity-grows-past-one-region", rs[0] > max && rs[1] > 1, "cap=" + rs[0] + " regions=" + rs[1]);
        long lo = used - MIB, hi = rs[0] + 4 * MIB;
        check("rssAnon-delta-in[used-1MiB,cap+4MiB]", rss1 - rss0 >= lo && rss1 - rss0 <= hi, "delta=" + (rss1 - rss0) + " range=[" + lo + "," + hi + "]");
        if (mode.equals("fill"))
        {
            check("instrument-model-capacity", rs[0] == mdl[0] && rs[1] == mdl[1] && rs[2] == mdl[2], "model cap=" + mdl[0] + " regions=" + mdl[1] + " max=" + mdl[2] + " real cap=" + rs[0] + " regions=" + rs[1] + " max=" + rs[2]);
            long[] ex = expected(max / 1024, S, N);
            if (ex != null) check("B2f-literal-capacity-and-regions", rs[0] == ex[0] && rs[1] == ex[1], "B2f cap=" + ex[0] + " regions=" + ex[1] + " real cap=" + rs[0] + " regions=" + rs[1]);
            else reading("B2f_literal", "none for this combination");
            // dead tail of every abandoned region is uncharged: slack > 0 unless every region is filled exactly
            if (S <= MAX_CLONED && (long) S * (max / S) != max) check("slack-positive-uncharged", rs[0] - used > 0, "slack=" + (rs[0] - used));
            a.setDiscarding();
            a.setDiscarded();
            reading("used_after_discard", pool.offHeap.used());
            check("discard-releases-charge", pool.offHeap.used() == 0, "used=" + pool.offHeap.used());
        }
        else
        {
            check("capacity>=used-with-threads", rs[0] >= used, "cap=" + rs[0]);
            Field rf = NativeAllocator.class.getDeclaredField("RACE_ALLOCATED");
            rf.setAccessible(true);
            Map<?, ?> stash = (Map<?, ?>) rf.get(null);
            long stashBytes = 0; int maxPer = 0;
            StringBuilder sb = new StringBuilder();
            for (Map.Entry<?, ?> e : stash.entrySet())
            {
                Field sf = e.getValue().getClass().getDeclaredField("stash");
                sf.setAccessible(true);
                int sz = ((Collection<?>) sf.get(e.getValue())).size();
                maxPer = Math.max(maxPer, sz);
                stashBytes += (long) sz * (Integer) e.getKey();
                if (sz > 0) sb.append(e.getKey()).append(':').append(sz).append(' ');
            }
            reading("stash_nonempty", sb.toString().trim());
            reading("stash_bytes", stashBytes);
            check("stash<=8-per-size-class", maxPer <= 8, "max per class=" + maxPer);
            check("stash-bytes<=16MiB+", stashBytes <= 16 * MIB, "stashBytes=" + stashBytes);
        }
        System.out.println("STAGE4 done mismatches=" + mismatches);
        System.exit(0);
    }

    /** case E: the pool limit is the cap (positive control); a blocking group overshoots it */
    static void limit(long L, int S, MemtableCleaner cleaner, int max) throws Exception
    {
        NativePool pool = new NativePool(1L << 30, L, 0.33f, cleaner);
        NativeAllocator a = pool.newAllocator("t");
        OpOrder.Group group = new OpOrder().start();
        long n = 0;
        while (pool.offHeap.used() + S <= L) { touch(a.allocate(S, group), S); n++; }
        long used = pool.offHeap.used();
        long[] rs = regionStats(a);
        reading("n", n); reading("used", used); reading("limit", L); reading("capacity_sum", rs[0]); reading("regions", rs[1]);
        check("fill-reached-limit", used + S > L && used <= L, "used=" + used + " S=" + S + " L=" + L);
        check("used-equals-n*S", used == n * S, "used=" + used);
        check("owns-equals-used", a.offHeap().owns() == used, "owns=" + a.offHeap().owns());
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
        OpOrder o2 = new OpOrder();
        OpOrder.Group g = o2.start();
        OpOrder.Barrier bar = o2.newBarrier();
        bar.issue();
        bar.markBlocking();
        check("group-isBlocking", g.isBlocking(), "isBlocking=" + g.isBlocking());
        NativeAllocator c = pool.newAllocator("t3");
        final int K = 10;
        Thread tb = new Thread(() -> { try { for (int i = 0; i < K; i++) c.allocate(S, g); } catch (Throwable e) { err.set(e); } }, "blocking-writer");
        tb.start();
        tb.join(5000);
        reading("blocking_writer_alive", tb.isAlive());
        reading("used_after_blocking", pool.offHeap.used());
        check("blocking-group-not-parked", !tb.isAlive() && err.get() == null, "alive=" + tb.isAlive() + " err=" + err.get());
        check("blocking-group-exceeds-L", pool.offHeap.used() > L && pool.offHeap.used() == used + (long) K * S, "used=" + pool.offHeap.used() + " L=" + L);
        a.setDiscarding();
        a.setDiscarded();
        t.join(10000);
        reading("extra_state_after_discard", t.getState());
        check("extra-completed-after-discard", !t.isAlive(), "alive=" + t.isAlive());
    }
}
