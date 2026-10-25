/* Stage-4 unit-tier probe for entry-size-limit-serialize-serializedSize--autonomous (case file B2, as amended B2i).
 * Not upstream code. Lives only in the local test tree. Writes RESULT lines to $STAGE4_OUT/results.csv and per-arm RssAnon series. */
package org.apache.cassandra.cache;

import java.io.FileInputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintWriter;
import java.util.*;
import java.util.concurrent.*;

import org.junit.Test;

import org.apache.cassandra.io.ISerializer;
import org.apache.cassandra.io.util.DataInputPlus;
import org.apache.cassandra.io.util.DataOutputPlus;
import org.apache.cassandra.io.util.WrappedDataOutputStreamPlus;

public class SerializingCacheLimitTest
{
    static final long MiB = 1L << 20;
    static final byte[] FILL = new byte[(int) MiB];
    static { Arrays.fill(FILL, (byte) 0x5A); }

    static final class Blob
    {
        final long declared, toWrite; final CyclicBarrier barrier;
        Blob(long declared, long toWrite, CyclicBarrier barrier) { this.declared = declared; this.toWrite = toWrite; this.barrier = barrier; }
    }

    static final class BlobSer implements ISerializer<Blob>
    {
        public void serialize(Blob b, DataOutputPlus out) throws IOException
        {
            long left = b.toWrite;
            while (left > 0) { int n = (int) Math.min(left, FILL.length); out.write(FILL, 0, n); left -= n; }
            if (b.barrier != null)
                try { b.barrier.await(120, TimeUnit.SECONDS); } catch (Exception e) { throw new IOException(e); }
        }
        public Blob deserialize(DataInputPlus in) { throw new UnsupportedOperationException(); }
        public long serializedSize(Blob b) { return b.declared; }
    }

    // ---- RssAnon sampler ----
    static long rssAnonKb() throws IOException
    {
        byte[] buf = new byte[8192];
        int n;
        try (FileInputStream in = new FileInputStream("/proc/self/status")) { n = in.read(buf); }
        String s = new String(buf, 0, n);
        int i = s.indexOf("RssAnon:");
        int j = i + 8;
        while (s.charAt(j) == ' ' || s.charAt(j) == '\t') j++;
        int k = j; while (Character.isDigit(s.charAt(k))) k++;
        return Long.parseLong(s.substring(j, k));
    }

    static final class Sampler extends Thread
    {
        volatile boolean stop; volatile long peakKb; final long t0 = System.currentTimeMillis(); final StringBuilder series = new StringBuilder();
        Sampler() { setDaemon(true); }
        public void run()
        {
            while (!stop)
            {
                try { long v = rssAnonKb(); if (v > peakKb) peakKb = v; series.append(System.currentTimeMillis()).append(',').append(v).append('\n'); Thread.sleep(10); }
                catch (Exception e) { return; }
            }
        }
    }

    static PrintWriter RES; static String OUT;

    static long mib(long kb) { return kb / 1024; }

    interface Body { void run(Map<String, Object> m, Sampler s) throws Exception; }

