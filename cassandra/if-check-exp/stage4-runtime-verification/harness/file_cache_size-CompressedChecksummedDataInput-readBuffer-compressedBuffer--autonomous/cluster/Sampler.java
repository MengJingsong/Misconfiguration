import java.io.*;
import java.nio.file.*;
import java.util.*;
import javax.management.*;
import javax.management.remote.*;

/** usage: Sampler <host> <jmxport> <pid> <out.csv> <periodMs>. Samples node1's pool + JVM direct + RssAnon until killed. */
public class Sampler
{
    static long gauge(MBeanServerConnection c, String name) throws Exception
    {
        return ((Number) c.getAttribute(new ObjectName("org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=" + name), "Value")).longValue();
    }
    static long net(MBeanServerConnection c, String name) throws Exception
    {
        return ((Number) c.getAttribute(new ObjectName("org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=" + name), "Value")).longValue();
    }
    static long rssAnon(String pid) throws IOException
    {
        for (String l : Files.readAllLines(Paths.get("/proc/" + pid + "/status")))
            if (l.startsWith("RssAnon:")) return Long.parseLong(l.replaceAll("[^0-9]", "")) * 1024;
        return -1;
    }
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + ":" + a[1] + "/jmxrmi");
        long period = Long.parseLong(a[4]);
        try (JMXConnector jc = JMXConnectorFactory.connect(u); PrintWriter out = new PrintWriter(new FileWriter(a[3]), true))
        {
            MBeanServerConnection c = jc.getMBeanServerConnection();
            ObjectName direct = new ObjectName("java.nio:type=BufferPool,name=direct");
            ObjectName mem = new ObjectName("java.lang:type=Memory");
            out.println("epoch_ms,capacity,size,used,overflow,pooled,direct_used,direct_count,rss_anon,heap_used,net_size,net_overflow");
            while (true)
            {
                long t = System.currentTimeMillis();
                try
                {
                    long cap = gauge(c, "Capacity"), size = gauge(c, "Size"), used = gauge(c, "UsedSize"), over = gauge(c, "OverflowSize");
                    long du = ((Number) c.getAttribute(direct, "MemoryUsed")).longValue(), dc = ((Number) c.getAttribute(direct, "Count")).longValue();
                    long heap = (Long) ((javax.management.openmbean.CompositeData) c.getAttribute(mem, "HeapMemoryUsage")).get("used");
                    out.println(t + "," + cap + "," + size + "," + used + "," + over + "," + (size - over) + "," + du + "," + dc + "," + rssAnon(a[2]) + "," + heap
                                + "," + net(c, "Size") + "," + net(c, "OverflowSize"));
                }
                catch (Exception e) { out.println(t + ",ERR," + e.getClass().getSimpleName()); }
                long d = period - (System.currentTimeMillis() - t);
                if (d > 0) Thread.sleep(d);
            }
        }
    }
}
