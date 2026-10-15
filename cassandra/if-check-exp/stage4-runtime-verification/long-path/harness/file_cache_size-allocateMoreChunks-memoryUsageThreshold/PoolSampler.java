import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Case 9c/9d sampler (amended 2026-10-14) for file_cache_size-allocateMoreChunks-memoryUsageThreshold.
 * usage: java PoolSampler <out.csv> <stop-file> [period_ms=1000]
 * One JMX connection to 127.0.0.1:7199. Every period it reads, in one pass, the chunk-cache pool's Capacity, Size, UsedSize,
 * OverflowSize (gauges, bytes), Hits and Misses (meter counts), the networking pool's Size and OverflowSize, and the JDK's
 * java.nio direct pool MemoryUsed and Count, and appends one CSV row:
 *   t0_ms,t1_ms,capacity,size,used,overflow,pooled,hits,misses,net_size,net_overflow,direct_used,direct_count
 * pooled = size - overflow, from the same pass (t1_ms - t0_ms is the pass's duration). Stops when <stop-file> exists.
 * A failed pass writes a row "t0_ms,ERR,<message>" and the sampler goes on.
 */
public class PoolSampler
{
    static final String CC = "org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=";
    static final String NET = "org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=";

    static long num(MBeanServerConnection m, String bean, String attr) throws Exception
    {
        return ((Number) m.getAttribute(new ObjectName(bean), attr)).longValue();
    }

    public static void main(String[] a) throws Exception
    {
        String out = a[0];
        File stop = new File(a[1]);
        long period = a.length > 2 ? Long.parseLong(a[2]) : 1000;
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi");
        boolean header = !new File(out).exists();
        try (JMXConnector c = JMXConnectorFactory.connect(u); PrintWriter w = new PrintWriter(new FileWriter(out, true), true))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            if (header)
                w.println("t0_ms,t1_ms,capacity,size,used,overflow,pooled,hits,misses,net_size,net_overflow,direct_used,direct_count");
            while (!stop.exists())
            {
                long t0 = System.currentTimeMillis();
                try
                {
                    long size = num(m, CC + "Size", "Value");
                    long overflow = num(m, CC + "OverflowSize", "Value");
                    long used = num(m, CC + "UsedSize", "Value");
                    long cap = num(m, CC + "Capacity", "Value");
                    long hits = num(m, CC + "Hits", "Count");
                    long misses = num(m, CC + "Misses", "Count");
                    long nsize = num(m, NET + "Size", "Value");
                    long nover = num(m, NET + "OverflowSize", "Value");
                    long du = num(m, "java.nio:type=BufferPool,name=direct", "MemoryUsed");
                    long dc = num(m, "java.nio:type=BufferPool,name=direct", "Count");
                    long t1 = System.currentTimeMillis();
                    w.println(t0 + "," + t1 + "," + cap + "," + size + "," + used + "," + overflow + "," + (size - overflow) + "," + hits + "," + misses
                              + "," + nsize + "," + nover + "," + du + "," + dc);
                }
                catch (Exception e)
                {
                    w.println(t0 + ",ERR," + e.getClass().getSimpleName() + ":" + String.valueOf(e.getMessage()).replace(',', ';'));
                }
                long sleep = period - (System.currentTimeMillis() - t0);
                if (sleep > 0)
                    Thread.sleep(sleep);
            }
        }
    }
}
