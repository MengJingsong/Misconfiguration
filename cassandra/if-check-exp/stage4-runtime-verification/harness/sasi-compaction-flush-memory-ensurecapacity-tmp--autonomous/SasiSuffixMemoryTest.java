/*
 * Stage-4 harness (not upstream code) for sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous, unit tier (B2).
 * Copied by unit-run.sh into test/unit/org/apache/cassandra/index/sasi/disk/ of a copy-source.sh tree.
 * One JVM runs one cell, selected by env STAGE4_CELL:
 *   p1                      Part 1: LongTimSort on n in {2^16, 2^20, 2^23} x {random, ascending, descending, runs}, STAGE4_REPEAT times each
 *   p2:<CONTAINS|PREFIX>:<M MiB>:<L chars>[:<repeat>]   Part 2: build an OnDiskIndexBuilder to the estimate crossing, then finish()
 * Env: STAGE4_OUT (output dir), STAGE4_TMP (scratch for the index file), STAGE4_SIZES (optional, p1 only: comma list of n, instrument check).
 * Writes $STAGE4_OUT/<cell>.csv (lines "P1,..." / "P2,key=value,...") and a Byteman trace elsewhere (-Dstage4.trace).
 */
package org.apache.cassandra.index.sasi.disk;

import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.SplittableRandom;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.BufferDecoratedKey;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.db.marshal.UTF8Type;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.utils.ByteBufferUtil;
import org.apache.cassandra.utils.LongTimSort;

public class SasiSuffixMemoryTest
{
    static final String ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

    @BeforeClass
    public static void setupDD()
    {
        DatabaseDescriptor.daemonInitialization();
    }

