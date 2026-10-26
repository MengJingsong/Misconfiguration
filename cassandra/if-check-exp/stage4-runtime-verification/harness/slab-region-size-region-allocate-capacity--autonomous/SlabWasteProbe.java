package org.apache.cassandra.utils.memory;

import java.io.BufferedReader;
import java.io.FileReader;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.util.Queue;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.utils.concurrent.ImmediateFuture;
import org.apache.cassandra.utils.concurrent.OpOrder;

/**
 * Unit tier (B2) of slab-region-size-region-allocate-capacity--autonomous (SlabAllocator.Region.allocate, line 201). One scenario per JVM.
 *   waste   <offheap|heap> <S> <N>            N single-thread allocations of S bytes, pool limits 2 GiB (the limit is not reached)
 *   limit   <offheap|heap> <L MiB> <S> <N>    a worker allocates N times, 5 s join; L is the limit of the charged counter
 *   threads <S> <rounds>                      rounds x (8 threads x 50 allocations of S, fresh allocator per round), offheap
 * REGION_SIZE is read from the loaded SlabAllocator class by reflection (1 MiB stock; a class directory ahead on the class path changes it).
 * Pool = SlabPool(heapLimit, offHeapLimit) as AbstractAllocatorMemtable.createMemtableAllocatorPoolInternal builds it for offheap_buffers /
 * heap_buffers (AbstractAllocatorMemtable.java:100-103); that class is not loaded because its static initialiser needs DatabaseDescriptor.
 * Direct-delta equalities allow 64 KiB (instrument-1 showed 3 bytes of unrelated small direct buffers; far below the 1 MiB of B2g).
 * Prints "STAGE4 reading k=v" (raw) and "STAGE4 check <name> ok|MISMATCH" (B2f of the case file as amended 2026-10-26, literals below).
 */
public class SlabWasteProbe
{
    static final long MIB = 1L << 20;
    static int mismatches = 0;
    /** the slices the memtable's cells would hold (a retired on-heap region lives only through its slices) */
    static final java.util.List<java.nio.ByteBuffer> KEEP = java.util.Collections.synchronizedList(new java.util.ArrayList<>());

    static void reading(String k, Object v) { System.out.println("STAGE4 reading " + k + "=" + v); }

    static void check(String name, boolean ok, String detail)
    {
        if (!ok) mismatches++;
        System.out.println("STAGE4 check " + name + (ok ? " ok " : " MISMATCH ") + detail);
    }

    static long rssAnon() throws Exception
    {
        try (BufferedReader r = new BufferedReader(new FileReader("/proc/self/status")))
        {
            for (String l; (l = r.readLine()) != null; )
                if (l.startsWith("RssAnon:")) return Long.parseLong(l.replaceAll("[^0-9]", "")) * 1024;
        }
        throw new IllegalStateException("no RssAnon");
    }

    static BufferPoolMXBean direct()
    {
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct")) return b;
        throw new IllegalStateException("no direct pool");
    }

    static Field field(String name) throws Exception
    {
        Field f = SlabAllocator.class.getDeclaredField(name);
        f.setAccessible(true);
        return f;
    }

    static int regionSize() throws Exception { return field("REGION_SIZE").getInt(null); }

    static int regionCount(SlabAllocator a) throws Exception { return ((AtomicInteger) field("regionCount").get(a)).get(); }

    static long unslabbed(SlabAllocator a) throws Exception { return ((AtomicLong) field("unslabbedSize").get(a)).get(); }

    @SuppressWarnings("unchecked")
    static int stash() throws Exception { return ((Queue<Object>) field("RACE_ALLOCATED").get(null)).size(); }

    /** rule of Region.allocate replayed for n allocations of s bytes, one thread: {regions} (independent of the code under test) */
    static long modelRegions(long n, int s, int cap)
    {
        if (s > 128 * 1024) return 0;
        long regions = 0, off = -1;
        for (long i = 0; i < n; i++)
            while (true)
            {
                if (off < 0) { regions++; off = 0; }
                long nw = off; off += s;
                if (nw + s <= cap) break;
                off = -1;
            }
        return regions;
    }

