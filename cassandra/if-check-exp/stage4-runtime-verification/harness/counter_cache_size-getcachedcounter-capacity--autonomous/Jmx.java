import javax.management.*;
import javax.management.remote.*;
import java.io.*;

/** Cache gauge reader / operation caller. Usage:
 *    java Jmx <jmx-port> once <scope>            prints "epoch_ms,size,capacity,entries,hits,requests" (org.apache.cassandra.metrics:type=Cache,scope=<scope>; scope CounterCache | RowCache | KeyCache)
 *    java Jmx <jmx-port> save                    invokes org.apache.cassandra.db:type=Caches saveCaches()
 *    java Jmx <jmx-port> set <counter|row|key> <MiB>   sets the CacheService attribute CounterCacheCapacityInMB / RowCacheCapacityInMB / KeyCacheCapacityInMB (MBean org.apache.cassandra.db:type=Caches) */
public class Jmx
{
    static Object g(MBeanServerConnection c, String scope, String name, String attr) throws Exception
    {
        return c.getAttribute(new ObjectName("org.apache.cassandra.metrics:type=Cache,scope=" + scope + ",name=" + name), attr);
    }
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi");
        try (JMXConnector jc = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection c = jc.getMBeanServerConnection();
            if (a[1].equals("once"))
            {
                long t = System.currentTimeMillis();
                System.out.println(t + "," + g(c, a[2], "Size", "Value") + "," + g(c, a[2], "Capacity", "Value") + "," + g(c, a[2], "Entries", "Value")
                                   + "," + g(c, a[2], "Hits", "Count") + "," + g(c, a[2], "Requests", "Count"));
            }
            else if (a[1].equals("save"))
            {
                c.invoke(new ObjectName("org.apache.cassandra.db:type=Caches"), "saveCaches", new Object[0], new String[0]);
                System.out.println("saveCaches returned");
            }
            else if (a[1].equals("set"))
            {
                String op = a[2].equals("counter") ? "CounterCacheCapacityInMB" : a[2].equals("row") ? "RowCacheCapacityInMB" : "KeyCacheCapacityInMB";
                try
                {
                    c.setAttribute(new ObjectName("org.apache.cassandra.db:type=Caches"), new Attribute(op, Long.parseLong(a[3])));
                    System.out.println("set " + op + "=" + a[3] + " returned");
                }
                catch (Exception e) { System.out.println("set " + op + "=" + a[3] + " threw " + e); }
            }
        }
    }
}
