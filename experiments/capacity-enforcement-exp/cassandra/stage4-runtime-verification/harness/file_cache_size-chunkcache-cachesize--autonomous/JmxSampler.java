import java.io.File;
import java.io.FileWriter;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 harness for file_cache_size-chunkcache-cachesize--autonomous, cluster tier (amendment A5).
 *   java JmxSampler <jmx port> <out csv> <interval ms> <stopfile> [once]
 * Appends one CSV line per interval until <stopfile> exists (or one line with "once"):
 *   epoch_ms,cacheCapacity,cacheSize,cacheEntries,cacheMisses,poolCapacity,poolSize,poolOverflow,poolUsed,directUsed,directCount
 * cache* = org.apache.cassandra.metrics:type=Cache,scope=ChunkCache (-1 if absent: no chunk cache);
 * pool* = type=BufferPool,scope=chunk-cache; direct* = java.nio:type=BufferPool,name=direct. One JMX connection for the whole run.
 */
public class JmxSampler
{
    static MBeanServerConnection m;

    static long get(String bean, String attr)
    {
        try
        {
            Object o = m.getAttribute(new ObjectName(bean), attr);
            return ((Number) o).longValue();
        }
        catch (javax.management.InstanceNotFoundException e)
        {
            return -1;
        }
        catch (Exception e)
        {
            return -2;
        }
    }

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[0]) + "/jmxrmi");
        long ms = Long.parseLong(a[2]);
        File stop = new File(a[3]);
        boolean once = a.length > 4 && a[4].equals("once");
        String C = "org.apache.cassandra.metrics:type=Cache,scope=ChunkCache,name=";
        String P = "org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=";
        String D = "java.nio:type=BufferPool,name=direct";
        try (JMXConnector c = JMXConnectorFactory.connect(u); FileWriter w = new FileWriter(a[1], true))
        {
            m = c.getMBeanServerConnection();
            while (true)
            {
                long t0 = System.currentTimeMillis();
                String line = t0 + "," + get(C + "Capacity", "Value") + "," + get(C + "Size", "Value") + "," + get(C + "Entries", "Value") + ","
                              + get(C + "Misses", "Count") + "," + get(P + "Capacity", "Value") + "," + get(P + "Size", "Value") + ","
                              + get(P + "OverflowSize", "Value") + "," + get(P + "UsedSize", "Value") + "," + get(D, "MemoryUsed") + "," + get(D, "Count");
                w.write(line + "\n");
                w.flush();
                if (once || stop.exists())
                    break;
                long sl = ms - (System.currentTimeMillis() - t0);
                if (sl > 0)
                    Thread.sleep(sl);
            }
        }
    }
}
