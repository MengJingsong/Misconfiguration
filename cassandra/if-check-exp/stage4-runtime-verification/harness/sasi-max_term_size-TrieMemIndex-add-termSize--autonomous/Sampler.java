// Stage-4 harness (not upstream): samples a Cassandra node over local JMX every <interval-ms>:
// heap used, ks.t MemtableOnHeapDataSize (Value) and MemtableSwitchCount (Count). The two table metrics read -1 until the table exists.
// Usage: java Sampler <jmx-port> <out.csv> <interval-ms>. Retries the connection until it works; stop it with kill.
import java.io.FileWriter;
import java.io.PrintWriter;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class Sampler
{
    static Object attr(MBeanServerConnection c, String name, String a)
    {
        try { return c.getAttribute(new ObjectName("org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=" + name), a); }
        catch (Exception e) { return -1L; }
    }

    public static void main(String[] a) throws Exception
    {
        int port = Integer.parseInt(a[0]);
        long iv = Long.parseLong(a[2]);
        PrintWriter w = new PrintWriter(new FileWriter(a[1]));
        w.println("epoch_ms,heap_used,memtable_onheap,switch_count");
        ObjectName mem = new ObjectName("java.lang:type=Memory");
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
                w.println(t + "," + cd.get("used") + "," + attr(c, "MemtableOnHeapDataSize", "Value") + "," + attr(c, "MemtableSwitchCount", "Count"));
                if (++n % 4 == 0) w.flush();
            }
            catch (Exception e)
            {
                c = null;
            }
            Thread.sleep(iv);
        }
    }
}
