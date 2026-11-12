/*
 * Stage-4 harness for file_cache_size-chunkcache-cachesize--autonomous, unit tier (case file B2c-B2e, amendment A3).
 * Copied into test/unit/org/apache/cassandra/cache/ of a local working tree by unit-run.sh; never into the repository's source.
 * Output: the file named by -Dfc.out (one line per record):
 *   CAPACITY,<cacheSize bytes> | CACHE_NULL
 *   SAMPLE,phase,reads,weighted,entries,misses,poolSize,poolOverflow,poolUsed,direct
 *   MAX,weighted,entries,poolSize,poolOverflow,poolUsed,direct
 *   FINAL,... (same columns as SAMPLE)
 * weighted/entries/misses come from ChunkCache.instance (-1 when the cache is null); pool* from BufferPools.forChunkCache();
 * direct = java.nio BufferPoolMXBean "direct" MemoryUsed (the JVM's direct memory).
 * Shakedown (-Dfc.shakedown=true) uses 4 partitions instead of 64 (instrument check, not a reading).
 */
package org.apache.cassandra.cache;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.Random;

import org.junit.Test;

import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.utils.memory.BufferPool;
import org.apache.cassandra.utils.memory.BufferPools;

public class ChunkCacheCapProbeTest extends CQLTester
{
    static final int BLOB = 16_384;
    static final int ROWS_PER_PARTITION = 200;
    static final int BATCHES = 4;

    PrintWriter out;
    BufferPoolMXBean direct;
    long[] max = new long[6];

    long direct()
    {
        return direct == null ? -1 : direct.getMemoryUsed();
    }

    void sample(String phase, long reads)
    {
        ChunkCache c = ChunkCache.instance;
        BufferPool p = BufferPools.forChunkCache();
        long w = c == null ? -1 : c.weightedSize();
        long e = c == null ? -1 : c.size();
        long m = c == null ? -1 : c.metrics.misses.getCount();
        long[] v = { w, e, p.sizeInBytes(), p.overflowMemoryInBytes(), p.usedSizeInBytes(), direct() };
        for (int i = 0; i < v.length; i++) max[i] = Math.max(max[i], v[i]);
        out.println(String.join(",", phase.equals("final") ? "FINAL" : "SAMPLE", phase, Long.toString(reads), Long.toString(w), Long.toString(e),
                                Long.toString(m), Long.toString(v[2]), Long.toString(v[3]), Long.toString(v[4]), Long.toString(v[5])));
        out.flush();
    }

    @Test
    public void probe() throws Throwable
    {
        int partitions = Boolean.getBoolean("fc.shakedown") ? 4 : 64;
        out = new PrintWriter(new FileWriter(System.getProperty("fc.out", "build/test/fc-unit.txt"), false));
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct")) direct = b;
        try
        {
            out.println(ChunkCache.instance == null ? "CACHE_NULL" : "CAPACITY," + ChunkCache.instance.capacity());
            out.println("POOL_THRESHOLD," + BufferPools.forChunkCache().memoryUsageThreshold());
            out.println("HEAPMAX," + Runtime.getRuntime().maxMemory() + ",MaxDirectMemorySizeFlag," + ManagementFactory.getPlatformMXBean(com.sun.management.HotSpotDiagnosticMXBean.class).getVMOption("MaxDirectMemorySize").getValue());
            createTable("CREATE TABLE %s (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression = {'class':'LZ4Compressor','chunk_length_in_kb':'16'}");
            disableCompaction();
            Random r = new Random(42);
            byte[] b = new byte[BLOB];
            int perBatch = partitions / BATCHES;
            for (int batch = 0; batch < BATCHES; batch++)
            {
                for (int pk = batch * perBatch; pk < (batch + 1) * perBatch; pk++)
                    for (int ck = 0; ck < ROWS_PER_PARTITION; ck++)
                    {
                        r.nextBytes(b);
                        execute("INSERT INTO %s (pk, ck, v) VALUES (?, ?, ?)", pk, ck, ByteBuffer.wrap(b.clone()));
                    }
                flush();
            }
            out.println("SSTABLES," + getCurrentColumnFamilyStore().getLiveSSTables().size()
                        + ",memtableLiveBytes," + getCurrentColumnFamilyStore().getTracker().getView().getCurrentMemtable().getLiveDataSize()
                        + ",onDiskBytes," + getCurrentColumnFamilyStore().metric.liveDiskSpaceUsed.getCount());
            sample("loaded", 0);
            long reads = 0;
            for (int pass = 1; pass <= 2; pass++)
            {
                for (int pk = 0; pk < partitions; pk++)
                    for (int ck = 0; ck < ROWS_PER_PARTITION; ck++)
                    {
                        if (execute("SELECT v FROM %s WHERE pk=? AND ck=?", pk, ck).size() != 1)
                            out.println("MISSING_ROW," + pk + "," + ck);
                        reads++;
                        if (reads % 256 == 0)
                            sample("pass" + pass, reads);
                    }
                sample("endpass" + pass, reads);
            }
            sample("final", reads);
            out.println("MAX," + max[0] + "," + max[1] + "," + max[2] + "," + max[3] + "," + max[4] + "," + max[5]);
        }
        finally
        {
            out.close();
        }
    }
}