    static MemtableCleaner cleaner(AtomicInteger cleans)
    {
        // throttled stub: unthrottled, MemtableCleanerThread-style callers loop while needsCleaning() holds
        return () -> { cleans.incrementAndGet(); try { Thread.sleep(50); } catch (InterruptedException e) { Thread.currentThread().interrupt(); } return ImmediateFuture.success(false); };
    }

    static SlabPool pool(boolean off, long L, AtomicInteger cleans)
    {
        return off ? new SlabPool(2048 * MIB, L, 0.99f, cleaner(cleans)) : new SlabPool(L, 0, 0.99f, cleaner(cleans));
    }

    /** B2f table literals (capacity, S) -> regionCount, N = 400 */
    static long literalRegions(int cap, int s)
    {
        if (cap == 1 << 20) switch (s) { case 116509: return 50; case 131072: return 50; case 100000: return 40; case 4096: return 2; case 131073: return 0; }
        if (cap == 512 << 10) switch (s) { case 116509: return 100; case 100000: return 80; }
        if (cap == 2 << 20) switch (s) { case 116509: return 24; case 100000: return 20; }
        return -1;
    }

    public static void main(String[] args) throws Exception
    {
        String mode = args[0];
        if (System.getProperty("cassandra.config") != null) DatabaseDescriptor.daemonInitialization();
        int REG = regionSize();
        reading("mode", String.join(" ", args));
        reading("REGION_SIZE", REG);
        BufferPoolMXBean dp = direct();
        AtomicInteger cleans = new AtomicInteger();
        if (mode.equals("waste")) waste(args[1].equals("offheap"), Integer.parseInt(args[2]), Integer.parseInt(args[3]), REG, dp, cleans);
        else if (mode.equals("limit")) limit(args[1].equals("offheap"), Long.parseLong(args[2]) * MIB, Integer.parseInt(args[3]), Integer.parseInt(args[4]), REG, dp, cleans);
        else if (mode.equals("threads")) threads(Integer.parseInt(args[1]), Integer.parseInt(args[2]), REG, dp, cleans);
        else throw new IllegalArgumentException(mode);
        System.out.println("STAGE4 done mismatches=" + mismatches);
        System.exit(0);
    }

