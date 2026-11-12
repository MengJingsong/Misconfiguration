import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.MemoryUsage;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * B1 sampler (adapted from the capacity-enforcement-exp networking_cache_size PoolSampler).
 * usage: java B1Sampler <out.csv> <stop-file> [period_ms=1000]
 * One JMX pass per period on 127.0.0.1:7199. CSV columns:
 *   t_ms,capacity,size,used,overflow,pooled,misses,direct_used,direct_count,requests_size,heap_used,clients
 * size/used/overflow: networking BufferPool gauges (K for D1/D2); pooled = size - overflow (chunks reserved);
 * direct_used/count: java.nio direct pool (U); requests_size: Client RequestsSize (in-flight counter, D3).
 */
public class B1Sampler
{
    static final String NET = "org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=";
    static final String CLI = "org.apache.cassandra.metrics:type=Client,name=";

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
                w.println("t_ms,capacity,size,used,overflow,pooled,misses,direct_used,direct_count,requests_size,heap_used,clients");
            while (!stop.exists())
            {
                long t0 = System.currentTimeMillis();
                try
                {
                    long cap = num(m, NET + "Capacity", "Value");
                    long size = num(m, NET + "Size", "Value");
                    long used = num(m, NET + "UsedSize", "Value");
                    long overflow = num(m, NET + "OverflowSize", "Value");
                    long misses = num(m, NET + "Misses", "Count");
                    long du = num(m, "java.nio:type=BufferPool,name=direct", "MemoryUsed");
                    long dc = num(m, "java.nio:type=BufferPool,name=direct", "Count");
                    long rs = num(m, CLI + "RequestsSize", "Value");
                    long cl = num(m, CLI + "ConnectedNativeClients", "Value");
                    MemoryUsage heap = MemoryUsage.from((CompositeData) m.getAttribute(new ObjectName("java.lang:type=Memory"), "HeapMemoryUsage"));
                    w.println(t0 + "," + cap + "," + size + "," + used + "," + overflow + "," + (size - overflow) + "," + misses + ","
                              + du + "," + dc + "," + rs + "," + heap.getUsed() + "," + cl);
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
