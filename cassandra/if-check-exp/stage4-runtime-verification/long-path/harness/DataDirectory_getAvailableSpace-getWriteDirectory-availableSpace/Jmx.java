import javax.management.Attribute;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Local node, port 7199, no auth.
 *   java Jmx get <bean> <attr> [<bean> <attr> ...]      prints bean|attr|value per pair (several attributes in one JVM start)
 *   java Jmx invoke <bean> <operation> <true|false>      invokes an operation that takes one boolean (compactionDiskSpaceCheck)
 *   java Jmx set <bean> <attr> <string value>            sets a string attribute
 */
public class Jmx
{
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            if (a[0].equals("get"))
                for (int i = 1; i + 1 < a.length; i += 2)
                    System.out.println(a[i] + "|" + a[i + 1] + "|" + m.getAttribute(new ObjectName(a[i]), a[i + 1]));
            else if (a[0].equals("invoke"))
            {
                Object r = m.invoke(new ObjectName(a[1]), a[2], new Object[] { Boolean.valueOf(a[3]) }, new String[] { "boolean" });
                System.out.println("invoked " + a[1] + " " + a[2] + "(" + a[3] + ") -> " + r);
            }
            else if (a[0].equals("set"))
            {
                m.setAttribute(new ObjectName(a[1]), new Attribute(a[2], a[3]));
                System.out.println("set " + a[2] + " " + a[3]);
            }
        }
    }
}
