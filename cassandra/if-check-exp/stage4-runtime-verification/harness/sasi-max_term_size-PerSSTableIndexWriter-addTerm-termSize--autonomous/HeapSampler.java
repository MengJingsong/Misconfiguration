// Stage-4 harness (not upstream): samples java.lang:type=Memory HeapMemoryUsage over local JMX. Usage: java HeapSampler <jmx-port> <out.csv> <interval-ms>. Stop it by PID.
import java.io.FileWriter;
import java.io.PrintWriter;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class HeapSampler
{
    public static void main(String[] a) throws Exception
    {
        int port = Integer.parseInt(a[0]);
        long iv = Long.parseLong(a[2]);
        PrintWriter w = new PrintWriter(new FileWriter(a[1]));
        w.println("epoch_ms,heap_used,heap_committed");
        ObjectName mem = new ObjectName("java.lang:type=Memory");
        MBeanServerConnection c = null;
        JMXConnector jc = null;
        int n = 0;
        while (true)
        {
            try
            {
                if (c == null)
                {
                    jc = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + port + "/jmxrmi"));
                    c = jc.getMBeanServerConnection();
                }
                long t = System.currentTimeMillis();
                CompositeData cd = (CompositeData) c.getAttribute(mem, "HeapMemoryUsage");
                w.println(t + "," + cd.get("used") + "," + cd.get("committed"));
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
