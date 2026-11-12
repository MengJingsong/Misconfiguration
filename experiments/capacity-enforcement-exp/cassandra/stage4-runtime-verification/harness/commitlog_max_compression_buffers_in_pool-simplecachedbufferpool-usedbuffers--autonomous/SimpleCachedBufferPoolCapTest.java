/*
 * Stage-4 harness, case commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-usedbuffers--autonomous,
 * unit tier B2c Test 1 (pool alone). Copied into test/unit/org/apache/cassandra/io/util/ by unit-run.sh.
 * Prints one "POOL" line per step to stdout (build/test/logs/_jdk11/TEST-<class>.log).
 */
package org.apache.cassandra.io.util;

import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.io.compress.BufferType;

public class SimpleCachedBufferPoolCapTest
{
    private static final int MIB = 1 << 20;

    @BeforeClass
    public static void setup()
    {
        DatabaseDescriptor.daemonInitialization();
    }

    private static BufferPoolMXBean direct()
    {
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct"))
                return b;
        throw new IllegalStateException("no direct buffer pool bean");
    }

    private static void line(int n, String step, Object k, SimpleCachedBufferPool pool, long direct0)
    {
        BufferPoolMXBean d = direct();
        System.out.println("POOL N=" + n + " step=" + step + " k=" + k
                           + " atLimit=" + (pool == null ? "na" : pool.atLimit())
                           + " pool=[" + pool + "]"
                           + " directDelta=" + (d.getMemoryUsed() - direct0)
                           + " directCount=" + d.getCount());
    }

    @Test
    public void capSweep()
    {
        for (int n : new int[]{ 1, 2, 3, 6, 12 })
        {
            long direct0 = direct().getMemoryUsed();
            SimpleCachedBufferPool pool;
            try
            {
                pool = new SimpleCachedBufferPool(n, MIB, BufferType.OFF_HEAP);
            }
            catch (Throwable t)
            {
                System.out.println("POOL N=" + n + " step=construct exception=" + t.getClass().getName() + " msg=" + t.getMessage());
                continue;
            }
            line(n, "construct", 0, pool, direct0);
            List<ByteBuffer> bufs = new ArrayList<>();
            try
            {
                for (int k = 1; k <= 2 * n; k++)
                {
                    bufs.add(pool.createBuffer());
                    line(n, "create", k, pool, direct0);
                }
                for (ByteBuffer b : bufs)
                    pool.releaseBuffer(b);
                bufs.clear();
                line(n, "released2N", 2 * n, pool, direct0);
                for (int k = 1; k <= n; k++)
                    bufs.add(pool.createBuffer());
                line(n, "retakeN", n, pool, direct0);
                for (ByteBuffer b : bufs)
                    pool.releaseBuffer(b);
                bufs.clear();
                pool.emptyBufferPool();
                line(n, "emptied", 0, pool, direct0);
            }
            catch (Throwable t)
            {
                System.out.println("POOL N=" + n + " step=error exception=" + t.getClass().getName() + " msg=" + t.getMessage());
            }
        }
    }
}
