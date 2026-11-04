/*
 * Stage-4 harness, NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous, unit tier (case file B2e,
 * with the stage-4 audit amendments U1-U3 of 2026-10-22). Copied into
 * test/unit/org/apache/cassandra/utils/memory/ of a cassandra-5.0.9 clone by unit-run.sh.
 *
 * Differences from the B2e listing (all amendments, recorded in the case file):
 *  - U2: every ROW line also carries dDirect, the change of java.nio direct MemoryUsed across putUnusedPortion
 *    (the real resource), and the PUT line carries sizeAfterGet; every CTL line carries directDelta (direct MemoryUsed
 *    at the first overflow minus before the first get), the macro-chunk count k = pooledBytes / 8 MiB, and pageSize.
 *  - U1: O1 is reported like the others; the B2f/B2g amendment says how its dSize is read.
 *  - an INFO line prints the constants the operands derive from.
 *  - D1 (runbook-defect fix, 2026-10-22): fill() keeps the buffers it got and puts them back after its CTL line and before
 *    unsafeReset(); B2e's listing called unsafeReset() with the buffers still held, which trips the -ea assertion in
 *    Chunk.recycleFully ("Status of chunk ... was not EVICTED", BufferPool.java:1308) on the first fill.
 * Observation only: no code path of BufferPool is changed.
 */
package org.apache.cassandra.utils.memory;

import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

import org.junit.After;
import org.junit.Test;

import org.apache.cassandra.io.compress.BufferType;

import static org.junit.Assert.assertEquals;

public class FreeUnusedPortionProbeTest
{
    BufferPool pool;

    @After
    public void tearDown()
    {
        if (pool != null)
            pool.unsafeReset();
    }

    private static long direct()
    {
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct"))
                return b.getMemoryUsed();
        return -1;
    }

    private void row(String id, int req, boolean atLeast, int limit)
    {
        ByteBuffer b = atLeast ? pool.getAtLeast(req, BufferType.OFF_HEAP) : pool.get(req, BufferType.OFF_HEAP);
        long sizeAfterGet = pool.sizeInBytes();
        BufferPool.Chunk c = BufferPool.Chunk.getParentChunk(b);
        int capBefore = b.capacity();
        long used0 = pool.usedSizeInBytes(), size0 = pool.sizeInBytes(), ovf0 = pool.overflowMemoryInBytes();
        int free0 = c == null ? -1 : c.free();
        String op = c == null ? "unit=-,size=-,capacity=-,guard=-"
                  : "unit=" + c.unit() + ",size=" + c.roundUp(limit) + ",capacity=" + c.roundUp(capBefore)
                    + ",guard=" + (c.roundUp(limit) == c.roundUp(capBefore));
        b.limit(limit);
        long d0 = direct();
        pool.putUnusedPortion(b);
        long d1 = direct();
        System.out.println("ROW," + id + "," + op + ",capBefore=" + capBefore + ",capAfter=" + b.capacity()
            + ",dFree=" + (c == null ? 0 : c.free() - free0) + ",dUsed=" + (pool.usedSizeInBytes() - used0)
            + ",dSize=" + (pool.sizeInBytes() - size0) + ",dOverflow=" + (pool.overflowMemoryInBytes() - ovf0)
            + ",dDirect=" + (d1 - d0));
        long sizeBeforePut = pool.sizeInBytes();
        pool.put(b);
        System.out.println("PUT," + id + ",overflowAfterPut=" + pool.overflowMemoryInBytes() + ",sizeAfterGet=" + sizeAfterGet
                           + ",sizeBeforePut=" + sizeBeforePut);
    }

    @Test
    public void probeRows()
    {
        System.out.println("INFO,NORMAL_CHUNK_SIZE=" + BufferPool.NORMAL_CHUNK_SIZE + ",NORMAL_ALLOCATION_UNIT=" + BufferPool.NORMAL_ALLOCATION_UNIT
                           + ",TINY_CHUNK_SIZE=" + BufferPool.TINY_CHUNK_SIZE + ",TINY_ALLOCATION_UNIT=" + BufferPool.TINY_ALLOCATION_UNIT
                           + ",MACRO_CHUNK_SIZE=" + BufferPool.GlobalPool.MACRO_CHUNK_SIZE + ",pageSize=" + MemoryUtil.pageSize());
        pool = new BufferPool("probe", 8L << 20, false);
        row("N1", 8192, true, 8192); row("N2", 8192, true, 6145);
        row("N3", 8192, true, 6144); row("N4", 8192, true, 1);
        row("N5", 5000, false, 4097); row("N6", 5000, false, 4096);
        row("T1", 100, true, 97);    row("T2", 100, true, 96);
        row("O1", 262144, false, 1024);
        int zero = 0;
        long shifted = 0xffffffffffffffffL >>> (64 - zero);
        System.out.println("SHIFT,slotCount=0,mask=" + shifted);
        assertEquals(-1L, shifted); // why the guard exists
    }

    private int fill(long threshold, boolean trim)
    {
        pool = new BufferPool("ctl", threshold, false);
        long direct0 = direct();
        int n = 0;
        long directAtOverflow;
        List<ByteBuffer> held = new ArrayList<>(); // runbook-defect fix D1 (2026-10-22): returned before unsafeReset
        while (true)
        {
            ByteBuffer b = pool.getAtLeast(65536, BufferType.OFF_HEAP);
            if (BufferPool.Chunk.getParentChunk(b) == null)
            {
                pool.put(b);
                directAtOverflow = direct();
                break;
            }
            if (trim) { b.limit(2048); pool.putUnusedPortion(b); }
            held.add(b);
            n++;
        }
        long pooled = pool.sizeInBytes() - pool.overflowMemoryInBytes();
        System.out.println("CTL,threshold=" + threshold + ",trim=" + trim + ",buffers=" + n + ",pooledBytes=" + pooled
                           + ",k=" + (pooled / BufferPool.GlobalPool.MACRO_CHUNK_SIZE) + ",directDelta=" + (directAtOverflow - direct0)
                           + ",pageSize=" + MemoryUtil.pageSize() + ",usedBytes=" + pool.usedSizeInBytes());
        for (ByteBuffer b : held)   // D1: unsafeReset asserts (-ea) that no local chunk still holds a buffer
            pool.put(b);
        pool.unsafeReset();
        pool = null;
        return n;
    }

    @Test
    public void positiveControl()
    {
        fill(8L << 20, false);
        fill(8L << 20, true);
        fill(16L << 20, false);
    }
}
