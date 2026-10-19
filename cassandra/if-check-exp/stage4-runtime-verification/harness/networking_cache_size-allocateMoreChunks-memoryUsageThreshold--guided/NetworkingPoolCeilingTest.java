/*
 * Stage 4, unit tier U2 and U3 of networking_cache_size-allocateMoreChunks-memoryUsageThreshold (case 9e). Not upstream.
 * Copy into test/unit/org/apache/cassandra/utils/memory/ of a clone at cassandra-5.0.9 and run
 *   ant testsome -Dtest.name=org.apache.cassandra.utils.memory.NetworkingPoolCeilingTest -Dtest.jvm.args=-Dstage4.out=<file>
 * U2: for T in {0, 4, 16, 20, 64, 100} MiB, new BufferPool("stage4-net-<T>", T, false) (as BufferPools builds the networking pool):
 *   frame-sized requests getAtLeast(131070) until the first non-pooled one; five more; tryGetAtLeast; puts; reuse.
 * U3: the recycle contrast, 64 MiB pools with recyclePartially false and true, 64 KiB buffers through a FIFO of 8.
 * Every comparison prints "STAGE4 check <pool> <name> expected=<e> got=<g> OK|MISMATCH" and is recorded; the test fails at the
 * end of its method if any check mismatched. "STAGE4 figures" lines carry the raw numbers.
 */
package org.apache.cassandra.utils.memory;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.Test;

import org.apache.cassandra.io.compress.BufferType;

import static org.junit.Assert.assertEquals;

public class NetworkingPoolCeilingTest
{
    static final long MIB = 1024L * 1024L;
    static final int FRAME = 131070;                                   // a full CRC frame's payload buffer (Flusher, FrameEncoderCrc)
    static final long MACRO = BufferPool.GlobalPool.MACRO_CHUNK_SIZE;  // 8 MiB
    static PrintWriter out;
    int mismatches = 0;

    static synchronized void line(String s)
    {
        System.out.println(s);
        try
        {
            if (out == null && System.getProperty("stage4.out") != null)
                out = new PrintWriter(new FileWriter(System.getProperty("stage4.out"), true), true);
        }
        catch (IOException e)
        {
            throw new RuntimeException(e);
        }
        if (out != null)
            out.println(s);
    }

    void check(String pool, String name, long expected, long got)
    {
        boolean ok = expected == got;
        if (!ok)
            mismatches++;
        line("STAGE4 check " + pool + " " + name + " expected=" + expected + " got=" + got + (ok ? " OK" : " MISMATCH"));
    }

    static long pooled(BufferPool p)
    {
        return p.sizeInBytes() - p.overflowMemoryInBytes();
    }

    static void figures(String pool, String step, BufferPool p)
    {
        line("STAGE4 figures " + pool + " " + step + " size=" + p.sizeInBytes() + " overflow=" + p.overflowMemoryInBytes() + " pooled=" + pooled(p)
             + " used=" + p.usedSizeInBytes() + " hits=" + p.metrics.hits.getCount() + " misses=" + p.metrics.misses.getCount()
             + " capacity=" + p.memoryUsageThreshold());
    }

    void u2(long mib)
    {
        String name = "stage4-net-" + mib;
        long T = mib * MIB;
        long Tq = (T / MACRO) * MACRO;
        BufferPool p = new BufferPool(name, T, false);
        check(name, "U2.capacity", T, p.memoryUsageThreshold());
        // 1: take frame-sized buffers, holding every one, until the first that is not a pooled 131,072-B slice
        List<ByteBuffer> held = new ArrayList<>();
        ByteBuffer first;
        while (true)
        {
            ByteBuffer b = p.getAtLeast(FRAME, BufferType.OFF_HEAP);
            if (b.capacity() != BufferPool.NORMAL_CHUNK_SIZE)
            {
                first = b;
                break;
            }
            held.add(b);
            if (held.size() > 100_000)
                throw new AssertionError("no overflow after 100,000 buffers");
        }
        figures(name, "1-first-overflow", p);
        check(name, "U2.1 pooled = T' (floor(T / 8 MiB) x 8 MiB)", Tq, pooled(p));
        check(name, "U2.1 pooled buffers = 64 x T' / 8 MiB", 64 * Tq / MACRO, held.size());
        check(name, "U2.1 first other buffer capacity", FRAME, first.capacity());
        check(name, "U2.1 overflow = 131,070", FRAME, p.overflowMemoryInBytes());
        long misses1 = p.metrics.misses.getCount();
        // 2: five more
        List<ByteBuffer> extra = new ArrayList<>();
        extra.add(first);
        int bad = 0;
        for (int i = 0; i < 5; i++)
        {
            ByteBuffer b = p.getAtLeast(FRAME, BufferType.OFF_HEAP);
            if (b == null || b.capacity() != FRAME || !b.isDirect())
                bad++;
            extra.add(b);
        }
        figures(name, "2-five-more", p);
        check(name, "U2.2 five more: each non-null, direct, capacity 131,070", 0, bad);
        check(name, "U2.2 overflow = 6 x 131,070", 6L * FRAME, p.overflowMemoryInBytes());
        check(name, "U2.2 Misses +5", misses1 + 5, p.metrics.misses.getCount());
        check(name, "U2.2 pooled unchanged", Tq, pooled(p));
        // 3: tryGetAtLeast sees the refusal
        ByteBuffer t = p.tryGetAtLeast(FRAME);
        check(name, "U2.3 tryGetAtLeast(131070) is null", 1, t == null ? 1 : 0);
        if (t != null)
            p.put(t);
        // 4: the six overflow buffers go back
        for (ByteBuffer b : extra)
            p.put(b);
        figures(name, "4-overflow-back", p);
        check(name, "U2.4 overflow 0", 0, p.overflowMemoryInBytes());
        // 5: all back, then the same count again: served from the kept slabs
        for (ByteBuffer b : held)
            p.put(b);
        figures(name, "5-all-back", p);
        check(name, "U2.5 pooled unchanged after all back", Tq, pooled(p));
        List<ByteBuffer> again = new ArrayList<>();
        int notPooled = 0;
        for (int i = 0; i < held.size(); i++)
        {
            ByteBuffer b = p.getAtLeast(FRAME, BufferType.OFF_HEAP);
            if (b.capacity() != BufferPool.NORMAL_CHUNK_SIZE)
                notPooled++;
            again.add(b);
        }
        figures(name, "5-again", p);
        check(name, "U2.5 the same count again is all pooled", 0, notPooled);
        check(name, "U2.5 pooled unchanged (no new slab)", Tq, pooled(p));
        check(name, "U2.5 overflow 0", 0, p.overflowMemoryInBytes());
        for (ByteBuffer b : again)
            p.put(b);
        p.releaseLocal();
    }