    /** Runs one arm: baseline after gc+settle; body; settle; end_fill; cleanup; settle; end_clean. */
    static void arm(String name, Body body, Runnable cleanup) throws Exception
    {
        System.gc(); Thread.sleep(300);
        long heapBefore = Runtime.getRuntime().totalMemory();
        long base = rssAnonKb();
        Sampler s = new Sampler(); s.start();
        Map<String, Object> m = new LinkedHashMap<>();
        long t0 = System.currentTimeMillis();
        try { body.run(m, s); } catch (Throwable t) { m.put("body_exception", t.getClass().getName() + ": " + t.getMessage()); }
        Thread.sleep(400);
        long peak = s.peakKb; long endFill = rssAnonKb();
        m.put("wall_ms", System.currentTimeMillis() - t0);
        if (cleanup != null) cleanup.run();
        Thread.sleep(500);
        long endClean = rssAnonKb();
        s.stop = true; s.join();
        long heapAfter = Runtime.getRuntime().totalMemory();
        StringBuilder sb = new StringBuilder("RESULT arm=" + name + " base_MiB=" + mib(base) + " peak_delta_MiB=" + mib(peak - base)
            + " end_fill_delta_MiB=" + mib(endFill - base) + " end_clean_delta_MiB=" + mib(endClean - base)
            + " heap_total_before_MiB=" + heapBefore / MiB + " heap_total_after_MiB=" + heapAfter / MiB);
        for (Map.Entry<String, Object> e : m.entrySet()) sb.append(' ').append(e.getKey()).append('=').append(String.valueOf(e.getValue()).replace(' ', '_'));
        System.out.println(sb); RES.println(sb); RES.flush();
        try (PrintWriter p = new PrintWriter(OUT + "/series-" + name + ".csv")) { p.print(s.series); }
    }

    static SerializingCache<Integer, Blob> cache(long cap) { return SerializingCache.create(cap, new BlobSer()); }

    static void emptyByRemove(SerializingCache<Integer, Blob> c)
    {
        List<Integer> keys = new ArrayList<>();
        for (Iterator<Integer> it = c.keyIterator(); it.hasNext(); ) keys.add(it.next());
        for (Integer k : keys) c.remove(k);
    }

    static void cacheStats(Map<String, Object> m, SerializingCache<Integer, Blob> c, String p)
    {
        m.put(p + "weighted_MiB", c.weightedSize() / MiB); m.put(p + "weighted_B", c.weightedSize()); m.put(p + "size", c.size()); m.put(p + "capacity_MiB", c.capacity() / MiB);
    }

