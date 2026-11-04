import javax.management.Attribute;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Node on 127.0.0.1, the JMX port given as the first argument, no auth.
 *   java Jmx <port> get <bean> <attr> [<bean> <attr> ...]   prints bean|attr|value per pair
 *   java Jmx <port> setint <bean> <attr> <int>              sets an int attribute, then prints bean|attr|value read back
 * Adapted from the internode_application_send_queue_capacity harness's Jmx.java (read-only there); setint added.
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
            else if (a[1].equals("setint"))
            {
                ObjectName n = new ObjectName(a[2]);
                m.setAttribute(n, new Attribute(a[3], Integer.parseInt(a[4])));
                System.out.println(a[2] + "|" + a[3] + "|" + m.getAttribute(n, a[3]));
            }
            else
            {
                throw new IllegalArgumentException("unknown command " + a[1]);
            }
        }
    }
}
