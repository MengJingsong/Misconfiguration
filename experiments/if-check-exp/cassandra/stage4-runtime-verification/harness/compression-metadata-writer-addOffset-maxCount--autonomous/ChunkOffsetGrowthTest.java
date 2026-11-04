package org.apache.cassandra.io.compress;

import java.io.IOException;
import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.io.util.Memory;
import org.apache.cassandra.schema.CompressionParams;

/**
 * Stage-4 harness, unit tier (B2) of compression-metadata-writer-addOffset-maxCount--autonomous (case file as amended 2026-10-26).
 * Drives CompressionMetadata.Writer.addOffset directly. One READING line per cell goes to ~/s4-cm-logs/unit-readings.txt; the
 * expectations are checked at the end so every cell is recorded even if one contradicts. Controls C1-C3 per B2h.
 * main(String[] {"c3"}) runs N=101 outside the test runner (java -ea / -da) for control C3.
 */
public class ChunkOffsetGrowthTest
{
    static final int[] CHUNKS = { 4096, 16384, 65536 };
    static final long[] NS = { 99, 100, 101, 200, 201, 1000, 65536, 100000, 10_000_000 };
    static final Path OUT = Paths.get(System.getProperty("user.home"), "s4-cm-logs", System.getProperty("cm.out", "unit-readings.txt"));
    final List<String> failures = new ArrayList<>();

    @BeforeClass
    public static void init()
    {
        DatabaseDescriptor.daemonInitialization();
    }

    static void log(String s) throws IOException
    {
        System.out.println(s);
        Files.write(OUT, (s + "\n").getBytes(StandardCharsets.UTF_8), StandardOpenOption.CREATE, StandardOpenOption.APPEND);
    }

    static Field field(Class<?> c, String n) throws Exception
    {
        Field f = c.getDeclaredField(n);
        f.setAccessible(true);
        return f;
    }

    static long rssAnonKb()
    {
        try
        {
            for (String l : Files.readAllLines(Paths.get("/proc/self/status")))
                if (l.startsWith("RssAnon:"))
                    return Long.parseLong(l.replaceAll("[^0-9]", ""));
        }
        catch (IOException e) { /* fall through */ }
        return -1;
    }

    /** The rule of the case file, written from the source (CompressionMetadata.java:366-368): start 100, double when count == maxCount. */
    static long expectedCapacity(long n)
    {
        long cap = 100;
        while (n > cap) cap *= 2;
        return cap;
    }

    void expect(boolean ok, String what)
    {
        if (!ok) failures.add(what);
    }

