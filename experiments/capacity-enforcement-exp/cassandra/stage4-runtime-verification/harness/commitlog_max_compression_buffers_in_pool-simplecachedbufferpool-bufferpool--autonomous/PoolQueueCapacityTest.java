/*
 * Stage-4 harness, case commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-bufferpool--autonomous,
 * unit tier class 2 (B2a): SimpleCachedBufferPool on its own, no segment manager. CAP_N (env) = maxBufferPoolSize.
 */
package org.apache.cassandra.db.commitlog;

import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.io.compress.BufferType;
import org.apache.cassandra.io.util.SimpleCachedBufferPool;

public class PoolQueueCapacityTest
{
    static BufferPoolMXBean direct()
    {
        return ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class).stream()
                                .filter(b -> b.getName().equals("direct")).findFirst().get();
    }

    @Test
    public void queueCapacity()
    {
        DatabaseDescriptor.daemonInitialization();
        int n = Integer.parseInt(System.getenv().getOrDefault("CAP_N", "3"));
        int k = 10;
        long d0 = direct().getMemoryUsed();
        SimpleCachedBufferPool pool = new SimpleCachedBufferPool(n, 1 << 20, BufferType.OFF_HEAP);
        List<ByteBuffer> held = new ArrayList<>();
        for (int i = 0; i < k; i++)
            held.add(pool.createBuffer());
        System.out.println("O44 Q CAP_N=" + n + " afterCreate pool=[" + pool + "] atLimit=" + pool.atLimit() + " directDelta=" + (direct().getMemoryUsed() - d0));
        Set<ByteBuffer> released = Collections.newSetFromMap(new IdentityHashMap<>());
        for (ByteBuffer b : held)
        {
            released.add(b);
            pool.releaseBuffer(b);
        }
        System.out.println("O44 Q CAP_N=" + n + " afterRelease pool=[" + pool + "] atLimit=" + pool.atLimit() + " directDelta=" + (direct().getMemoryUsed() - d0));
        int retained = 0;
        List<ByteBuffer> again = new ArrayList<>();
        for (int i = 0; i < k; i++)
        {
            ByteBuffer b = pool.createBuffer();
            again.add(b);
            if (released.contains(b))
                retained++;
        }
        System.out.println("O44 Q CAP_N=" + n + " retained=" + retained + " afterRecreate pool=[" + pool + "] directDelta=" + (direct().getMemoryUsed() - d0));
        for (ByteBuffer b : again)
            pool.releaseBuffer(b);
        pool.emptyBufferPool();
        String n1;
        try
        {
            new SimpleCachedBufferPool(1, 1 << 20, BufferType.OFF_HEAP);
            n1 = "noException";
        }
        catch (Throwable e)
        {
            n1 = e.getClass().getName();
        }
        System.out.println("O44 Q CAP_N=" + n + " N1=" + n1);
    }
}
