import java.util.Set;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Node on 127.0.0.1, the JMX port given as the first argument, no auth.
 *   java Jmx <port> get <bean> <attr> [<bean> <attr> ...]   prints bean|attr|value per pair (several attributes in one JVM start)
 *   java Jmx <port> query <pattern>                         prints the names of the beans that match an ObjectName pattern
 * Adapted from the JMX client of the max_space_usable_for_compactions... harness (which hard-codes 7199); read-only.
 */
public class Jmx
{
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
                        System.out.println(a[i] + "|" + a[i + 1] + "|" + m.getAttribute(new ObjectName(a[i]), a[i + 1]));
                    }
                    catch (Exception e)
                    {
                        System.out.println(a[i] + "|" + a[i + 1] + "|ERROR " + e.getClass().getSimpleName());
                    }
                }
            }
            else if (a[1].equals("query"))
            {
                Set<ObjectName> names = m.queryNames(new ObjectName(a[2]), null);
                for (ObjectName n : new java.util.TreeSet<>(names))
                    System.out.println(n);
            }
        }
    }
}
