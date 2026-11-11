import javax.management.*;
import javax.management.remote.*;
import java.io.*;

/** Row-cache gauge poller. Usage: java Jmx <jmx-port> once | poll <interval-ms> <outfile>
 *  Prints "epoch_ms,size,capacity,entries" (gauges org.apache.cassandra.metrics:type=Cache,scope=RowCache,name=Size|Capacity|Entries, attribute Value). */
public class Jmx
{
    static String line(MBeanServerConnection c) throws Exception
    {
        long t = System.currentTimeMillis();
        Object s = c.getAttribute(new ObjectName("org.apache.cassandra.metrics:type=Cache,scope=RowCache,name=Size"), "Value");
        Object cap = c.getAttribute(new ObjectName("org.apache.cassandra.metrics:type=Cache,scope=RowCache,name=Capacity"), "Value");
        Object e = c.getAttribute(new ObjectName("org.apache.cassandra.metrics:type=Cache,scope=RowCache,name=Entries"), "Value");
        return t + "," + s + "," + cap + "," + e;
    }
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi");
        try (JMXConnector jc = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection c = jc.getMBeanServerConnection();
            if (a[1].equals("once")) { System.out.println(line(c)); return; }
            long iv = Long.parseLong(a[2]);
            try (PrintWriter w = new PrintWriter(new FileWriter(a[3])))
            {
                w.println("epoch_ms,size,capacity,entries");
                while (true) { try { w.println(line(c)); w.flush(); } catch (Exception ex) { w.println("ERR," + ex); w.flush(); return; } Thread.sleep(iv); }
            }
        }
    }
}
