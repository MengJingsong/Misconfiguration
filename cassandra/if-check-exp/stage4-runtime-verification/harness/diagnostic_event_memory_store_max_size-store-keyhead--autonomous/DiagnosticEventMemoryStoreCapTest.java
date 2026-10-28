/*
 * Stage-4 unit-tier probe for diagnostic_event_memory_store_max_size-store-keyhead--autonomous (B2).
 * Package org.apache.cassandra.diag.store: size() and setMaxSize() are package-private (DiagnosticEventMemoryStore.java:86, :92).
 * Prints STAGE4 lines "<kind> <name> expected=<..> got=<..> PASS|FAIL"; the test fails if any known-answer FAILs.
 */
package org.apache.cassandra.diag.store;

import java.io.Serializable;
import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.Test;

import org.apache.cassandra.diag.DiagnosticEvent;

import static org.junit.Assert.assertEquals;

public class DiagnosticEventMemoryStoreCapTest
{
    enum T { PAYLOAD }

    static final class PayloadEvent extends DiagnosticEvent
    {
        final byte[] payload;
        PayloadEvent(int n) { payload = new byte[n]; }
        public Enum<?> getType() { return T.PAYLOAD; }
        public Map<String, Serializable> toMap() { return new HashMap<>(); }
    }

    int fails = 0;

    void check(String name, long expected, long got)
    {
        boolean ok = expected == got;
        if (!ok) fails++;
        System.out.println("STAGE4 check " + name + " expected=" + expected + " got=" + got + (ok ? " PASS" : " FAIL"));
    }

    void checkRange(String name, long lo, long hi, long got)
    {
        boolean ok = got >= lo && got <= hi;
        if (!ok) fails++;
        System.out.println("STAGE4 check " + name + " expected=[" + lo + "," + hi + "] got=" + got + (ok ? " PASS" : " FAIL"));
    }