    @Test
    public void probe() throws Exception
    {
        OUT = System.getenv("STAGE4_OUT");
        new java.io.File(OUT).mkdirs();
        RES = new PrintWriter(new java.io.FileWriter(OUT + "/results.csv", true));
        String only = System.getenv("STAGE4_ARMS"); // comma list for a shakedown
        Set<String> sel = only == null ? null : new HashSet<>(Arrays.asList(only.split(",")));
        int scale = Integer.parseInt(System.getenv().getOrDefault("STAGE4_SCALE", "1")); // shakedown divisor for entry counts/sizes
        RES.println("# probe start " + new Date() + " scale=" + scale + " env MALLOC_ARENA_MAX=" + System.getenv("MALLOC_ARENA_MAX") + " MALLOC_MMAP_THRESHOLD_=" + System.getenv("MALLOC_MMAP_THRESHOLD_") + " MALLOC_TRIM_THRESHOLD_=" + System.getenv("MALLOC_TRIM_THRESHOLD_"));

        // W1: guard
        for (long[] g : new long[][]{{Integer.MAX_VALUE}, {1L << 31}, {(1L << 31) + 4096}})
        {
            String name = "guard_" + g[0];
            if (sel != null && !sel.contains("guard")) break;
            final SerializingCache<Integer, Blob> c = cache(64 * MiB);
            arm(name, (m, s) -> {
                try { c.put(1, new Blob(g[0], 0, null)); m.put("exception", "none"); }
                catch (Throwable t) { m.put("exception", t.getClass().getName()); m.put("message", "\"" + t.getMessage() + "\""); }
                Thread.sleep(100); cacheStats(m, c, "");
            }, () -> emptyByRemove(c));
        }
        // nocache control: the W2 loop into a discarding stream
        if (sel == null || sel.contains("nocache"))
            arm("nocache", (m, s) -> {
                BlobSer ser = new BlobSer(); WrappedDataOutputStreamPlus out = new WrappedDataOutputStreamPlus(OutputStream.nullOutputStream());
                for (int i = 0; i < 1024 / scale; i++) ser.serialize(new Blob(MiB, MiB, null), out);
            }, null);
        // W2: aggregate cap
        for (String a : new String[]{"agg64", "agg64_repeat", "agg128", "agg256"})
        {
            if (sel != null && !sel.contains("agg")) break;
            long cap = Long.parseLong(a.replaceAll("[^0-9]", "").isEmpty() ? "64" : a.replaceAll("_repeat", "").replaceAll("[^0-9]", "")) * MiB;
            final SerializingCache<Integer, Blob> c = cache(cap);
            arm(a, (m, s) -> {
                for (int i = 0; i < 1024 / scale; i++) c.put(i, new Blob(MiB, MiB, null));
                Thread.sleep(200); cacheStats(m, c, ""); m.put("offered_MiB", 1024 / scale);
            }, () -> emptyByRemove(c));
        }
        // shrink
        if (sel == null || sel.contains("shrink"))
        {
            final SerializingCache<Integer, Blob> c = cache(256 * MiB);
            arm("shrink256to128", (m, s) -> {
                for (int i = 0; i < 1024 / scale; i++) c.put(i, new Blob(MiB, MiB, null));
                Thread.sleep(200); cacheStats(m, c, "before_"); long b4 = rssAnonKb();
                c.setCapacity(128 * MiB); Thread.sleep(500);
                cacheStats(m, c, "after_"); m.put("rss_after_shrink_delta_vs_before_MiB", mib(rssAnonKb() - b4));
            }, () -> emptyByRemove(c));
        }
        // W3
        if (sel == null || sel.contains("over"))
        {
            final SerializingCache<Integer, Blob> c1 = cache(64 * MiB);
            arm("over1_512MiB", (m, s) -> { c1.put(1, new Blob(512 * MiB / scale, 512 * MiB / scale, null)); Thread.sleep(200); cacheStats(m, c1, ""); }, () -> emptyByRemove(c1));
            for (long sz : new long[]{256, 512})
            {
                final SerializingCache<Integer, Blob> c8 = cache(64 * MiB);
                arm("over8x" + sz + "MiB", (m, s) -> {
                    CyclicBarrier bar = new CyclicBarrier(8);
                    ExecutorService ex = Executors.newFixedThreadPool(8);
                    List<Future<?>> fs = new ArrayList<>();
                    for (int t = 0; t < 8; t++) { final int k = t; fs.add(ex.submit(() -> { c8.put(k, new Blob(sz * MiB / scale, sz * MiB / scale, bar)); return null; })); }
                    for (Future<?> f : fs) f.get(300, TimeUnit.SECONDS);
                    ex.shutdown(); Thread.sleep(200); cacheStats(m, c8, "");
                }, () -> emptyByRemove(c8));
            }
        }
        // W2big
        if (sel == null || sel.contains("big"))
        {
            final SerializingCache<Integer, Blob> cb = cache(3072 * MiB);
            arm("agg3072", (m, s) -> {
                for (int i = 0; i < 4096 / scale; i++) cb.put(i, new Blob(MiB, MiB, null));
                Thread.sleep(300); cacheStats(m, cb, ""); m.put("offered_MiB", 4096 / scale);
            }, () -> emptyByRemove(cb));
        }
        // clear() probe, last: leaks by design of the source under test
        if (sel == null || sel.contains("clear"))
        {
            final SerializingCache<Integer, Blob> cc = cache(64 * MiB);
            arm("clear_probe64", (m, s) -> {
                for (int i = 0; i < 1024 / scale; i++) cc.put(i, new Blob(MiB, MiB, null));
                Thread.sleep(200); cacheStats(m, cc, "before_"); long b4 = rssAnonKb(); m.put("rss_before_clear_kB", b4);
                cc.clear(); Thread.sleep(500); cacheStats(m, cc, "after_"); long af = rssAnonKb(); m.put("rss_after_clear_kB", af);
            }, null);
        }
        RES.println("# probe end " + new Date()); RES.close();
    }
}
