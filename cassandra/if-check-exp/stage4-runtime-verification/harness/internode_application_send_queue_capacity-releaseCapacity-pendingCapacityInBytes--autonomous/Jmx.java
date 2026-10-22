import java.io.File;
import java.util.Set;
import java.util.TreeSet;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Node on 127.0.0.1, the JMX port given as the first argument, no auth. Read-only.
 *   java Jmx <port> get <bean> <attr> [<bean> <attr> ...]        prints bean|attr|value per pair
 *   java Jmx <port> query <pattern> <attr>                        prints bean|attr|value for every bean matching the pattern
 *   java Jmx <port> poll <ms> <n> <stopfile> <bean> <attr> ...   one JVM, one connection: every <ms> ms prints
 *                                                                 "<epoch ms>,<v1>,<v2>,..." until <n> samples or until
 *                                                                 <stopfile> exists
 * A CompositeData attribute (java.lang:type=Memory HeapMemoryUsage) prints its "used" item. From the max_hints_size_per_host
 * harness's Jmx.java (setint dropped, poll added) for internode_application_receive_queue_capacity, 2026-10-14. Copied for
 * the releaseCapacity--autonomous case 2026-10-21 and unchanged for the send-side releaseCapacity--autonomous case; poll fixed so a failed attribute is one field ("ERR"), not two.
 */
public class Jmx
{
    static Object value(MBeanServerConnection m, String bean, String attr) throws Exception
    {
        Object v = m.getAttribute(new ObjectName(bean), attr);
        if (v instanceof CompositeData)
            return ((CompositeData) v).get("used");
        return v;
    }

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[0]) + "/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            if (a[1].equals("get"))
            {
                for (int i = 2; i + 1 < a.length; i += 2)
                {
                    try
                    {
                        System.out.println(a[i] + "|" + a[i + 1] + "|" + value(m, a[i], a[i + 1]));
                    }
                    catch (Exception e)
                    {
                        System.out.println(a[i] + "|" + a[i + 1] + "|ERROR " + e.getClass().getSimpleName());
                    }
                }
            }
            else if (a[1].equals("query"))
            {
                Set<String> names = new TreeSet<>();
                for (ObjectName n : m.queryNames(new ObjectName(a[2]), null))
                    names.add(n.toString());
                for (String n : names)
                    System.out.println(n + "|" + a[3] + "|" + value(m, n, a[3]));
                System.out.println("QUERY-END " + names.size());
            }
            else if (a[1].equals("poll"))
            {
                long ms = Long.parseLong(a[2]);
                int n = Integer.parseInt(a[3]);
                File stop = new File(a[4]);
                long next = System.currentTimeMillis();
                for (int k = 0; k < n && !stop.exists(); k++)
                {
                    StringBuilder sb = new StringBuilder().append(System.currentTimeMillis());
                    for (int i = 5; i + 1 < a.length; i += 2)
                    {
                        Object v;
                        try
                        {
                            v = value(m, a[i], a[i + 1]);
                        }
                        catch (Exception e)
                        {
                            v = "ERR";
                        }
                        sb.append(',').append(v);   // one field per attribute (fixed 2026-10-21: the copy wrote ",,ERR")
                    }
                    System.out.println(sb);
                    System.out.flush();
                    next += ms;
                    long w = next - System.currentTimeMillis();
                    if (w > 0)
                        Thread.sleep(w);
                }
            }
            else
            {
                throw new IllegalArgumentException("unknown command " + a[1]);
            }
        }
    }
}
