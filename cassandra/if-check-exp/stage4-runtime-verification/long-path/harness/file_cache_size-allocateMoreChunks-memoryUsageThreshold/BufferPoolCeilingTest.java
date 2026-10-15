/*
 * Stage 4, unit tier of file_cache_size-allocateMoreChunks-memoryUsageThreshold (case 9e unit step 2, amended 2026-10-14).
 * Copy into test/unit/org/apache/cassandra/utils/memory/ of a clone at cassandra-5.0.9 and run
 *   ant testsome -Dtest.name=org.apache.cassandra.utils.memory.BufferPoolCeilingTest -Dtest.jvm.args=-Dstage4.out=<file>
 * For each pool size (16, 20, 64, 100 MiB) it builds new BufferPool("stage4-<MiB>", bytes, true) and:
 *   1. takes floor(bytes / 8 MiB) * 64 direct buffers of 128 KiB (one normal chunk each): pooled = floor(bytes/8MiB) * 8 MiB, overflow 0;
 *   2. takes five more: each non-null and direct, overflow +5 * 128 KiB, pooled unchanged, Misses +5, Hits unchanged;
 *   3. tryGet(128 KiB) returns null, Misses +1;
 *   4. puts the five overflow buffers back: overflow 0;
 *   5. puts every buffer back: pooled unchanged (the reservation is never released), used 0.
 * Every comparison prints "STAGE4 check <pool> <name> expected=<e> got=<g> OK|MISMATCH" and is recorded, not thrown; the test fails at
 * the end if any check mismatched. "STAGE4 figures" lines carry the raw numbers.
 */
package org.apache.cassandra.utils.memory;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

import org.junit.AfterClass;
import org.junit.Test;

import org.apache.cassandra.io.compress.BufferType;

import static org.junit.Assert.assertEquals;

public class BufferPoolCeilingTest
{
    static final long MIB = 1024L * 1024L;
    static final int BUF = BufferPool.NORMAL_CHUNK_SIZE;              // 128 KiB
    static final long MACRO = BufferPool.GlobalPool.MACRO_CHUNK_SIZE; // 8 MiB
    static int checks = 0, mismatches = 0;
    static PrintWriter out;

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

    static void check(String pool, String name, long expected, long got)
    {
        checks++;
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

    void runPool(long mib)
    {
        String name = "stage4-" + mib;
        long bytes = mib * MIB;
        long ceiling = (bytes / MACRO) * MACRO;
        BufferPool p = new BufferPool(name, bytes, true);
        check(name, "capacity", bytes, p.memoryUsageThreshold());
        figures(name, "0-new", p);

        // step 1: fill the pool to its ceiling
        int n = (int) (ceiling / BUF);
        List<ByteBuffer> pooledBufs = new ArrayList<>(n);
        int nulls = 0, notDirect = 0;
        for (int i = 0; i < n; i++)
        {
            ByteBuffer b = p.get(BUF, BufferType.OFF_HEAP);
            if (b == null) nulls++;
            else if (!b.isDirect()) notDirect++;
            pooledBufs.add(b);
        }
        figures(name, "1-ceiling", p);
        check(name, "1.null_buffers", 0, nulls);
        check(name, "1.non_direct_buffers", 0, notDirect);
        check(name, "1.pooled_eq_floor_T_over_M_times_M", ceiling, pooled(p));
        check(name, "1.overflow", 0, p.overflowMemoryInBytes());
        check(name, "1.pooled_le_threshold", 1, pooled(p) <= bytes ? 1 : 0);
        long hits1 = p.metrics.hits.getCount(), misses1 = p.metrics.misses.getCount();
        check(name, "1.hits_eq_n", n, hits1);
        check(name, "1.misses", 0, misses1);

        // step 2: five more, past the ceiling
        List<ByteBuffer> extra = new ArrayList<>();
        nulls = 0; notDirect = 0;
        for (int i = 0; i < 5; i++)
        {
            ByteBuffer b = p.get(BUF, BufferType.OFF_HEAP);
            if (b == null) nulls++;
            else if (!b.isDirect()) notDirect++;
            extra.add(b);
        }
        figures(name, "2-past", p);
        check(name, "2.null_buffers", 0, nulls);
        check(name, "2.non_direct_buffers", 0, notDirect);
        check(name, "2.overflow_eq_5x128KiB", 5L * BUF, p.overflowMemoryInBytes());
        check(name, "2.pooled_unchanged", ceiling, pooled(p));
        check(name, "2.misses_plus5", misses1 + 5, p.metrics.misses.getCount());
        check(name, "2.hits_unchanged", hits1, p.metrics.hits.getCount());

        // step 3: tryGet sees the refusal
        ByteBuffer t = p.tryGet(BUF);
        figures(name, "3-tryget", p);
        check(name, "3.tryGet_null", 1, t == null ? 1 : 0);
        check(name, "3.misses_plus6", misses1 + 6, p.metrics.misses.getCount());
        check(name, "3.overflow_unchanged", 5L * BUF, p.overflowMemoryInBytes());
        if (t != null)
            p.put(t);

        // step 4: the overflow buffers go back
        for (ByteBuffer b : extra)
            p.put(b);
        figures(name, "4-overflow-back", p);
        check(name, "4.overflow_zero", 0, p.overflowMemoryInBytes());
        check(name, "4.pooled_unchanged", ceiling, pooled(p));

        // step 5: everything goes back; the reservation stays
        for (ByteBuffer b : pooledBufs)
            p.put(b);
        p.releaseLocal();
        figures(name, "5-all-back", p);
        check(name, "5.pooled_unchanged", ceiling, pooled(p));
        check(name, "5.used_zero", 0, p.usedSizeInBytes());
        check(name, "5.overflow_zero", 0, p.overflowMemoryInBytes());

        // after step 5 the pool serves again without a new macro chunk: one more buffer is a hit
        ByteBuffer again = p.get(BUF, BufferType.OFF_HEAP);
        figures(name, "6-reuse", p);
        check(name, "6.reuse_overflow_zero", 0, p.overflowMemoryInBytes());
        check(name, "6.reuse_pooled_unchanged", ceiling, pooled(p));
        p.put(again);
        p.unsafeReset();
    }

    @Test
    public void ceiling16()
    {
        runPool(16);
    }

    @Test
    public void ceiling20()
    {
        runPool(20);
    }

    @Test
    public void ceiling64()
    {
        runPool(64);
    }

    @Test
    public void ceiling100()
    {
        runPool(100);
    }

    @AfterClass
    public static void done()
    {
        line("STAGE4 done checks=" + checks + " mismatches=" + mismatches);
        assertEquals("STAGE4 mismatches", 0, mismatches);
    }
}
