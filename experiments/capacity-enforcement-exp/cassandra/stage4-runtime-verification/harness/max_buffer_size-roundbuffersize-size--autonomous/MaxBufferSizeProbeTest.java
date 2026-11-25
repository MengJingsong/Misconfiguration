package org.apache.cassandra.io.util;

import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import org.junit.BeforeClass;
import org.junit.Test;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.utils.memory.BufferPool;
import org.apache.cassandra.utils.memory.BufferPools;

// Case file B2a, with amendment A2 (chunkSize() read through ChunkReader).
public class MaxBufferSizeProbeTest
{
    static final long[] RECORD_SIZES = { 1000, 10000, 30000, 65536, 100000, 200000, 1L << 20, 16L << 20 };
    static final int K = 32;

    @BeforeClass
    public static void setup() { DatabaseDescriptor.daemonInitialization(); }

    @Test
    public void probe() throws Exception
    {
        File f = FileUtils.createTempFile("probe", ".db");
        byte[] data = new byte[4 << 20];               // 4 MiB > any buffer under test
        new Random(42).nextBytes(data);
        Files.write(f.toPath(), data);
        BufferPool pool = BufferPools.forChunkCache();
        System.out.println("PROBE MAX_BUFFER_SIZE=" + DiskOptimizationStrategy.MAX_BUFFER_SIZE);
        DiskOptimizationStrategy[] strategies = { new SsdDiskOptimizationStrategy(0.1), new SpinningDiskOptimizationStrategy() };
        for (DiskOptimizationStrategy s : strategies)
            for (long r : RECORD_SIZES)
            {
                int bufferSize = s.bufferSize(r);
                try (FileHandle fh = new FileHandle.Builder(f).mmapped(false).bufferSize(bufferSize).complete())
                {
                    long used0 = pool.usedSizeInBytes(), over0 = pool.overflowMemoryInBytes();
                    List<RandomAccessReader> readers = new ArrayList<>();
                    for (int i = 0; i < K; i++) { RandomAccessReader rr = fh.createReader(); rr.readByte(); readers.add(rr); }
                    long used1 = pool.usedSizeInBytes(), over1 = pool.overflowMemoryInBytes();
                    System.out.printf("PROBE strategy=%s r=%d bufferSize=%d chunk=%d bufCap=%d dUsed=%d dOverflow=%d perReader=%d%n",
                                      s.getClass().getSimpleName(), r, bufferSize, ((ChunkReader) fh.rebuffererFactory()).chunkSize(),
                                      readers.get(0).buffer.capacity(), used1 - used0, over1 - over0, (used1 - used0) / K);
                    for (RandomAccessReader rr : readers) rr.close();
                }
            }
        f.tryDelete();
    }
}
