/*
 * Stage-4 harness, unit tier (B2) of file_cache_size-chunk_cache_eviction-weighted_size--autonomous.
 * Copied into test/unit/org/apache/cassandra/cache/ of the local copy only (unit-run.sh), removed afterwards.
 * F (file_cache_size, MiB) comes from env PROBE_FCS; output lines go to the file named by env PROBE_OUT (and stdout).
 */
package org.apache.cassandra.cache;

import java.io.PrintStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.StandardOpenOption;
import java.util.Random;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.io.util.FileHandle;
import org.apache.cassandra.io.util.FileUtils;
import org.apache.cassandra.io.util.RandomAccessReader;
import org.apache.cassandra.utils.memory.BufferPool;
import org.apache.cassandra.utils.memory.BufferPools;

public class ChunkCacheCapProbeTest
{
    static final int CHUNK = 65536;
    static final long FILE_BYTES = 256L << 20;
    static int F;
    static PrintStream out;

    @BeforeClass
    public static void init() throws Exception
    {
        F = Integer.parseInt(System.getenv().getOrDefault("PROBE_FCS", "64"));
        String o = System.getenv("PROBE_OUT");
        out = o == null ? System.out : new PrintStream(new java.io.FileOutputStream(o, true), true);
        DatabaseDescriptor.daemonInitialization(() -> {
            Config c = DatabaseDescriptor.loadConfig();
            c.file_cache_size = new DataStorageSpec.IntMebibytesBound(F);
            c.file_cache_enabled = true;
            return c;
        });
    }

    static void p(String s) { out.println(s); if (out != System.out) System.out.println(s); }

    @Test
    public void fill() throws Exception
    {
        p("PROBEINFO F=" + F + " getFileCacheSizeInMiB=" + DatabaseDescriptor.getFileCacheSizeInMiB()
          + " enabled=" + DatabaseDescriptor.getFileCacheEnabled() + " roundUp=" + DatabaseDescriptor.getFileCacheRoundUp()
          + " RESERVED=" + ChunkCache.RESERVED_POOL_SPACE_IN_MiB + " cacheSize=" + ChunkCache.cacheSize
          + " poolThreshold=" + BufferPools.forChunkCache().memoryUsageThreshold()
          + " maxHeap=" + Runtime.getRuntime().maxMemory());
        if (ChunkCache.instance == null)
        {
            p("PROBE F=" + F + " instance=null cacheSize=" + ChunkCache.cacheSize);
            return;
        }
        File f = FileUtils.createTempFile("ccprobe", ".bin");
        // same bytes for every F: seeded random, written in 1 MiB blocks
        try (FileChannel ch = FileChannel.open(f.toPath(), StandardOpenOption.WRITE))
        {
            Random r = new Random(42);
            byte[] blk = new byte[1 << 20];
            for (long w = 0; w < FILE_BYTES; w += blk.length)
            {
                r.nextBytes(blk);
                ByteBuffer bb = ByteBuffer.wrap(blk);
                while (bb.hasRemaining()) ch.write(bb);
            }
        }
        ChunkCache cc = ChunkCache.instance;
        BufferPool pool = BufferPools.forChunkCache();
        long maxW = 0, maxE = 0, maxPool = 0, reads = 0;
        long[] passMaxW = new long[2];
        long m0 = cc.metrics.misses.getCount();
        try (FileHandle fh = new FileHandle.Builder(f).withChunkCache(cc).bufferSize(CHUNK).complete();
             RandomAccessReader rd = fh.createReader())
        {
            long n = fh.dataLength() / CHUNK;
            p("PROBEFILE dataLength=" + fh.dataLength() + " chunks=" + n + " rebufferer=" + fh.rebuffererFactory().getClass().getName());
            long[] order = new long[(int) n];
            for (int i = 0; i < n; i++) order[i] = i;
            Random rnd = new Random(7);
            for (int i = (int) n - 1; i > 0; i--) { int j = rnd.nextInt(i + 1); long t = order[i]; order[i] = order[j]; order[j] = t; }
            byte[] b = new byte[CHUNK];
            for (int pass = 0; pass < 2; pass++)
            {
                for (int i = 0; i < n; i++)
                {
                    long pos = (pass == 0 ? i : order[i]) * (long) CHUNK;
                    rd.seek(pos);
                    rd.readFully(b);
                    reads++;
                    long w = cc.weightedSize();
                    maxW = Math.max(maxW, w);
                    passMaxW[pass] = Math.max(passMaxW[pass], w);
                    maxE = Math.max(maxE, cc.size());
                    maxPool = Math.max(maxPool, pool.sizeInBytes());
                }
                long misses = cc.metrics.misses.getCount() - m0;
                p(String.format("PROBEPASS F=%d pass=%d endW=%d passMaxW=%d endE=%d misses=%d evictions=%d poolSize=%d poolUsed=%d overflow=%d",
                                F, pass, cc.weightedSize(), passMaxW[pass], cc.size(), misses, misses - cc.size(),
                                pool.sizeInBytes(), pool.usedSizeInBytes(), pool.overflowMemoryInBytes()));
            }
            long misses = cc.metrics.misses.getCount() - m0;
            p(String.format("PROBE F=%d cap=%d maxW=%d maxE=%d poolSize=%d poolUsed=%d overflow=%d maxPoolSize=%d misses=%d evictions=%d hits=%d reads=%d",
                            F, cc.capacity(), maxW, maxE, pool.sizeInBytes(), pool.usedSizeInBytes(), pool.overflowMemoryInBytes(),
                            maxPool, misses, misses - cc.size(), cc.metrics.hits.getCount(), reads));
        }
        p(String.format("PROBEAFTERCLOSE F=%d W=%d E=%d poolSize=%d poolUsed=%d overflow=%d",
                        F, cc.weightedSize(), cc.size(), pool.sizeInBytes(), pool.usedSizeInBytes(), pool.overflowMemoryInBytes()));
        f.delete();
    }
}