    static long usedAfterGc()
    {
        for (int i = 0; i < 3; i++) { System.gc(); try { Thread.sleep(50); } catch (InterruptedException e) {} }
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    static int live(List<WeakReference<DiagnosticEvent>> refs)
    {
        int n = 0;
        for (WeakReference<DiagnosticEvent> w : refs) if (w.get() != null) n++;
        return n;
    }

    @Test
    public void capTest() throws Exception
    {
        System.out.println("STAGE4 info maxMemory=" + Runtime.getRuntime().maxMemory());
        // warm-up (discarded)
        { DiagnosticEventMemoryStore w = new DiagnosticEventMemoryStore(); for (int i = 0; i < 20000; i++) w.store(new PayloadEvent(0)); }

        // Part 1: size follows m, key range, live refs (zero payload)
        for (int m : new int[]{ 1, 50, 200, 1000 })
        {
            int[] ns = new int[]{ m - 1, m, m + 1, 10 * m, 100000 };
            for (int n : ns)
            {
                if (n <= 0) continue;
                DiagnosticEventMemoryStore s = new DiagnosticEventMemoryStore();
                s.setMaxSize(m);
                List<WeakReference<DiagnosticEvent>> refs = new ArrayList<>();
                for (int i = 0; i < n; i++) { PayloadEvent e = new PayloadEvent(0); refs.add(new WeakReference<>(e)); s.store(e); }
                String tag = "m=" + m + ",N=" + n;
                long exp = Math.min(n, m);
                check("size " + tag, exp, s.size());
                check("lastKey " + tag, n, s.getLastEventId());
                NavigableMap<Long, DiagnosticEvent> all = s.scan(0L, 0);
                check("scan.size " + tag, exp, all.size());
                check("lowKey " + tag, n - exp + 1, all.firstKey());
                check("highKey " + tag, n, all.lastKey());
                all = null;
                usedAfterGc();
                int lv = live(refs);
                checkRange("liveRefs " + tag, exp, exp + 2, lv);
                System.out.println("STAGE4 reading part1 " + tag + " size=" + s.size() + " live=" + lv);
            }
        }

        // Part 2: 64 KiB payload; used heap above baseline at checkpoints, for m in {50,200,1000}; plus m=200 to 100000
        final int P = 64 * 1024;
        for (int m : new int[]{ 50, 200, 1000 })
        {
            long base = usedAfterGc();
            DiagnosticEventMemoryStore s = new DiagnosticEventMemoryStore();
            s.setMaxSize(m);
            List<WeakReference<DiagnosticEvent>> refs = new ArrayList<>();
            int[] cps = m == 200 ? new int[]{ 200, 400, 1000, 10000, 100000 } : new int[]{ m, 2 * m, 10000 };
            int i = 0;
            for (int cp : cps)
            {
                for (; i < cp; i++) { PayloadEvent e = new PayloadEvent(P); refs.add(new WeakReference<>(e)); s.store(e); }
                long used = usedAfterGc();
                long delta = used - base;
                long expB = (long) m * P;
                int lv = live(refs);
                System.out.println("STAGE4 reading part2 m=" + m + " N=" + cp + " size=" + s.size() + " live=" + lv + " deltaBytes=" + delta
                                   + " expectedBytes=" + expB + " ratio=" + String.format("%.3f", delta / (double) expB));
                check("size part2 m=" + m + ",N=" + cp, Math.min(cp, m), s.size());
                checkRange("live part2 m=" + m + ",N=" + cp, Math.min(cp, m), Math.min(cp, m) + 2, lv);
                if (cp >= m) checkRange("deltaBytes within 20% part2 m=" + m + ",N=" + cp, (long) (expB * 0.8), (long) (expB * 1.2 + 1_000_000), delta);
            }
        }

        // Part 3: concurrent, 8 threads x 20000, m=200
        {
            final DiagnosticEventMemoryStore s = new DiagnosticEventMemoryStore();
            s.setMaxSize(200);
            final AtomicBoolean done = new AtomicBoolean(false);
            final int[] max = { 0 };
            Thread mon = new Thread(() -> { while (!done.get()) { int z = s.size(); if (z > max[0]) max[0] = z; } });
            mon.start();
            Thread[] ts = new Thread[8];
            for (int t = 0; t < 8; t++) { ts[t] = new Thread(() -> { for (int i = 0; i < 20000; i++) s.store(new PayloadEvent(0)); }); ts[t].start(); }
            for (Thread t : ts) t.join();
            done.set(true); mon.join();
            check("lastKey concurrent", 160000, s.getLastEventId());
            checkRange("final size concurrent", 200, 208, s.size());
            System.out.println("STAGE4 reading part3 finalSize=" + s.size() + " monitorMax=" + max[0]);
            checkRange("monitor max concurrent", 199, 208, max[0]);
        }

        // Part 4: positive control, plain ConcurrentSkipListMap, no eviction, 64 KiB payload
        {
            long base = usedAfterGc();
            ConcurrentSkipListMap<Long, DiagnosticEvent> c = new ConcurrentSkipListMap<>();
            int i = 0;
            for (int cp : new int[]{ 1000, 5000 })
            {
                for (; i < cp; i++) c.put((long) i, new PayloadEvent(P));
                long delta = usedAfterGc() - base;
                System.out.println("STAGE4 reading part4 control N=" + cp + " size=" + c.size() + " deltaBytes=" + delta + " expectedBytes=" + (long) cp * P);
                check("control size N=" + cp, cp, c.size());
                checkRange("control deltaBytes N=" + cp, (long) (cp * (long) P * 0.9), (long) (cp * (long) P * 1.1 + 1_000_000), delta);
            }
        }
        assertEquals("known-answer failures", 0, fails);
    }
    /** Supplementary (added after run 1 showed the per-event WeakReference list itself costs ~36 B/event at N=100000):
     *  the same m=200, 64 KiB workload with no per-event reference list; heap only. */
    @Test
    public void payloadNoRefList() throws Exception
    {
        final int P = 64 * 1024;
        long base = usedAfterGc();
        DiagnosticEventMemoryStore s = new DiagnosticEventMemoryStore();
        s.setMaxSize(200);
        int i = 0;
        for (int cp : new int[]{ 200, 400, 1000, 10000, 100000 })
        {
            for (; i < cp; i++) s.store(new PayloadEvent(P));
            long delta = usedAfterGc() - base;
            System.out.println("STAGE4 reading part2b-noreflist m=200 N=" + cp + " size=" + s.size() + " deltaBytes=" + delta + " expectedBytes=" + 200L * P
                               + " ratio=" + String.format("%.3f", delta / (200.0 * P)));
            check("size part2b N=" + cp, Math.min(cp, 200), s.size());
            checkRange("deltaBytes within 20% part2b N=" + cp, (long) (200L * P * 0.8), (long) (200L * P * 1.2 + 1_000_000), delta);
        }
        assertEquals("known-answer failures", 0, fails);
    }
}
