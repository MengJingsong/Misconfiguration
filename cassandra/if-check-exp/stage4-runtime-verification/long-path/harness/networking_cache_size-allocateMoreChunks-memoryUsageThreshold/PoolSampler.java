import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Case 9c/9d sampler for networking_cache_size-allocateMoreChunks-memoryUsageThreshold: the file_cache_size harness's sampler with
 * the scopes swapped. usage: java PoolSampler <out.csv> <stop-file> [period_ms=1000]
 * One JMX connection to 127.0.0.1:7199; every period, in one pass: the networking pool's Capacity, Size, UsedSize, OverflowSize,
 * Hits, Misses; the chunk-cache pool's Size and OverflowSize; java.nio direct MemoryUsed and Count; and StorageService
 * ReleaseVersion, which triggers net.btm's dump line. One CSV row per pass:
 *   t0_ms,t1_ms,capacity,size,used,overflow,pooled,hits,misses,cc_size,cc_overflow,direct_used,direct_count
 * pooled = size - overflow from the same pass. Stops when <stop-file> exists. A failed pass writes "t0_ms,ERR,<message>".
 */
public class PoolSampler
{
    static final String NET = "org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=";
    static final String CC = "org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=";

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
                w.println("t0_ms,t1_ms,capacity,size,used,overflow,pooled,hits,misses,cc_size,cc_overflow,direct_used,direct_count");
            while (!stop.exists())
            {
                long t0 = System.currentTimeMillis();
                try
                {
                    long size = num(m, NET + "Size", "Value");
                    long overflow = num(m, NET + "OverflowSize", "Value");
                    long used = num(m, NET + "UsedSize", "Value");
                    long cap = num(m, NET + "Capacity", "Value");
                    long hits = num(m, NET + "Hits", "Count");
                    long misses = num(m, NET + "Misses", "Count");
                    long ccs = num(m, CC + "Size", "Value");
                    long cco = num(m, CC + "OverflowSize", "Value");
                    long du = num(m, "java.nio:type=BufferPool,name=direct", "MemoryUsed");
                    long dc = num(m, "java.nio:type=BufferPool,name=direct", "Count");
                    m.getAttribute(new ObjectName("org.apache.cassandra.db:type=StorageService"), "ReleaseVersion");
                    long t1 = System.currentTimeMillis();
                    w.println(t0 + "," + t1 + "," + cap + "," + size + "," + used + "," + overflow + "," + (size - overflow) + "," + hits + "," + misses
                              + "," + ccs + "," + cco + "," + du + "," + dc);
                }
                catch (Exception e)
                {
                    w.println(t0 + ",ERR," + e.toString().replace(',', ';'));
                }
                long sleep = period - (System.currentTimeMillis() - t0);
                if (sleep > 0)
                    Thread.sleep(sleep);
            }
        }
    }
}
