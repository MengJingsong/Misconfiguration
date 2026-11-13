// C3 (2026-11-12): low-overhead JMX sampler for the JDK direct buffer pool of one Cassandra node.
// Usage: java DirectPoll <jmx_port> <period_ms> > samples.tsv
// Columns: epoch_ms  direct_used_B  direct_count  threads  heap_used_B
// One JMX connection, polling the platform MXBeans only (no Cassandra MBeans): U independent of any
// Cassandra counter. Exits when the connection fails (node gone).
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class DirectPoll
{
    public static void main(String[] args) throws Exception
    {
        int port = Integer.parseInt(args[0]);
        long period = Long.parseLong(args[1]);
        JMXServiceURL url = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + port + "/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(url))
        {
            MBeanServerConnection s = c.getMBeanServerConnection();
            ObjectName direct = new ObjectName("java.nio:type=BufferPool,name=direct");
            ObjectName threads = new ObjectName("java.lang:type=Threading");
            ObjectName mem = new ObjectName("java.lang:type=Memory");
            while (true)
            {
                long t = System.currentTimeMillis();
                long used = (Long) s.getAttribute(direct, "MemoryUsed");
                long count = (Long) s.getAttribute(direct, "Count");
                int th = (Integer) s.getAttribute(threads, "ThreadCount");
                long heap = (Long) ((CompositeData) s.getAttribute(mem, "HeapMemoryUsage")).get("used");
                System.out.println(t + "\t" + used + "\t" + count + "\t" + th + "\t" + heap);
                System.out.flush();
                long sl = period - (System.currentTimeMillis() - t);
                if (sl > 0) Thread.sleep(sl);
            }
        }
        catch (Exception e)
        {
            System.err.println("DirectPoll stopped: " + e);
        }
    }
}