    @Test
    public void u2_ceiling()
    {
        for (long mib : new long[]{ 0, 4, 16, 20, 64, 100 })
            u2(mib);
        line("STAGE4 info u2_ceiling done, mismatches " + mismatches);
        assertEquals(0, mismatches);
    }

    /** Counts the pool's recycle events. */
    static class Counting implements BufferPool.Debug
    {
        final AtomicLong registerNormal = new AtomicLong(), acquire = new AtomicLong(), recycleNormal = new AtomicLong(), recyclePartial = new AtomicLong();
        public void registerNormal(BufferPool.Chunk chunk) { registerNormal.incrementAndGet(); }
        public void acquire(BufferPool.Chunk chunk) { acquire.incrementAndGet(); }
        public void recycleNormal(BufferPool.Chunk o, BufferPool.Chunk n) { recycleNormal.incrementAndGet(); }
        public void recyclePartial(BufferPool.Chunk chunk) { recyclePartial.incrementAndGet(); }
    }

    long[] u3(boolean partially, int fifo, int steps)
    {
        String name = "stage4-net-recycle-" + partially + "-fifo" + fifo;
        BufferPool p = new BufferPool(name, 64 * MIB, partially);
        Counting c = new Counting();
        p.debug(c, BufferPool.DebugLeaks.NO_OP);
        ArrayDeque<ByteBuffer> q = new ArrayDeque<>();
        for (int i = 0; i < steps; i++)
        {
            q.addLast(p.get(65536, BufferType.OFF_HEAP));
            if (q.size() > fifo)
                p.put(q.removeFirst());
        }
        figures(name, "u3-end-holding", p);
        long pooledEnd = pooled(p), overflowEnd = p.overflowMemoryInBytes();
        while (!q.isEmpty())
            p.put(q.removeFirst());
        line("STAGE4 figures " + name + " recycleNormal=" + c.recycleNormal.get() + " recyclePartial=" + c.recyclePartial.get()
             + " registerNormal=" + c.registerNormal.get() + " acquire=" + c.acquire.get() + " pooled=" + pooledEnd + " overflow=" + overflowEnd);
        p.releaseLocal();
        return new long[]{ c.recyclePartial.get(), pooledEnd, overflowEnd };
    }

    @Test
    public void u3_recycleContrast()
    {
        int fifo = 8;
        long[] t = u3(true, fifo, 20000);
        if (t[0] == 0)
        {
            fifo = 9;    // the pattern did not evict a part-used chunk: change the FIFO length and record it (9e U3); not a result
            line("STAGE4 info u3: recyclePartial 0 on the true pool at FIFO 8; FIFO changed to " + fifo);
            t = u3(true, fifo, 20000);
        }
        long[] f = u3(false, fifo, 20000);
        line("STAGE4 info u3 FIFO " + fifo + ": true pool recyclePartial " + t[0] + " pooled " + t[1] + "; false pool recyclePartial " + f[0] + " pooled " + f[1]);
        check("u3-false", "U3 recyclePartial 0 on the networking-like pool", 0, f[0]);
        check("u3-false", "U3 pooled 8 MiB at the end (one slab)", MACRO, f[1]);
        check("u3-false", "U3 overflow 0", 0, f[2]);
        check("u3-true", "U3 recyclePartial > 0 on the chunk-cache-like pool", 1, t[0] > 0 ? 1 : 0);
        check("u3-true", "U3 pooled above 8 MiB on the chunk-cache-like pool", 1, t[1] > MACRO ? 1 : 0);
        line("STAGE4 info u3_recycleContrast done, mismatches " + mismatches);
        assertEquals(0, mismatches);
    }
}
