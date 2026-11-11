/*
 * Stage 4, unit tier mechanism (B2c-B2d, amended 2026-10-25) of
 * compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous. Not upstream.
 * Copy into test/unit/org/apache/cassandra/probe/ of the run clone; one `ant testsome` (own JVM) per arm, the knob and
 * file_cache_enabled set in test/conf/cassandra.yaml by unit-run.sh:
 *   ant testsome -Dtest.name=org.apache.cassandra.probe.ReadAheadProbeTest -Dtest.jvm.args="-Dstage4.out=<file> -Dstage4.label=<arm>"
 * Workload: LZ4 table, chunk 16 KiB (property stage4.chunk_kb, amendment D2: 256 in arm 256KiB-chunk256), compaction disabled, 16 rounds x 2,000 inserts of 4,096 random bytes (Random(42)), flush per
 * round. Then in this thread: an unrecorded warm-up cycle over all SSTables, the measured cycles k16 and k1, and an INFO point read.
 * A cycle: gc + 1 s; reading "before"; getScanner() on each SSTable, then hasNext()/next() once each; reading "open"; close all;
 * reading "closed". A reading = direct BufferPoolMXBean (MemoryUsed, Count, TotalCapacity) + this thread's read-ahead map
 * (ThreadLocalReadAheadBuffer.blockMap by reflection: entries with a non-null buffer, their capacity, isDirect, and whether the key
 * is a data file of this table: path contains "/<table directory name>/" and ends in -Data.db). Prints STAGE4 lines only; asserts nothing about the claim.
 */
package org.apache.cassandra.probe;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.TreeMap;

import org.junit.Test;

import io.netty.util.concurrent.FastThreadLocal;
import org.apache.cassandra.cache.ChunkCache;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.rows.UnfilteredRowIterator;
import org.apache.cassandra.io.sstable.ISSTableScanner;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.io.util.FileHandle;
import org.apache.cassandra.io.util.ThreadLocalReadAheadBuffer;

public class ReadAheadProbeTest extends CQLTester
{
    static PrintWriter out;
    static String label = System.getProperty("stage4.label", "?");

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

    @SuppressWarnings("unchecked")
    static Map<String, Object> blockMap() throws Exception
    {
        Field f = ThreadLocalReadAheadBuffer.class.getDeclaredField("blockMap");
        f.setAccessible(true);
        return ((FastThreadLocal<Map<String, Object>>) f.get(null)).get();
    }

    static Field blockBuffer;

    /** "live=<n> own=<n> caps=<sorted cap:count> direct=<all|not-all>" over this thread's map */
    static String mapReading(String tableDir) throws Exception
    {
        if (blockBuffer == null)
        {
            Class<?> blk = Class.forName("org.apache.cassandra.io.util.ThreadLocalReadAheadBuffer$Block");
            blockBuffer = blk.getDeclaredField("buffer");
            blockBuffer.setAccessible(true);
        }
        int live = 0, own = 0;
        boolean allDirect = true;
        TreeMap<Integer, Integer> caps = new TreeMap<>();
        for (Map.Entry<String, Object> e : blockMap().entrySet())
        {
            ByteBuffer b = (ByteBuffer) blockBuffer.get(e.getValue());
            if (b == null)
                continue;
            live++;
            if (e.getKey().contains("/" + tableDir + "/") && e.getKey().endsWith("-Data.db"))
                own++;
            caps.merge(b.capacity(), 1, Integer::sum);
            allDirect &= b.isDirect();
        }
        StringBuilder c = new StringBuilder();
        for (Map.Entry<Integer, Integer> e : caps.entrySet())
            c.append(c.length() == 0 ? "" : ",").append(e.getKey()).append('x').append(e.getValue());
        return "live=" + live + " own=" + own + " caps=[" + c + "] direct=" + (live == 0 ? "na" : allDirect ? "all" : "not-all");
    }

    static String pool()
    {
        BufferPoolMXBean d = direct();
        return "used=" + d.getMemoryUsed() + " count=" + d.getCount() + " cap=" + d.getTotalCapacity();
    }

    static long used()
    {
        return direct().getMemoryUsed();
    }

