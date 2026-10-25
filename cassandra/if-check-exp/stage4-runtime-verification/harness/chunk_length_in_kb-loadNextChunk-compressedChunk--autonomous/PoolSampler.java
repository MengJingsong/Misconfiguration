// Stage-4 harness (not upstream): samples java.nio:type=BufferPool,name=direct of a JVM over local JMX.
// Usage: java PoolSampler <jmx-port> <out.csv> <interval-ms>. Retries the connection until it works; stop it with kill.
import java.io.FileWriter;
import java.io.PrintWriter;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class PoolSampler
{
    public static void main(String[] a) throws Exception
    {
        int port = Integer.parseInt(a[0]);
        long iv = Long.parseLong(a[2]);
        PrintWriter w = new PrintWriter(new FileWriter(a[1]));
        w.println("epoch_ms,direct_used,direct_count,mapped_used");
        ObjectName direct = new ObjectName("java.nio:type=BufferPool,name=direct");
        ObjectName mapped = new ObjectName("java.nio:type=BufferPool,name=mapped");
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
                long u = (Long) c.getAttribute(direct, "MemoryUsed");
                long k = (Long) c.getAttribute(direct, "Count");
                long m = (Long) c.getAttribute(mapped, "MemoryUsed");
                w.println(t + "," + u + "," + k + "," + m);
                if (++n % 25 == 0) w.flush();
            }
            catch (Exception e)
            {
                c = null;
            }
            Thread.sleep(iv);
        }
    }
}
