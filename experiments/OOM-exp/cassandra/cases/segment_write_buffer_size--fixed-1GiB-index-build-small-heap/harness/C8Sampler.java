import java.io.FileWriter;
import java.io.PrintWriter;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * C8 stage-2 sampler (extends the stage-4 Sampler.java of segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous).
 *   java C8Sampler <jmx-port> <out.csv> <interval-ms>
 * Columns: ms, K_D1 SegmentBufferSpaceUsedBytes, SegmentBufferSpaceLimitBytes, ColumnIndexBuildsInProgress, heap used, heap committed,
 *          K_D2 AllMemtablesOnHeapDataSize (Table global), MemtablePool BlockedOnAllocation count, MemtablePool PendingFlushTasks,
 *          G1 young count, G1 old count, key cache weighted Size (K_D3), key cache Entries (added 2026-11-18 stage 2, amendment A2).
 * A reading that fails is written as -1. Reconnects if JMX drops; exits after 20 consecutive failures.
 */
public class C8Sampler
{
    static long attr(MBeanServerConnection m, String on, String... attrs)
    {
        for (String a : attrs)
        {
            try
            {
                Object v = m.getAttribute(new ObjectName(on), a);
                return ((Number) v).longValue();
            }
            catch (Exception e)
            {
                // try next
            }
        }
        return -1;
    }

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[0]) + "/jmxrmi");
        long interval = Long.parseLong(a[2]);
        PrintWriter w = new PrintWriter(new FileWriter(a[1], true), true);
        w.println("ms,k_d1,limit,builds,heap_used,heap_committed,k_d2,blocked,pending_flush,young_gc,old_gc,kc_size,kc_entries");
        int fails = 0;
        while (fails < 20)
        {
            try (JMXConnector c = JMXConnectorFactory.connect(u))
            {
                MBeanServerConnection m = c.getMBeanServerConnection();
                fails = 0;
                while (true)
                {
                    long t = System.currentTimeMillis();
                    CompositeData h = (CompositeData) m.getAttribute(new ObjectName("java.lang:type=Memory"), "HeapMemoryUsage");
                    String sai = "org.apache.cassandra.metrics:type=StorageAttachedIndex,name=";
                    w.println(t + "," + attr(m, sai + "SegmentBufferSpaceUsedBytes", "Value") + "," + attr(m, sai + "SegmentBufferSpaceLimitBytes", "Value") + ","
                              + attr(m, sai + "ColumnIndexBuildsInProgress", "Value") + "," + h.get("used") + "," + h.get("committed") + ","
                              + attr(m, "org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize", "Value") + ","
                              + attr(m, "org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation", "Count", "Value") + ","
                              + attr(m, "org.apache.cassandra.metrics:type=MemtablePool,name=PendingFlushTasks", "Value", "Count") + ","
                              + attr(m, "java.lang:type=GarbageCollector,name=G1 Young Generation", "CollectionCount") + ","
                              + attr(m, "java.lang:type=GarbageCollector,name=G1 Old Generation", "CollectionCount") + ","
                              + attr(m, "org.apache.cassandra.metrics:type=Cache,scope=KeyCache,name=Size", "Value") + ","
                              + attr(m, "org.apache.cassandra.metrics:type=Cache,scope=KeyCache,name=Entries", "Value"));
                    Thread.sleep(interval);
                }
            }
            catch (Exception e)
            {
                fails++;
                Thread.sleep(1000);
            }
        }
    }
}