    static void waste(boolean off, int S, int N, int REG, BufferPoolMXBean dp, AtomicInteger cleans) throws Exception
    {
        SlabPool pool = pool(off, 2048 * MIB, cleans);
        SlabAllocator a = (SlabAllocator) pool.newAllocator("t");
        OpOrder.Group group = new OpOrder().start();
        System.gc(); System.gc();
        long rss0 = rssAnon(), d0 = dp.getMemoryUsed(), c0 = dp.getCount();
        Runtime rt = Runtime.getRuntime();
        long h0 = rt.totalMemory() - rt.freeMemory();
        for (int i = 0; i < N; i++) KEEP.add(a.allocate(S, group));
        long owns = (off ? a.offHeap() : a.onHeap()).owns(), used = off ? pool.offHeap.used() : pool.onHeap.used();
        int regions = regionCount(a);
        long unsl = unslabbed(a), real = (long) regions * REG + (S > 128 * 1024 ? unsl : 0);
        long dd = dp.getMemoryUsed() - d0, dc = dp.getCount() - c0, rss = rssAnon() - rss0;
        System.gc(); System.gc();
        long hd = rt.totalMemory() - rt.freeMemory() - h0;
        reading("owns", owns); reading("pool_used", used); reading("other_owns", (off ? a.onHeap() : a.offHeap()).owns());
        reading("regionCount", regions); reading("unslabbedSize", unsl); reading("real", real);
        reading("ratio_real_over_owns", String.format("%.5f", (double) real / owns));
        reading("direct_delta", dd); reading("direct_count_delta", dc); reading("rss_delta", rss); reading("heap_used_delta", hd); reading("stash", stash());
        check("owns-equals-N*S", owns == (long) N * S && used == owns, "owns=" + owns + " used=" + used + " N*S=" + (long) N * S);
        check("other-counter-0", (off ? a.onHeap() : a.offHeap()).owns() == 0, "other=" + (off ? a.onHeap() : a.offHeap()).owns());
        check("regionCount-equals-replay", regions == modelRegions(N, S, REG), "regionCount=" + regions + " replay=" + modelRegions(N, S, REG));
        if (N == 400 && literalRegions(REG, S) >= 0)
            check("regionCount-equals-B2f-table", regions == literalRegions(REG, S), "regionCount=" + regions + " table=" + literalRegions(REG, S));
        if (off)
        {
            // 1 MiB region = one direct buffer; oversize = one dedicated buffer per allocation
            long expDirect = S > 128 * 1024 ? (long) N * S : (long) regions * REG;
            long expCount = S > 128 * 1024 ? N : regions;
            check("direct-delta-equals-real", Math.abs(dd - expDirect) <= 65536 && Math.abs(dc - expCount) <= 2, "delta=" + dd + "/" + dc + " expect=" + expDirect + "/" + expCount);
            reading("rss_minus_direct", rss - expDirect);   // reading only: glibc reuses memory freed before the baseline, so RssAnon can be below the direct delta
            a.setDiscarding(); a.setDiscarded();
            long dda = dp.getMemoryUsed() - d0;
            reading("direct_delta_after_discard", dda);
            check("discard-releases-direct", Math.abs(dda - (long) stash() * REG) <= 65536, "delta=" + dda + " stash=" + stash());
        }
        else
        {
            check("heap-no-direct", Math.abs(dd) <= 65536 && Math.abs(dc) <= 2, "delta=" + dd + "/" + dc);
            if (S <= 128 * 1024)
                check("heap-retained-within-3MiB-of-real", Math.abs(hd - real) <= 3 * MIB, "heap_delta=" + hd + " real=" + real);
        }
    }