    static long threadAlloc()
    {
        return ((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId());
    }

    /** Live bytes: the total line of GC.class_histogram (it runs a full GC first), the same call as jcmd. */
    static long liveBytes() throws Exception
    {
        MBeanServer mbs = ManagementFactory.getPlatformMBeanServer();
        String text = (String) mbs.invoke(new ObjectName("com.sun.management:type=DiagnosticCommand"), "gcClassHistogram",
                                          new Object[]{ new String[0] }, new String[]{ String[].class.getName() });
        String last = null;
        for (String line : text.split("\n"))
            if (line.trim().startsWith("Total"))
                last = line.trim();
        if (last == null) throw new IllegalStateException("no Total line in class histogram");
        String[] f = last.split("\\s+");
        return Long.parseLong(f[2]);
    }

    @Test
    public void cell() throws Exception
    {
        String cell = System.getenv("STAGE4_CELL"), out = System.getenv("STAGE4_OUT"), tmp = System.getenv("STAGE4_TMP");
        if (cell == null || out == null || tmp == null) throw new IllegalStateException("STAGE4_CELL / STAGE4_OUT / STAGE4_TMP not set");
        new java.io.File(out).mkdirs(); new java.io.File(tmp).mkdirs();
        try (PrintWriter w = new PrintWriter(new java.io.FileWriter(out + "/" + cell.replace(':', '_') + ".csv", true), true))
        {
            if (cell.equals("p1")) part1(w);
            else if (cell.startsWith("p2:")) part2(w, cell.split(":"), tmp);
            else throw new IllegalArgumentException(cell);
        }
    }

    // ---------------- Part 1: the sort buffer against the array ----------------

    void part1(PrintWriter w)
    {
        int reps = Integer.parseInt(System.getenv().getOrDefault("STAGE4_REPEAT", "3"));
        String sizes = System.getenv("STAGE4_SIZES");
        int[] ns = sizes != null ? java.util.Arrays.stream(sizes.split(",")).mapToInt(Integer::parseInt).toArray()
                                 : new int[]{ 1 << 16, 1 << 20, 1 << 23 };
        String[] shapes = { "random", "ascending", "descending", "runs" };
        w.println("# P1 columns: seq,n,shape,rep,millis,thread_alloc_bytes,sorted_ok");
        int seq = 0;
        // warm-up (not recorded in the CSV; it does appear in the Byteman trace as sort number 0)
        sortOnce(1 << 14, "random", 99, w, -1);
        for (int n : ns)
            for (String shape : shapes)
                for (int r = 1; r <= reps; r++)
                    sortOnce(n, shape, r, w, ++seq);
    }

    void sortOnce(int n, String shape, int rep, PrintWriter w, int seq)
    {
        SplittableRandom rnd = new SplittableRandom(1000 + n + shape.hashCode() + rep);
        long[] a = new long[n];
        switch (shape)
        {
            case "random": for (int i = 0; i < n; i++) a[i] = rnd.nextLong(); break;
            case "ascending": for (int i = 0; i < n; i++) a[i] = i; break;
            case "descending": for (int i = 0; i < n; i++) a[i] = n - i; break;
            case "runs": // ascending runs of random length 100..1000, run bases random
            {
                int i = 0;
                while (i < n)
                {
                    int len = 100 + rnd.nextInt(901);
                    long base = rnd.nextLong(1L << 40);
                    for (int j = 0; j < len && i < n; j++) a[i++] = base + j;
                }
                break;
            }
            default: throw new IllegalArgumentException(shape);
        }
        long a0 = threadAlloc(), t0 = System.nanoTime();
        LongTimSort.sort(a, Long::compare);
        long ms = (System.nanoTime() - t0) / 1_000_000, alloc = threadAlloc() - a0;
        boolean ok = true;
        for (int i = 1; i < n; i++) if (a[i - 1] > a[i]) { ok = false; break; }
        if (seq >= 0) w.println(String.join(",", "P1", "" + seq, "" + n, shape, "" + rep, "" + ms, "" + alloc, "" + ok));
    }

    // ---------------- Part 2: the SASI segment build ----------------

    static DecoratedKey key(int i)
    {
        ByteBuffer k = ByteBufferUtil.bytes(String.format("key%08d", i));
        return new BufferDecoratedKey(new Murmur3Partitioner.LongToken(i * 7919L + 13), k);
    }

    void part2(PrintWriter w, String[] c, String tmp) throws Exception
    {
        OnDiskIndexBuilder.Mode mode = OnDiskIndexBuilder.Mode.valueOf(c[1]);
        long limit = Long.parseLong(c[2]) << 20;
        int L = Integer.parseInt(c[3]);
        int reps = c.length > 4 ? Integer.parseInt(c[4]) : 1;
        if (reps > 1) runBuild(mode, limit, L, tmp, -1, null); // warm-up on the same cell, not recorded
        for (int r = 1; r <= reps; r++)
            runBuild(mode, limit, L, tmp, r, w);
    }

    void runBuild(OnDiskIndexBuilder.Mode mode, long limit, int L, String tmp, int rep, PrintWriter w) throws Exception
    {
        SplittableRandom rnd = new SplittableRandom(42 + L + limit + rep);
        OnDiskIndexBuilder b = new OnDiskIndexBuilder(UTF8Type.instance, UTF8Type.instance, mode);
        long n = 0;
        byte[] buf = new byte[L];
        while (b.estimatedMemoryUse() < limit)           // the check of PerSSTableIndexWriter.java:247 (with its >= / <)
        {
            for (int i = 0; i < L; i++) buf[i] = (byte) ALPHABET.charAt(rnd.nextInt(ALPHABET.length()));
            int ki = (int) n;
            b.add(ByteBuffer.wrap(buf.clone()), key(ki), ki);
            n++;
        }
        long est = b.estimatedMemoryUse();
        long chars = n * L;
        File f = new File(tmp + "/idx-" + mode + "-" + (limit >> 20) + "-" + L + "-" + Math.max(rep, 0));
        long base = liveBytes();
        AtomicBoolean stop = new AtomicBoolean();
        AtomicLong peak = new AtomicLong(base);
        AtomicLong samples = new AtomicLong();
        Thread sampler = new Thread(() -> {
            try
            {
                while (!stop.get())
                {
                    long v = liveBytes();
                    samples.incrementAndGet();
                    if (v > peak.get()) peak.set(v);
                    for (int i = 0; i < 20 && !stop.get(); i++) Thread.sleep(100);
                }
            }
            catch (Exception e) { e.printStackTrace(); }
        }, "stage4-sampler");
        sampler.setDaemon(true);
        long a0 = threadAlloc(), t0 = System.nanoTime();
        System.out.println("S4 finish begin mode=" + mode + " M=" + (limit >> 20) + " L=" + L + " N=" + n + " chars=" + chars);
        sampler.start();
        boolean wrote = b.finish(f);
        long ms = (System.nanoTime() - t0) / 1_000_000, alloc = threadAlloc() - a0;
        stop.set(true); sampler.join();
        long fileLen = f.exists() ? f.length() : -1;
        f.tryDelete();
        if (w != null)
            w.println(String.join(",", "P2", "mode=" + mode, "M_mib=" + (limit >> 20), "L=" + L, "rep=" + rep, "N=" + n, "chars=" + chars,
                                  "estimate=" + est, "overshoot=" + (est - limit), "baseline_live=" + base, "peak_live=" + peak.get(),
                                  "increment=" + (peak.get() - base), "samples=" + samples.get(), "finish_ms=" + ms,
                                  "thread_alloc_bytes=" + alloc, "wrote=" + wrote, "file_len=" + fileLen));
    }
}
