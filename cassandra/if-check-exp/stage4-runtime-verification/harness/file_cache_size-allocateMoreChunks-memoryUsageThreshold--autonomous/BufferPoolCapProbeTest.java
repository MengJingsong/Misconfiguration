/*
 * Stage-4 harness, unit tier (B2 as amended 2026-10-27, U1-U3) of
 * file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous.
 * Copied into the run clone at test/unit/org/apache/cassandra/utils/memory/ by unit-run.sh and removed afterwards.
 *
 * One @Test per threshold T. unit-run.sh runs each method in its own JVM (ant testsome -Dtest.methods=...), because the
 * "Maximum memory usage reached" message goes through one static NoSpamLogger statement shared by every pool in a JVM
 * (BufferPool.java:135, 447; NoSpamLogger.java:212, 252), so only the first capped pool per 15 min would log (U2).
 * The tests assert nothing; each prints one FCSU line after the gets and one FCSU-AFTER line after the puts.
 */
package org.apache.cassandra.utils.memory;

import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

import org.junit.After;
import org.junit.Test;

import org.apache.cassandra.io.compress.BufferType;

public class BufferPoolCapProbeTest
{
    static final int REQ = 65536;          // B2c: 64 KiB per request
    static final int N_DEFAULT = 384;      // B2c: 384 x 64 KiB = 24 MiB
    static final int N_512 = 16384;        // U2: 16,384 x 64 KiB = 1 GiB, for T = 512 MiB

    private BufferPool pool;

    private void probe(long t, int n)
    {
        pool = new BufferPool("probe-" + t, t, false);
        // printed after the pool exists, so logging is initialised and the line reaches the TEST log (shakedown finding)
        System.out.println("FCSU-ENV T=" + t + " macroChunkSize=" + BufferPool.GlobalPool.MACRO_CHUNK_SIZE
                           + " normalChunkSize=" + BufferPool.NORMAL_CHUNK_SIZE
                           + " jvmArgs=" + String.join(" ", ManagementFactory.getRuntimeMXBean().getInputArguments()).replace(' ', '|'));
        List<ByteBuffer> held = new ArrayList<>(n);
        int served = 0;
        for (int i = 0; i < n; i++)
        {
            ByteBuffer b = pool.get(REQ, BufferType.OFF_HEAP);
            if (BufferPool.Chunk.getParentChunk(b) != null)
                served++;
            held.add(b);
        }
        long size = pool.sizeInBytes();
        long overflow = pool.overflowMemoryInBytes();
        long used = pool.usedSizeInBytes();
        System.out.println("FCSU T=" + t + " threshold=" + pool.memoryUsageThreshold() + " n=" + n + " demand=" + ((long) n * REQ)
                           + " size=" + size + " overflow=" + overflow + " pooled=" + (size - overflow) + " used=" + used
                           + " served=" + served + " unpooled=" + (n - served));
        for (ByteBuffer b : held)
            pool.put(b);
        held.clear();
        System.out.println("FCSU-AFTER T=" + t + " size=" + pool.sizeInBytes() + " overflow=" + pool.overflowMemoryInBytes()
                           + " used=" + pool.usedSizeInBytes());
    }

    @After
    public void tearDown()
    {
        if (pool != null)
        {
            pool.unsafeReset();   // U3(b): BufferPool has no unsafeFree(); unsafeReset() calls globalPool.unsafeFree() (BufferPool.java:1628-1635)
            pool = null;
        }
    }

    @Test public void t0()       { probe(0L, N_DEFAULT); }
    @Test public void t1_5MiB()  { probe(1572864L, N_DEFAULT); }
    @Test public void t4MiB()    { probe(4L << 20, N_DEFAULT); }
    @Test public void t8MiB()    { probe(8L << 20, N_DEFAULT); }
    @Test public void t16MiB()   { probe(16L << 20, N_DEFAULT); }
    @Test public void t512MiB()  { probe(512L << 20, N_512); }
}
