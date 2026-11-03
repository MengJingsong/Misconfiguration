import javax.management.Attribute;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * usage (local node, port 7199, no auth):
 *   java Jmx get <bean> <attr> [<bean> <attr> ...]      prints bean|attr|value per pair
 *   java Jmx set <bean> <attr> <int|long|str|bool|null>:<value>   sets one attribute, then reads it back ("null:" writes a null)
 *   java Jmx setonly <bean> <attr> <int|long|str>:<value>  sets a write-only attribute (a setter without a getter, e.g.
 *                                                       CacheServiceMBean.setKeyCacheCapacityInMB(long) = attribute KeyCacheCapacityInMB)
 *   java Jmx invoke <bean> <op> <int|long|str>:<value>  invokes a one-argument operation
 */
public class Jmx
{
    static Object val(String tv)
    {
        int i = tv.indexOf(':');
        String t = tv.substring(0, i), v = tv.substring(i + 1);
        switch (t)
        {
            case "int": return Integer.valueOf(v);
            case "long": return Long.valueOf(v);
            case "bool": return Boolean.valueOf(v);
            case "null": return null;
            default: return v;
        }
    }

    static String sig(Object o)
    {
        return o instanceof Integer ? "int" : o instanceof Long ? "long" : o instanceof Boolean ? "boolean" : "java.lang.String";
    }

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            switch (a[0])
            {
                case "get":
                    for (int i = 1; i + 1 < a.length; i += 2)
                        System.out.println(a[i] + "|" + a[i + 1] + "|" + m.getAttribute(new ObjectName(a[i]), a[i + 1]));
                    break;
                case "set":
                    m.setAttribute(new ObjectName(a[1]), new Attribute(a[2], val(a[3])));
                    System.out.println(a[1] + "|" + a[2] + "|" + m.getAttribute(new ObjectName(a[1]), a[2]));
                    break;
                case "setonly":
                    m.setAttribute(new ObjectName(a[1]), new Attribute(a[2], val(a[3])));
                    System.out.println("set " + a[1] + "|" + a[2] + "|" + a[3]);
                    break;
                case "invoke":
                    Object v = val(a[3]);
                    Object r = m.invoke(new ObjectName(a[1]), a[2], new Object[]{ v }, new String[]{ sig(v) });
                    System.out.println("invoked " + a[2] + "(" + v + ") -> " + r);
                    break;
                default:
                    throw new IllegalArgumentException(a[0]);
            }
        }
    }
}
