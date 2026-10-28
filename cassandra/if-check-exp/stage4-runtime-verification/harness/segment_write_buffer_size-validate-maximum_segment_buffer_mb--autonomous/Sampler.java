import java.io.FileWriter;
import java.io.PrintWriter;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 harness: java Sampler <jmx-port> <out.csv> <interval-ms>
 * Every interval writes: epoch ms, SegmentBufferSpaceUsedBytes, SegmentBufferSpaceLimitBytes, ColumnIndexBuildsInProgress, heap used, heap committed.
 * Runs until killed. A reading that fails is written as -1 (the gauge is registered only when V1OnDiskFormat is loaded).
 */
public class Sampler
{
    static long gauge(MBeanServerConnection m, String name)
    {
        try
        {
            Object v = m.getAttribute(new ObjectName("org.apache.cassandra.metrics:type=StorageAttachedIndex,name=" + name), "Value");
            return ((Number) v).longValue();
        }
        catch (Exception e)
        {
            return -1;
        }
    }

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[0]) + "/jmxrmi");
        long interval = Long.parseLong(a[2]);
        try (JMXConnector c = JMXConnectorFactory.connect(u); PrintWriter w = new PrintWriter(new FileWriter(a[1], true), true))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            w.println("ms,used,limit,builds,heap_used,heap_committed");
            while (true)
            {
                long t = System.currentTimeMillis();
                CompositeData h = (CompositeData) m.getAttribute(new ObjectName("java.lang:type=Memory"), "HeapMemoryUsage");
                w.println(t + "," + gauge(m, "SegmentBufferSpaceUsedBytes") + "," + gauge(m, "SegmentBufferSpaceLimitBytes") + ","
                          + gauge(m, "ColumnIndexBuildsInProgress") + "," + h.get("used") + "," + h.get("committed"));
                Thread.sleep(interval);
            }
        }
    }
}
