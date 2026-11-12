package org.apache.cassandra.io.util;

import java.nio.file.Files;
import java.util.*;
import org.junit.*;
import org.apache.cassandra.cache.ChunkCache;
import org.apache.cassandra.config.*;
import org.apache.cassandra.io.compress.BufferType;
import org.apache.cassandra.utils.memory.BufferPools;

// Stage-4 harness for file_cache_size-chunkcache-weightedsize--autonomous: the test of case-file B2a, verbatim,
// plus the one "O05 EVID" line of audit amendment AM7 (after the FINAL line).
public class ChunkCacheCapTest
{
    static final int FCS = Integer.getInteger("fcs.mib", 64);           // knob: file_cache_size in MiB
    static final int FILE_MIB = Integer.getInteger("file.mib", 2 * FCS + 64);
    static final int HOLD = Integer.getInteger("hold.chunks", 0);       // chunks kept referenced (overshoot probe)
    static final int CHUNK = 65536;

    @BeforeClass
    public static void setup()
    {
        DatabaseDescriptor.daemonInitialization(() -> {
            Config c = DatabaseDescriptor.loadConfig();
            c.file_cache_enabled = true;
            c.file_cache_size = new DataStorageSpec.IntMebibytesBound(FCS);
            return c;
        });
    }

    @Test
    public void cap() throws Exception
    {
        if (FCS <= ChunkCache.RESERVED_POOL_SPACE_IN_MiB) { System.out.println("O05 instance=" + ChunkCache.instance); return; }
        File f = FileUtils.createTempFile("o05", ".bin");
        byte[] block = new byte[1 << 20]; new Random(5).nextBytes(block);
        try (java.io.OutputStream o = Files.newOutputStream(f.toPath()))
        { for (int i = 0; i < FILE_MIB; i++) o.write(block); }
        long max = 0; List<Rebufferer.BufferHolder> held = new ArrayList<>();
        try (ChannelProxy ch = new ChannelProxy(f))
        {
            RebuffererFactory rf = ChunkCache.maybeWrap(new SimpleChunkReader(ch, f.length(), BufferType.OFF_HEAP, CHUNK));
            Rebufferer rb = rf.instantiateRebufferer(false);
            for (int pass = 0; pass < 2; pass++)
                for (long pos = 0, i = 0; pos < f.length(); pos += CHUNK, i++)
                {
                    Rebufferer.BufferHolder h = rb.rebuffer(pos);
                    if (pass == 0 && i < HOLD) held.add(h); else h.release();
                    max = Math.max(max, ChunkCache.instance.weightedSize());
                    if (i % 256 == 0)
                        System.out.printf("O05 pass=%d i=%d w=%d entries=%d poolSize=%d overflow=%d%n", pass, i,
                                          ChunkCache.instance.weightedSize(), ChunkCache.instance.size(),
                                          BufferPools.forChunkCache().sizeInBytes(), BufferPools.forChunkCache().overflowMemoryInBytes());
                }
            System.out.printf("O05 FINAL fcs=%d cacheSize=%d maxW=%d w=%d entries=%d poolSize=%d overflow=%d held=%d%n",
                              FCS, ChunkCache.cacheSize, max, ChunkCache.instance.weightedSize(), ChunkCache.instance.size(),
                              BufferPools.forChunkCache().sizeInBytes(), BufferPools.forChunkCache().overflowMemoryInBytes(), held.size());
            System.out.printf("O05 EVID fcs=%d misses=%d requests=%d%n", FCS,
                              ChunkCache.instance.metrics.misses.getCount(), ChunkCache.instance.metrics.requests.getCount());
            held.forEach(Rebufferer.BufferHolder::release);
            ChunkCache.instance.invalidateFile(ch.filePath());
        }
        finally { f.tryDelete(); }
    }
}
