import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.file.Files;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 harness, cluster tier B3d (amended 2026-10-25) of key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous.
 * Modelled on the memtable_heap_space-applySimpleConfig harness Sampler.java (one JMX connection; jstat cannot attach here).
 * Every 2 s appends
 *   epoch_ms,phase,capacity,size_bytes,entries,requests,hits,misses,heap_used
 * (org.apache.cassandra.metrics:type=Cache,scope=KeyCache,name=Capacity|Size|Entries (gauges, Value) and Requests|Hits|Misses
 * (meters, Count), CacheMetrics.java:69-75; java.lang:type=Memory HeapMemoryUsage.used) to <csv>, with the phase label read
 * from <phasefile>, until <stopfile> exists.   usage: java KeyCacheSampler <port> <csv> <phasefile> <stopfile>
 */
public class KeyCacheSampler
{
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[0]) + "/jmxrmi");
        String p = "org.apache.cassandra.metrics:type=Cache,scope=KeyCache,name=";
        ObjectName cap = new ObjectName(p + "Capacity"), size = new ObjectName(p + "Size"), ent = new ObjectName(p + "Entries");
        ObjectName req = new ObjectName(p + "Requests"), hit = new ObjectName(p + "Hits"), mis = new ObjectName(p + "Misses");
        ObjectName mem = new ObjectName("java.lang:type=Memory");
        File phase = new File(a[2]), stop = new File(a[3]);
        try (JMXConnector c = JMXConnectorFactory.connect(u);
             PrintWriter w = new PrintWriter(new FileWriter(a[1], true), true))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            w.println("epoch_ms,phase,capacity,size_bytes,entries,requests,hits,misses,heap_used");
            long next = System.currentTimeMillis();
            while (true)
            {
                boolean last = stop.exists();
                long t = System.currentTimeMillis();
                String ph = phase.exists() ? new String(Files.readAllBytes(phase.toPath())).trim() : "";
                String row;
                try
                {
                    row = t + "," + ph + "," + m.getAttribute(cap, "Value") + "," + m.getAttribute(size, "Value") + "," + m.getAttribute(ent, "Value")
                          + "," + m.getAttribute(req, "Count") + "," + m.getAttribute(hit, "Count") + "," + m.getAttribute(mis, "Count")
                          + "," + ((CompositeData) m.getAttribute(mem, "HeapMemoryUsage")).get("used");
                }
                catch (Exception e)
                {
                    row = t + "," + ph + ",ERROR " + e.getClass().getSimpleName() + ",,,,,,";
                }
                w.println(row);
                if (last) break;
                next += 2000;
                long sl = next - System.currentTimeMillis();
                if (sl > 0) Thread.sleep(sl);
            }
        }
    }
}
