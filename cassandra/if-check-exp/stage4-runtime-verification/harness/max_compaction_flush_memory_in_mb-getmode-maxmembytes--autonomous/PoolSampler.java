// Stage-4 harness (not upstream): samples a Cassandra JVM over local JMX every <interval> ms:
// heap used, G1 Old Gen usage and its after-last-GC usage, and the SASI-General / SASI-Memtable executors' pending / active / completed task counts
// (a pending task of SASI-General is a queued segment builder that is still on the heap).
// Usage: java PoolSampler <jmx-port> <out.csv> <interval-ms>. Retries the connection; stop it with kill.
import java.io.FileWriter;
import java.io.PrintWriter;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class PoolSampler
{
    static Object attr(MBeanServerConnection c, String name, String a)
    {
        try { return c.getAttribute(new ObjectName(name), a); } catch (Exception e) { return -1; }
    }
    static String tp(String scope, String metric)
    {
        return "org.apache.cassandra.metrics:type=ThreadPools,path=internal,scope=" + scope + ",name=" + metric;
    }
    public static void main(String[] a) throws Exception
    {
        int port = Integer.parseInt(a[0]);
        long iv = Long.parseLong(a[2]);
        PrintWriter w = new PrintWriter(new FileWriter(a[1]));
        w.println("epoch_ms,heap_used,heap_committed,old_used,old_after_gc,general_pending,general_active,general_completed,memtable_pending,memtable_active");
        ObjectName mem = new ObjectName("java.lang:type=Memory");
        ObjectName old = new ObjectName("java.lang:type=MemoryPool,name=G1 Old Gen");
        MBeanServerConnection c = null;
        int n = 0;
        while (true)
        {
            try
            {
                if (c == null)
                {
                    JMXConnector jc = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + port + "/jmxrmi"));
                    c = jc.getMBeanServerConnection();
                }
                long t = System.currentTimeMillis();
                CompositeData cd = (CompositeData) c.getAttribute(mem, "HeapMemoryUsage");
                CompositeData ou = (CompositeData) c.getAttribute(old, "Usage");
                CompositeData oc = (CompositeData) c.getAttribute(old, "CollectionUsage");
                w.println(t + "," + cd.get("used") + "," + cd.get("committed") + "," + ou.get("used") + "," + oc.get("used") + ","
                          + attr(c, tp("SASI-General", "PendingTasks"), "Value") + "," + attr(c, tp("SASI-General", "ActiveTasks"), "Value") + "," + attr(c, tp("SASI-General", "CompletedTasks"), "Value") + ","
                          + attr(c, tp("SASI-Memtable", "PendingTasks"), "Value") + "," + attr(c, tp("SASI-Memtable", "ActiveTasks"), "Value"));
                if (++n % 10 == 0) w.flush();
            }
            catch (Exception e)
            {
                c = null;
            }
            Thread.sleep(iv);
        }
    }
}
