// Stage-4 recheck (2026-11-17), native_transport_max_frame_size-decode-bytesToDiscard--autonomous: read-only helper called
// from the NTFMEM Byteman rule (ntfr.btm). Counts the native-transport pooled allocator's chunks and the 16 MiB buffers it holds:
// a chunk with no free bytes is one whole-chunk allocation (a stalled connection's cumulation of capacity = chunkSize), and an
// active huge allocation is a buffer larger than a chunk. Compiled by run.sh against the run copy's Netty jars, loaded with sys:.
package ntfr;

import io.netty.buffer.ByteBufAllocator;
import io.netty.buffer.PoolArenaMetric;
import io.netty.buffer.PoolChunkListMetric;
import io.netty.buffer.PoolChunkMetric;
import io.netty.buffer.PooledByteBufAllocator;
import io.netty.buffer.PooledByteBufAllocatorMetric;

public final class Probe
{
    private Probe() {}

    public static String pool(ByteBufAllocator a)
    {
        if (!(a instanceof PooledByteBufAllocator))
            return "probe=not-pooled";
        PooledByteBufAllocatorMetric m = ((PooledByteBufAllocator) a).metric();
        long chunks = 0, fullChunks = 0, chunkBytes = 0, freeBytes = 0, normal = 0, huge = 0, arenasWithChunks = 0;
        for (PoolArenaMetric am : m.directArenas())
        {
            normal += am.numActiveNormalAllocations();
            huge += am.numActiveHugeAllocations();
            long before = chunks;
            for (PoolChunkListMetric cl : am.chunkLists())
                for (PoolChunkMetric c : cl)
                {
                    chunks++;
                    chunkBytes += c.chunkSize();
                    freeBytes += c.freeBytes();
                    if (c.freeBytes() == 0)
                        fullChunks++;
                }
            if (chunks > before)
                arenasWithChunks++;
        }
        return "chunks=" + chunks + " fullChunks=" + fullChunks + " chunkBytes=" + chunkBytes + " chunkFreeBytes=" + freeBytes
               + " arenasWithChunks=" + arenasWithChunks + " activeNormal=" + normal + " activeHuge=" + huge
               + " held16=" + (fullChunks + huge);
    }
}
