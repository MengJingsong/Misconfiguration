import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

import org.apache.cassandra.utils.memory.BufferPool;
import org.apache.cassandra.utils.memory.BufferPools;

/** Byteman helper (loaded with the agent's sys: option): the chunk-cache pool's counters and the JVM direct pool, as one string. */
public class HuHelper
{
    public static String pool()
    {
        BufferPool p = BufferPools.forChunkCache();
        long direct = -1;
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct"))
                direct = b.getMemoryUsed();
        return "size=" + p.sizeInBytes() + " used=" + p.usedSizeInBytes() + " ovf=" + p.overflowMemoryInBytes()
               + " thr=" + p.memoryUsageThreshold() + " direct=" + direct;
    }
}