    static void limit(boolean off, long L, int S, int N, int REG, BufferPoolMXBean dp, AtomicInteger cleans) throws Exception
    {
        SlabPool pool = pool(off, L, cleans);
        SlabAllocator a = (SlabAllocator) pool.newAllocator("t");
        OpOrder.Group group = new OpOrder().start();
        System.gc(); System.gc();
        long d0 = dp.getMemoryUsed(), c0 = dp.getCount();
        Runtime rt = Runtime.getRuntime();
        long h0 = rt.totalMemory() - rt.freeMemory();
        AtomicInteger done = new AtomicInteger();
        Throwable[] err = new Throwable[1];
        Thread w = new Thread(() -> { try { for (int i = 0; i < N; i++) { KEEP.add(a.allocate(S, group)); done.incrementAndGet(); } } catch (Throwable e) { err[0] = e; } }, "limit-worker");
        w.start();
        w.join(5000);
        Thread.State st = w.getState();
        StackTraceElement[] stack = w.getStackTrace();
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < Math.min(8, stack.length); i++) sb.append(stack[i].getClassName().replace("org.apache.cassandra.", "")).append('.').append(stack[i].getMethodName()).append(':').append(stack[i].getLineNumber()).append(" < ");
        int n = done.get();
        long owns = (off ? a.offHeap() : a.onHeap()).owns();
        int regions = regionCount(a);
        long real = (long) regions * REG, dd = dp.getMemoryUsed() - d0;
        System.gc(); System.gc();
        long hd = rt.totalMemory() - rt.freeMemory() - h0;
        reading("limit_L", L); reading("worker_state", st); reading("worker_alive", w.isAlive()); reading("worker_stack", sb);
        reading("allocations_done", n); reading("owns", owns); reading("regionCount", regions); reading("real", real);
        reading("real_over_L", String.format("%.5f", (double) real / L)); reading("direct_delta", dd); reading("heap_used_delta", hd);
        reading("other_owns", (off ? a.onHeap() : a.offHeap()).owns()); reading("cleaner_calls", cleans.get());
        long expN = L / S;
        check("worker-stalled", w.isAlive() && (st == Thread.State.WAITING || st == Thread.State.TIMED_WAITING), "state=" + st + " done=" + n);
        check("stall-in-SubAllocator.allocate", sb.toString().contains("MemtableAllocator$SubAllocator.allocate"), sb.toString());
        check("done-equals-floor(L/S)", n == expN, "done=" + n + " floor(L/S)=" + expN);
        check("owns-equals-done*S-and-le-L", owns == (long) n * S && owns <= L, "owns=" + owns + " L=" + L);
        check("regionCount-equals-replay", regions == modelRegions(n, S, REG), "regionCount=" + regions + " replay=" + modelRegions(n, S, REG));
        if (REG == MIB && S == 116509 && L == 64 * MIB) check("B2f-limit-64-116509", n == 575 && owns == 66992675 && regions == 72 && real == 75497472, "n=" + n + " owns=" + owns + " regions=" + regions);
        if (REG == MIB && S == 116509 && L == 128 * MIB) check("B2f-limit-128-116509", n == 1151 && owns == 134101859 && regions == 144 && real == 150994944, "n=" + n + " owns=" + owns + " regions=" + regions);
        if (REG == MIB && S == 131072 && L == 64 * MIB) check("B2f-limit-64-131072", n == 512 && owns == 67108864 && regions == 64 && real == L, "n=" + n + " owns=" + owns + " regions=" + regions);
        if (off) check("direct-delta-equals-real", Math.abs(dd - real) <= 65536, "delta=" + dd + " real=" + real);
        else
        {
            check("heap-no-direct", Math.abs(dd) <= 65536, "delta=" + dd);
            check("heap-retained-within-3MiB-of-real", Math.abs(hd - real) <= 3 * MIB, "heap_delta=" + hd + " real=" + real);
        }
        a.setDiscarding(); a.setDiscarded();   // frees the pool; the worker then proceeds (not read)
    }

    static void threads(int S, int rounds, int REG, BufferPoolMXBean dp, AtomicInteger cleans) throws Exception
    {
        SlabPool pool = pool(true, 2048 * MIB, cleans);
        System.gc(); System.gc();
        long d0 = dp.getMemoryUsed();
        long sumRegions = 0;
        boolean allOwns = true, all50 = true;
        for (int r = 0; r < rounds; r++)
        {
            SlabAllocator a = (SlabAllocator) pool.newAllocator("t" + r);
            Thread[] ts = new Thread[8];
            for (int i = 0; i < 8; i++)
            {
                ts[i] = new Thread(() -> { OpOrder.Group g = new OpOrder().start(); for (int k = 0; k < 50; k++) a.allocate(S, g); }, "w" + i);
                ts[i].start();
            }
            for (Thread t : ts) t.join();
            long owns = a.offHeap().owns();
            int reg = regionCount(a);
            sumRegions += reg;
            allOwns &= owns == 400L * S;
            all50 &= reg == (int) modelRegions(400, S, REG);
            reading("round" + r, "owns=" + owns + " regionCount=" + reg + " stash=" + stash());
        }
        long dd = dp.getMemoryUsed() - d0;
        int st = stash();
        reading("sum_regionCount", sumRegions); reading("final_stash", st); reading("direct_delta", dd);
        check("owns-per-round-equals-400*S", allOwns, "S=" + S);
        check("regionCount-per-round-equals-replay", all50, "replay=" + modelRegions(400, S, REG));
        check("direct-delta-equals-(sum-regionCount+stash)*REGION_SIZE", Math.abs(dd - (sumRegions + st) * REG) <= 65536, "delta=" + dd + " expect=" + (sumRegions + st) * REG);
    }
}
