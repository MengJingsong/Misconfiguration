import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 sampler for NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous, cluster tier (case file B3d, amendment K1):
 * the observables of B3d's `nodetool sjk mx` loop, read over one JMX connection per node in one pass, instead of six JVM
 * starts per sample. Adapted from the networking_cache_size guided harness's PoolSampler.
 * usage: java PoolSampler <jmx-port> <out.csv> <stop-file> [period_ms=5000]
 * Each pass: networking pool Capacity, Size, UsedSize, OverflowSize, Hits, Misses; java.nio direct MemoryUsed and Count;
 * then StorageService ReleaseVersion, which fires ncs.btm's dump line. One CSV row per pass:
 *   t0_ms,t1_ms,capacity,size,used,overflow,pooled_derived,hits,misses,direct_used,direct_count
 * pooled_derived = size - overflow from the same pass (two gauge reads; exact only when no frame is in flight).
 * Stops when <stop-file> exists. A failed pass writes "t0_ms,ERR,<message>" and the sampler retries the connection.
 */
public class PoolSampler
{
    static final String NET = "org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=";

    static long num(MBeanServerConnection m, String bean, String attr) throws Exception
    {
        return ((Number) m.getAttribute(new ObjectName(bean), attr)).longValue();
    }

    public static void main(String[] a) throws Exception
    {
        int port = Integer.parseInt(a[0]);
        String out = a[1];
        File stop = new File(a[2]);
        long period = a.length > 3 ? Long.parseLong(a[3]) : 5000;
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + port + "/jmxrmi");
        boolean header = !new File(out).exists();
        try (PrintWriter w = new PrintWriter(new FileWriter(out, true), true))
        {
            if (header)
                w.println("t0_ms,t1_ms,capacity,size,used,overflow,pooled_derived,hits,misses,direct_used,direct_count");
            JMXConnector c = null;
            while (!stop.exists())
            {
                long t0 = System.currentTimeMillis();
                try
                {
                    if (c == null)
                        c = JMXConnectorFactory.connect(u);
                    MBeanServerConnection m = c.getMBeanServerConnection();
                    long size = num(m, NET + "Size", "Value");
                    long overflow = num(m, NET + "OverflowSize", "Value");
                    long used = num(m, NET + "UsedSize", "Value");
                    long cap = num(m, NET + "Capacity", "Value");
                    long hits = num(m, NET + "Hits", "Count");
                    long misses = num(m, NET + "Misses", "Count");
                    long du = num(m, "java.nio:type=BufferPool,name=direct", "MemoryUsed");
                    long dc = num(m, "java.nio:type=BufferPool,name=direct", "Count");
                    m.getAttribute(new ObjectName("org.apache.cassandra.db:type=StorageService"), "ReleaseVersion");
                    long t1 = System.currentTimeMillis();
                    w.println(t0 + "," + t1 + "," + cap + "," + size + "," + used + "," + overflow + "," + (size - overflow) + ","
                              + hits + "," + misses + "," + du + "," + dc);
                }
                catch (Exception e)
                {
                    w.println(t0 + ",ERR," + e.toString().replace(',', ';'));
                    try { if (c != null) c.close(); } catch (Exception ignored) {}
                    c = null;
                }
                long sleep = period - (System.currentTimeMillis() - t0);
                if (sleep > 0)
                    Thread.sleep(sleep);
            }
            try { if (c != null) c.close(); } catch (Exception ignored) {}
        }
    }
}
