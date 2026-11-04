/*
 * Stage 4, unit tier B2 (as amended 2026-10-25) of
 * compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous. Not upstream.
 * The filed B2e skeleton, with the audit's additions: per-worker read-ahead map readout (B2d), the chunk-cache BufferPool
 * size at each reading (B2d), the reader's captured size (B2d), 2097151 (B2b), the stale-reader cycle (B2b/B2h), the gate
 * control (B2e), gc + 1 s before each cycle, barrier timeouts, worker join (B2e).
 * Copy to test/unit/org/apache/cassandra/io/util/ of the run clone; the clone's test yaml line 55 set to file_cache_enabled: false.
 *   ant testsome -Dtest.name=org.apache.cassandra.io.util.ReadAheadSetterTest -Dtest.jvm.args="-Dstage4.out=<file> -Dstage4.label=<rep>"
 * Properties: stage4.out, stage4.label, stage4.values (default 256,1024,4096,16384), stage4.shakedown=true (only the v cycles of
 * stage4.values; no rejections, no stale or gate control: a harness check, not a reading).
 * Prints STAGE4 lines only; asserts nothing about the claim.
 */
package org.apache.cassandra.io.util;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.TreeMap;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;

import org.junit.Test;

import io.netty.util.concurrent.FastThreadLocal;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.rows.UnfilteredRowIterator;
import org.apache.cassandra.io.sstable.Descriptor;
import org.apache.cassandra.io.sstable.ISSTableScanner;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.service.StorageService;
import org.apache.cassandra.utils.memory.BufferPools;

public class ReadAheadSetterTest extends CQLTester
{
    static PrintWriter out;
    static final String label = System.getProperty("stage4.label", "?");

    static synchronized void line(String s)
    {
        System.out.println(s);
        try
        {
            if (out == null && System.getProperty("stage4.out") != null)
                out = new PrintWriter(new FileWriter(System.getProperty("stage4.out"), true), true);
        }
        catch (java.io.IOException e)
        {
            throw new RuntimeException(e);
        }
        if (out != null)
            out.println(s);
    }

    static BufferPoolMXBean direct()
    {
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct"))
                return b;
        throw new IllegalStateException("no direct pool");
    }

    static long pool()
    {
        return BufferPools.forChunkCache().sizeInBytes();
    }

