import javax.management.Attribute;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Node on 127.0.0.1, the JMX port given as the first argument, no auth. Adapted from the repair_session_space harness.
 *   java Jmx <port> get <bean> <attr> [<bean> <attr> ...]       prints bean|attr|value per pair
 *   java Jmx <port> setdouble <bean> <attr> <double>            sets, then prints bean|attr|value read back; on failure prints
 *                                                               SETFAIL <exception chain messages> and exits 3
 *   java Jmx <port> setstring <bean> <attr> <string|null>       the same for a String attribute ("null" writes a null)
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
                    try { System.out.println(a[i] + "|" + a[i + 1] + "|" + m.getAttribute(new ObjectName(a[i]), a[i + 1])); }
                    catch (Exception e) { System.out.println(a[i] + "|" + a[i + 1] + "|ERROR " + e.getClass().getSimpleName()); }
                }
                return;
            }
            ObjectName n = new ObjectName(a[2]);
            Object v = a[1].equals("setdouble") ? (Object) Double.valueOf(a[4]) : (a[4].equals("null") ? null : a[4]);
            try
            {
                m.setAttribute(n, new Attribute(a[3], v));
            }
            catch (Exception e)
            {
                StringBuilder sb = new StringBuilder("SETFAIL");
                for (Throwable t = e; t != null; t = t.getCause())
                    sb.append(" | ").append(t.getClass().getSimpleName()).append(": ").append(t.getMessage());
                System.out.println(sb);
                System.exit(3);
            }
            System.out.println(a[2] + "|" + a[3] + "|" + m.getAttribute(n, a[3]));
        }
    }
}