    static void settle() throws Exception
    {
        System.gc();
        Thread.sleep(1000);
    }

    void cycle(String phase, List<SSTableReader> ss, String tableDir, boolean record) throws Throwable
    {
        settle();
        long u0 = used();
        String r0 = pool() + " " + mapReading(tableDir);
        List<ISSTableScanner> scanners = new ArrayList<>();
        int partitions = 0;
        try
        {
            for (SSTableReader s : ss)
                scanners.add(s.getScanner());
            for (ISSTableScanner sc : scanners)
            {
                if (sc.hasNext())
                {
                    try (UnfilteredRowIterator p = sc.next())
                    {
                        partitions++;
                    }
                }
            }
            long u1 = used();
            String r1 = pool() + " " + mapReading(tableDir);
            for (ISSTableScanner sc : scanners)
                sc.close();
            scanners.clear();
            long u2 = used();
            String r2 = pool() + " " + mapReading(tableDir);
            if (record)
                line("STAGE4 cycle label=" + label + " phase=" + phase + " k=" + ss.size() + " partitions=" + partitions
                     + " d_open=" + (u1 - u0) + " d_close=" + (u1 - u2)
                     + " | before " + r0 + " | open " + r1 + " | closed " + r2);
        }
        finally
        {
            for (ISSTableScanner sc : scanners)
                sc.close();
        }
    }

    static String factoryClass(SSTableReader s) throws Exception
    {
        Field f = SSTableReader.class.getDeclaredField("dfile");
        f.setAccessible(true);
        FileHandle fh = (FileHandle) f.get(s);
        return fh.rebuffererFactory().getClass().getName().replaceFirst("^.*\\.", "");
    }

    @Test
    public void probe() throws Throwable
    {
        int chunkKb = Integer.getInteger("stage4.chunk_kb", 16);
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob) WITH compression = {'class':'LZ4Compressor','chunk_length_in_kb':" + chunkKb + "}");
        disableCompaction();
        Random r = new Random(42);
        int key = 0;
        for (int round = 0; round < 16; round++)
        {
            for (int i = 0; i < 2000; i++)
            {
                byte[] b = new byte[4096];
                r.nextBytes(b);
                execute("INSERT INTO %s (k, v) VALUES (?, ?)", key++, ByteBuffer.wrap(b));
            }
            flush();
        }
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        List<SSTableReader> ss = new ArrayList<>(cfs.getLiveSSTables());
        ss.sort(Comparator.comparing(s -> s.getFilename()));
        String tableDir = cfs.getDirectories().getDirectoryForNewSSTables().name();
        TreeMap<String, Integer> factories = new TreeMap<>();
        long bytesOnDisk = 0;
        for (SSTableReader s : ss)
        {
            factories.merge(factoryClass(s), 1, Integer::sum);
            bytesOnDisk += s.onDiskLength();
        }
        line("STAGE4 readback label=" + label + " B=" + DatabaseDescriptor.getCompressedReadAheadBufferSize()
             + " fileCacheEnabled=" + DatabaseDescriptor.getFileCacheEnabled() + " chunkCacheInstance=" + (ChunkCache.instance != null)
             + " diskAccessMode=" + DatabaseDescriptor.getDiskAccessMode() + " sstables=" + ss.size()
             + " chunkLength=" + ss.get(0).compression + "/" + ss.get(0).getCompressionMetadata().chunkLength()
             + " factories=" + factories + " dataBytesOnDisk=" + bytesOnDisk + " rows=" + key
             + " maxMemory=" + Runtime.getRuntime().maxMemory() + " tableDir=" + tableDir);

        cycle("warmup", ss, tableDir, false);
        cycle("k16", ss, tableDir, true);
        cycle("k1", ss.subList(0, 1), tableDir, true);

        settle();
        long u0 = used();
        String m0 = mapReading(tableDir);
        int rows = execute("SELECT v FROM %s WHERE k = ?", 5).size();
        long u1 = used();
        line("STAGE4 pointread label=" + label + " rows=" + rows + " d=" + (u1 - u0) + " | before " + m0 + " | after " + mapReading(tableDir));
        line("STAGE4 done label=" + label);
    }
}