    static Object field(Object o, Class<?> c, String name) throws Exception
    {
        Field f = c.getDeclaredField(name);
        f.setAccessible(true);
        return f.get(o);
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> blockMap() throws Exception
    {
        return ((FastThreadLocal<Map<String, Object>>) field(null, ThreadLocalReadAheadBuffer.class, "blockMap")).get();
    }

    /** "entries=<n with buffer> own=<cap>:<direct>|none" for the calling thread */
    static String myMap(String dataFile) throws Exception
    {
        Class<?> blk = Class.forName("org.apache.cassandra.io.util.ThreadLocalReadAheadBuffer$Block");
        int n = 0;
        String own = "none";
        for (Map.Entry<String, Object> e : blockMap().entrySet())
        {
            ByteBuffer b = (ByteBuffer) field(e.getValue(), blk, "buffer");
            if (b == null)
                continue;
            n++;
            if (e.getKey().equals(dataFile))
                own = b.capacity() + ":" + (b.isDirect() ? "direct" : "heap");
        }
        return "entries=" + n + " own=" + own;
    }

    static FileHandle dfile(SSTableReader r) throws Exception
    {
        return (FileHandle) field(r, SSTableReader.class, "dfile");
    }

    /** factory class and the size captured by its ScanCompressedReader ("none" if it has none) */
    static String captured(SSTableReader r) throws Exception
    {
        Object f = dfile(r).rebuffererFactory();
        String cls = f.getClass().getName().replaceFirst("^.*\\.", "");
        if (!(f instanceof CompressedChunkReader.Standard))
            return "factory=" + cls + " captured=n/a";
        Object scan = field(f, CompressedChunkReader.Standard.class, "scanReader");
        if (scan == null)
            return "factory=" + cls + " captured=none";
        Object rab = field(scan, scan.getClass(), "readAheadBuffer");
        return "factory=" + cls + " captured=" + field(rab, ThreadLocalReadAheadBuffer.class, "bufferSize");
    }

    static String dataFile(SSTableReader r) throws Exception
    {
        return dfile(r).path();
    }

    void warm(SSTableReader r)
    {
        try (ISSTableScanner w = r.getScanner())
        {
            if (w.hasNext())
                w.next().close();
        }
    }

    void cycle(String tag, SSTableReader rd, int T) throws Throwable
    {
        BufferPoolMXBean d = direct();
        String df = dataFile(rd);
        System.gc();
        Thread.sleep(1000);
        CyclicBarrier open = new CyclicBarrier(T + 1), done = new CyclicBarrier(T + 1);
        List<String> workers = Collections.synchronizedList(new ArrayList<>());
        List<String> after = Collections.synchronizedList(new ArrayList<>());
        List<Throwable> errors = Collections.synchronizedList(new ArrayList<>());
        long m0 = d.getMemoryUsed(), c0 = d.getCount(), p0 = pool();
        List<Thread> ts = new ArrayList<>();
        for (int t = 0; t < T; t++)
        {
            Thread th = new Thread(() -> {
                try
                {
                    try (ISSTableScanner s = rd.getScanner())
                    {
                        if (s.hasNext())
                            try (UnfilteredRowIterator p = s.next()) {}
                        workers.add(myMap(df));
                        open.await(60, TimeUnit.SECONDS);
                        done.await(60, TimeUnit.SECONDS);
                    }
                    after.add(myMap(df));
                }
                catch (Throwable e)
                {
                    errors.add(e);
                }
            }, "stage4-worker-" + t);
            ts.add(th);
            th.start();
        }
        open.await(60, TimeUnit.SECONDS);
        long m1 = d.getMemoryUsed(), c1 = d.getCount(), p1 = pool();
        done.await(60, TimeUnit.SECONDS);
        Thread.sleep(500);
        for (Thread th : ts)
            th.join(10000);
        long m2 = d.getMemoryUsed(), p2 = pool();
        TreeMap<String, Integer> w = new TreeMap<>(), a = new TreeMap<>();
        for (String s : workers) w.merge(s, 1, Integer::sum);
        for (String s : after) a.merge(s, 1, Integer::sum);
        line("STAGE4 cycle label=" + label + " tag=" + tag + " T=" + T
             + " openDelta=" + (m1 - m0) + " countDelta=" + (c1 - c0) + " closedDelta=" + (m2 - m0)
             + " poolOpen=" + (p1 - p0) + " poolClosed=" + (p2 - p0)
             + " openDeltaC=" + ((m1 - m0) - (p1 - p0)) + " closedDeltaC=" + ((m2 - m0) - (p2 - p0))
             + " workers=" + w + " afterClose=" + a + " errors=" + errors.size()
             + (errors.isEmpty() ? "" : " firstError=" + errors.get(0)));
        if (!errors.isEmpty())
            throw new RuntimeException("worker failed", errors.get(0));
    }

    void insert20k() throws Throwable
    {
        Random r = new Random(1);
        for (int i = 0; i < 20000; i++)
        {
            byte[] b = new byte[1024];
            r.nextBytes(b);
            execute("INSERT INTO %s (k, v) VALUES (?, ?)", i, ByteBuffer.wrap(b));
        }
        flush();
    }

    static String getter()
    {
        return "getterKiB=" + DatabaseDescriptor.getCompressedReadAheadBufferSizeInKB();
    }

    void set(int v, String tag)
    {
        try
        {
            StorageService.instance.setCompressedReadAheadBufferInKB(v);
            line("STAGE4 set label=" + label + " tag=" + tag + " v=" + v + " ACCEPTED " + getter());
        }
        catch (RuntimeException e)
        {
            line("STAGE4 set label=" + label + " tag=" + tag + " v=" + v + " REJECTED " + e.getClass().getSimpleName() + " " + e.getMessage() + " " + getter());
        }
    }

    @Test
    public void setterAndBuffers() throws Throwable
    {
        boolean shakedown = Boolean.getBoolean("stage4.shakedown");
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob) WITH compression = {'class':'LZ4Compressor','chunk_length_in_kb':16}");
        insert20k();
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        SSTableReader live = cfs.getLiveSSTables().iterator().next();
        Descriptor d = live.descriptor;
        line("STAGE4 readback label=" + label + " sstables=" + cfs.getLiveSSTables().size()
             + " chunkLength=" + live.getCompressionMetadata().chunkLength() + " live " + captured(live)
             + " fileCacheEnabled=" + DatabaseDescriptor.getFileCacheEnabled() + " diskAccessMode=" + DatabaseDescriptor.getDiskAccessMode()
             + " " + getter() + " bytes=" + DatabaseDescriptor.getCompressedReadAheadBufferSize()
             + " maxMemory=" + Runtime.getRuntime().maxMemory() + " dataBytes=" + live.onDiskLength() + " shakedown=" + shakedown);

        if (!shakedown)
        {
            for (int bad : new int[]{ 0, 128, 255, 2097152 })
                set(bad, "reject");
            set(2097151, "max");
        }

        String vs = System.getProperty("stage4.values", "256,1024,4096,16384");
        for (String s : vs.split(","))
        {
            int v = Integer.parseInt(s.trim());
            set(v, "v" + v);
            SSTableReader rd = SSTableReader.open(cfs, d);
            try
            {
                line("STAGE4 reader label=" + label + " tag=v" + v + " " + captured(rd) + " " + getter());
                warm(rd);
                cycle("v" + v, rd, 1);
                cycle("v" + v, rd, 8);
            }
            finally
            {
                rd.selfRef().release();
            }
        }

        if (!shakedown)
        {
            // stale reader: the live reader, opened by the flush at the start-up value (256 KiB); knob now the last value set
            line("STAGE4 reader label=" + label + " tag=stale " + captured(live) + " " + getter());
            warm(live);
            cycle("stale", live, 8);

            // gate control: chunk 1024 KiB, knob 512 KiB
            createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob) WITH compression = {'class':'LZ4Compressor','chunk_length_in_kb':1024}");
            insert20k();
            ColumnFamilyStore cfs2 = getCurrentColumnFamilyStore();
            SSTableReader live2 = cfs2.getLiveSSTables().iterator().next();
            set(512, "gate");
            SSTableReader rd2 = SSTableReader.open(cfs2, live2.descriptor);
            try
            {
                line("STAGE4 reader label=" + label + " tag=gate chunkLength=" + rd2.getCompressionMetadata().chunkLength() + " sstables=" + cfs2.getLiveSSTables().size() + " " + captured(rd2) + " " + getter());
                warm(rd2);
                cycle("gate", rd2, 8);
            }
            finally
            {
                rd2.selfRef().release();
            }
        }
        line("STAGE4 done label=" + label);
    }
}