    void cell(CompressionParams params, int chunk, long n, boolean sampleRss) throws Exception
    {
        java.io.File dir = Files.createTempDirectory(Paths.get("/dev/shm"), "cmgrow").toFile();
        File ci = new File(new java.io.File(dir, "d-CompressionInfo.db"));
        Field fMax = field(CompressionMetadata.Writer.class, "maxCount");
        Field fCount = field(CompressionMetadata.Writer.class, "count");
        long capExp = expectedCapacity(n);
        String exception = "none";
        long maxCount = -1, count = -1, offBefore = -1, offAfter = -1, fileLen = -1, rss0 = rssAnonKb(), rss1 = -1, rss2 = -1, rssPeak = -1;
        int doublings = 0;
        AtomicBoolean stop = new AtomicBoolean();
        AtomicLong peak = new AtomicLong(rss0);
        Thread sampler = null;
        if (sampleRss)
        {
            sampler = new Thread(() -> {
                while (!stop.get())
                {
                    peak.accumulateAndGet(rssAnonKb(), Math::max);
                    try { Thread.sleep(5); } catch (InterruptedException e) { return; }
                }
            });
            sampler.setDaemon(true);
            sampler.start();
        }
        CompressionMetadata.Writer w = CompressionMetadata.Writer.open(params, ci);
        try
        {
            long prevMax = fMax.getInt(w);
            for (long i = 0; i < n; i++)
            {
                w.addOffset(i * chunk);
                int mc = fMax.getInt(w);
                if (mc != prevMax)
                {
                    doublings++;
                    if (mc != 2 * prevMax)
                        failures.add("n=" + n + " maxCount went " + prevMax + " -> " + mc + " at count " + fCount.getInt(w));
                    prevMax = mc;
                }
            }
            maxCount = fMax.getInt(w);
            count = fCount.getInt(w);
            rss1 = rssAnonKb();
            CompressionMetadata m = w.open(n * (long) chunk, n * (long) chunk + 16);
            offBefore = m.offHeapSize();
            m.close();
            w.finalizeLength(n * (long) chunk, (int) n).prepareToCommit();
            CompressionMetadata m2 = w.open(n * (long) chunk, n * (long) chunk + 16);
            offAfter = m2.offHeapSize();
            m2.close();
            rss2 = rssAnonKb();
            fileLen = Files.size(ci.toPath());
            w.commit();
        }
        catch (Throwable t)
        {
            exception = t.getClass().getName() + ": " + t.getMessage();
            try { w.abort(null); } catch (Throwable ignored) { /* best effort */ }
        }
        finally
        {
            stop.set(true);
            if (sampler != null) sampler.join();
            rssPeak = peak.get();
            for (java.io.File f : dir.listFiles()) f.delete();
            dir.delete();
        }
        log(String.format("READING n=%d chunk=%d maxCount=%d count=%d doublings=%d offHeapBeforePrepare=%d offHeapAfterPrepare=%d ciFileBytes=%d exception=%s "
                          + "expMaxCount=%d expOffBefore=%d expOffAfter=%d rssAnonKb=%d/%d/%d peakKb=%d",
                          n, chunk, maxCount, count, doublings, offBefore, offAfter, fileLen, exception, capExp, capExp * 8, n * 8,
                          rss0, rss1, rss2, rssPeak));
        expect(exception.equals("none"), "n=" + n + " chunk=" + chunk + " exception " + exception);
        expect(maxCount == capExp, "n=" + n + " chunk=" + chunk + " maxCount " + maxCount + " != " + capExp);
        expect(count == n, "n=" + n + " count " + count);
        expect(offBefore == capExp * 8, "n=" + n + " chunk=" + chunk + " offHeap before prepare " + offBefore + " != " + capExp * 8);
        expect(offAfter == n * 8, "n=" + n + " chunk=" + chunk + " offHeap after prepare " + offAfter + " != " + n * 8);
    }

    @Test
    public void growth() throws Exception
    {
        log("RUN start " + java.time.Instant.now() + " assertionsEnabled=" + assertionsOn());
        for (int chunk : CHUNKS)
        {
            CompressionParams p = CompressionParams.lz4(chunk);
            for (long n : NS)
                cell(p, chunk, n, n >= 10_000_000);
        }
        // C1: a genuinely fixed 800-byte region of the same type rejects the 101st long (needs -ea)
        String c1 = "none";
        Memory fixed = Memory.allocate(800);
        try
        {
            for (int i = 0; i < 100; i++) fixed.setLong(8L * i, i);   // the first 100 offsets fit
            fixed.setLong(800, 100);                                  // the 101st does not
        }
        catch (Throwable t)
        {
            c1 = t.getClass().getName() + ": " + t.getMessage();
        }
        finally
        {
            fixed.free();
        }
        log("READING control=C1 fixed800 101st-setLong=" + c1 + " assertionsEnabled=" + assertionsOn());
        expect(c1.startsWith("java.lang.AssertionError") && c1.contains("Illegal bounds [800..808); size: 800"), "C1 did not throw the expected AssertionError: " + c1);
        if (!failures.isEmpty())
        {
            log("FAILURES " + failures);
            Assert.fail(failures.toString());
        }
        log("ALL EXPECTATIONS HELD");
    }

    @SuppressWarnings("all")
    static boolean assertionsOn()
    {
        boolean on = false;
        assert on = true;
        return on;
    }

    /** Control C3: N=101 addOffset outside the test runner, with whatever -ea / -da the launcher gave. */
    public static void main(String[] args) throws Exception
    {
        init();
        ChunkOffsetGrowthTest t = new ChunkOffsetGrowthTest();
        log("C3 start assertionsEnabled=" + assertionsOn());
        t.cell(CompressionParams.lz4(16384), 16384, 101, false);
        log("C3 failures=" + t.failures);
        System.exit(t.failures.isEmpty() ? 0 : 1);
    }
}
